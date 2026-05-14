from __future__ import annotations

import logging
import numbers

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ai_engine.models import QueryFeedback, QueryLog
from ai_engine.serializers import (
	AdminQueryFeedbackSerializer,
	AdminQueryLogSerializer,
	AskQuerySerializer,
	AskResponseSerializer,
	ChatQuerySerializer,
	QueryFeedbackSerializer,
)
from ai_engine.services.qa import generate_answer
from conversations.models import Conversation
from conversations.permissions import IsConversationOwner
from documents.models import Document

User = get_user_model()

logger = logging.getLogger(__name__)



def _json_native(value):
	"""Recursively convert numpy scalars and odd types to JSON-native Python (DRF 400-safe)."""
	if value is None:
		return None
	if hasattr(value, 'item') and callable(getattr(value, 'item')):
		try:
			return _json_native(value.item())
		except Exception:
			pass
	if isinstance(value, dict):
		return {k: _json_native(v) for k, v in value.items()}
	if isinstance(value, (list, tuple)):
		return [_json_native(v) for v in value]
	if isinstance(value, bool):
		return value
	if isinstance(value, numbers.Integral):
		return int(value)
	if isinstance(value, numbers.Real):
		return float(value)
	return value


def _chat_response_to_response_body(chat_response) -> dict:
	"""Build API JSON dict without failing DRF validation on numpy / edge types."""
	tu = chat_response.tokens_used or {}
	return {
		'answer': '' if chat_response.answer is None else str(chat_response.answer),
		'sources': _json_native(chat_response.sources or []),
		'model_used': str(chat_response.model_used),
		'tokens_used': {
			'prompt': int(_json_native(tu.get('prompt', 0))),
			'completion': int(_json_native(tu.get('completion', 0))),
			'total': int(_json_native(tu.get('total', 0))),
		},
		'retrieval_confidence': float(_json_native(chat_response.retrieval_confidence)),
		'warnings': [str(w) for w in (chat_response.warnings or [])],
		'query_id': int(chat_response.query_log_id) if chat_response.query_log_id is not None else None,
	}


class ChatAskView(generics.CreateAPIView):
	"""
	Chat endpoint: grounded RAG when document passages exist, otherwise general chat.

	POST /api/v1/chat/{conversation_id}/ask/
	{
		"query": "What are the key clauses?",
		"top_k": 5
	}

	Does not require conversation.document; retrieval prefers attached document, else the owner's library.
	If no chunks match, the LLM answers conversationally (no 400).
	"""
	serializer_class = ChatQuerySerializer
	permission_classes = [permissions.IsAuthenticated, IsConversationOwner]

	def get_conversation(self) -> Conversation:
		"""Fetch and validate conversation ownership. Document FK is optional — chat works without it."""
		conversation = Conversation.objects.select_related('document', 'owner').get(
			pk=self.kwargs['conversation_pk']
		)
		self.check_object_permissions(self.request, conversation)
		return conversation

	def create(self, request, *args, **kwargs):
		"""Handle chat query."""
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		query = serializer.validated_data['query']
		top_k = serializer.validated_data.get('top_k', 5)

		try:
			conversation = self.get_conversation()
		except Conversation.DoesNotExist:
			return Response(
				{'detail': 'Conversation not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		# Intentional: never require conversation.document. RAG scopes to attached doc if present,
		# otherwise RetrievalService falls back to all chunks owned by conversation.owner.
		doc_pk = getattr(conversation.document, 'pk', None)
		logger.info(
			'chat_ask start conversation_id=%s owner_id=%s document_id=%s (optional)',
			conversation.id,
			conversation.owner_id,
			doc_pk,
		)

		# Conversations may start without a document; retrieval returns no chunks and the LLM still answers.
		try:
			from ai_engine.services.rag import RAGPipeline

			pipeline = RAGPipeline()
			chat_response = pipeline.process_query(
				query=query,
				conversation=conversation,
				top_k=top_k,
				save_log=True,
			)
		except Exception as exc:
			logger.exception(f'RAG pipeline failed: {exc}')
			return Response(
				{'detail': 'An internal error occurred while processing the request.'},
				status=status.HTTP_500_INTERNAL_SERVER_ERROR,
			)

		try:
			from conversations.models import ConversationMessage
			from conversations.services import create_conversation_message

			user_message = create_conversation_message(
				conversation=conversation,
				content=query,
			)

			assistant_message = ConversationMessage.objects.create(
				conversation=conversation,
				sender=ConversationMessage.Sender.ASSISTANT,
				content=chat_response.answer,
				metadata={
					'sources': chat_response.sources,
					'model': chat_response.model_used,
					'tokens': chat_response.tokens_used,
					'retrieval_confidence': chat_response.retrieval_confidence,
					'warnings': chat_response.warnings,
					'query_log_id': chat_response.query_log_id,
				},
			)
			conversation.last_message_at = assistant_message.created_at
			conversation.save(update_fields=['last_message_at'])
		except Exception as exc:
			logger.exception(f'Failed to save messages to conversation: {exc}')
			# Propagate failure to response warnings so callers are aware
			if hasattr(chat_response, 'warnings'):
				chat_response.warnings.append('Failed to persist messages to conversation history')
			# Do not update conversation.last_message_at when save failed

		body = _chat_response_to_response_body(chat_response)
		return Response(body, status=status.HTTP_200_OK)


_ASK_RATE_WINDOW_SECONDS = 60


def _record_ask_call(user_id: int) -> int:
	"""Best-effort per-user request counter over the last 60s.

	Uses Django's cache (LocMem in dev, Redis in prod when REDIS_URL is set).
	Any cache failure is swallowed and reported as ``0`` so the request flow is
	never blocked. Layer DRF's ``UserRateThrottle`` on top for actual rate
	limiting; this helper is purely an observability counter.
	"""
	try:
		from django.core.cache import cache

		key = f'ask:rate:{user_id}'
		count = cache.get(key) or 0
		count = int(count) + 1
		cache.set(key, count, timeout=_ASK_RATE_WINDOW_SECONDS)
		return count
	except Exception as exc:
		logger.warning('ask: rate counter unavailable: %s', exc)
		return 0


class AskView(generics.GenericAPIView):
	"""
	Stateless retrieval-augmented Q&A over the caller's document library.

	POST /api/v1/ask/
	{
		"query": "What does the Commercial Code say about partnerships?",
		"top_k": 5,                # optional, 1..20, default 5
		"min_similarity": 0.0      # optional, 0.0..1.0, default 0.0
	}

	Response 200:
	{
		"answer": "...",
		"sources": [{"source_number": 1, "chunk_id": 42, ...}, ...],
		"model_used": "mistral-7b-instruct",
		"retrieval_confidence": 0.71,
		"latency_ms": 1842,
		"warnings": [],
		"query_log_id": 17
	}

	Differs from ``ChatAskView`` (which is scoped to a Conversation and writes
	turn-by-turn ``ConversationMessage`` rows) by being entirely stateless and
	library-wide. Useful for one-shot Q&A, evaluation harnesses, and external
	integrations.
	"""
	serializer_class = AskQuerySerializer
	permission_classes = [permissions.IsAuthenticated]

	@staticmethod
	def get_response_serializer():
		return AskResponseSerializer

	def post(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		query = serializer.validated_data['query']
		top_k = serializer.validated_data.get('top_k', 5)
		min_similarity = serializer.validated_data.get('min_similarity', 0.0)

		recent_count = _record_ask_call(request.user.id)
		logger.info(
			'ask: user_id=%s query_chars=%s top_k=%s min_similarity=%s recent_60s=%s',
			request.user.id,
			len(query),
			top_k,
			min_similarity,
			recent_count,
		)

		try:
			result = generate_answer(
				query=query,
				user=request.user,
				top_k=top_k,
				min_similarity=min_similarity,
			)
		except Exception as exc:
			logger.exception('ask: generate_answer failed: %s', exc)
			return Response(
				{'detail': 'An internal error occurred while processing the request.'},
				status=status.HTTP_500_INTERNAL_SERVER_ERROR,
			)

		return Response(result, status=status.HTTP_200_OK)


class ChatFeedbackView(generics.CreateAPIView):
	"""
	Submit feedback on a chat response.
	
	POST /api/v1/chat/feedback/{query_log_id}/
	{
		"rating": "up",
		"comment": "Helpful and accurate"
	}
	"""
	serializer_class = QueryFeedbackSerializer
	permission_classes = [permissions.IsAuthenticated]

	def perform_create(self, serializer):
		try:
			query_log = QueryLog.objects.get(pk=self.kwargs['query_log_pk'])
			if query_log.user != self.request.user:
				self.permission_denied(self.request, 'You can only provide feedback on your own queries')
			serializer.save(query_log=query_log)
		except QueryLog.DoesNotExist:
			from django.http import Http404
			raise Http404('Query not found')


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def analytics_view(request):
	"""
	Admin analytics endpoint.
	GET /api/v1/ai/analytics/?days=<1..90>

	Primary metrics (all-time, GLOBAL — the admin dashboard headline cards):
	- total_queries, avg_latency_ms, avg_retrieval_confidence from ALL QueryLog rows
	- helpful_feedback / unhelpful_feedback from ALL QueryFeedback rows
	- total_documents, total_users from live tables

	The `days` parameter still scopes **additive** period metrics used for
	trends: total_queries_in_period, active_users_in_period, queries_by_model,
	helpful_feedback_in_period, etc.

	Response shape (period fields are additive — older clients can ignore them):

	{
	  'total_queries': int,
	  'avg_latency_ms': float,
	  'avg_retrieval_confidence': float,
	  'helpful_feedback': int,
	  'unhelpful_feedback': int,
	  'feedback_breakdown': { helpful, not_helpful },
	  'total_documents': int,
	  'total_users': int,
	  'active_users_in_period': int,
	  'period_days': int,
	  'total_queries_in_period': int,
	  ...
	}
	"""
	# Validate 'days' query param
	_default_days = 7
	_min_days = 1
	_max_days = 90
	days_raw = request.query_params.get('days', None)
	if days_raw is None:
		days_back = _default_days
	else:
		try:
			days_back = int(days_raw)
		except (TypeError, ValueError):
			return Response({'detail': 'Invalid days parameter'}, status=status.HTTP_400_BAD_REQUEST)
		# clamp to sensible bounds
		days_back = max(_min_days, min(_max_days, days_back))

	cutoff_date = timezone.now() - timedelta(days=days_back)
	recent_logs = QueryLog.objects.filter(created_at__gte=cutoff_date)
	all_logs = QueryLog.objects.all()

	helpful_in_period = QueryFeedback.objects.filter(
		created_at__gte=cutoff_date,
		rating=QueryFeedback.Rating.THUMBS_UP,
	).count()
	unhelpful_in_period = QueryFeedback.objects.filter(
		created_at__gte=cutoff_date,
		rating=QueryFeedback.Rating.THUMBS_DOWN,
	).count()

	helpful_all = QueryFeedback.objects.filter(rating=QueryFeedback.Rating.THUMBS_UP).count()
	unhelpful_all = QueryFeedback.objects.filter(rating=QueryFeedback.Rating.THUMBS_DOWN).count()

	# `total_documents` and `total_users` are intentionally GLOBAL (not
	# bounded by `cutoff_date`). The admin dashboard "Total Documents" card
	# must reflect every ingested document, not just recent ones — bounding
	# it by the analytics window would silently understate the corpus.
	total_documents = Document.objects.count()
	total_users = User.objects.count()
	active_users_in_period = recent_logs.values('user').distinct().count()

	def _avg_float(qs, field: str) -> float:
		row = qs.aggregate(Avg(field))
		val = row.get(f'{field}__avg')
		if val is None:
			return 0.0
		return float(val)

	stats = {
		# Primary metrics (GLOBAL — all-time QueryLog / QueryFeedback), per admin spec:
		'total_queries': all_logs.count(),
		'avg_latency_ms': _avg_float(all_logs, 'latency_ms'),
		'avg_retrieval_confidence': _avg_float(all_logs, 'retrieval_confidence'),
		'helpful_feedback': helpful_all,
		'unhelpful_feedback': unhelpful_all,

		# Window-scoped (last `days` days) — additive for existing consumers:
		'total_queries_in_period': recent_logs.count(),
		'avg_latency_ms_in_period': _avg_float(recent_logs, 'latency_ms'),
		'avg_retrieval_confidence_in_period': _avg_float(recent_logs, 'retrieval_confidence'),
		'helpful_feedback_in_period': helpful_in_period,
		'unhelpful_feedback_in_period': unhelpful_in_period,
		'queries_by_model': dict(
			recent_logs.values('llm_model').annotate(count=Count('id')).values_list('llm_model', 'count')
		),
		# Back-compat: nested shape still mirrors the all-time thumbs counts.
		'feedback_breakdown': {
			'helpful': helpful_all,
			'not_helpful': unhelpful_all,
		},
		'period_days': days_back,

		# Global metrics (documents / accounts):
		'total_documents': total_documents,
		'total_users': total_users,
		'active_users_in_period': active_users_in_period,
	}

	return Response(stats)


class AdminQueryLogListView(generics.ListAPIView):
	"""
	GET /api/v1/ai/query-logs/

	Admin-only list of every query the RAG pipeline has answered. Supports
	`?search=` (against `query_text` and `llm_response`, case-insensitive)
	and `?min_confidence=` / `?max_confidence=` for filtering low-confidence
	retrievals (the admin SPA highlights `retrieval_confidence < 0.5` as
	"low confidence"; this view lets admins drill into just those rows if
	they want to).

	Pagination is disabled so the admin SPA can derive aggregate
	low-confidence / high-confidence counts from the array length. The
	queryset is capped to the 500 most recent rows in ``list()`` — older
	traffic should be narrowed with ``?min_confidence=`` / ``?search=``.

	Response envelope::

	    {
	      "count": <total rows matching filters (not capped)>,
	      "results": [ ... up to 500 rows ... ],
	      "stats": {
	        "total_queries": <same as count>,
	        "avg_latency_ms": float,
	        "avg_retrieval_confidence": float,
	        "low_confidence_count": int,  # retrieval_confidence < 0.5 (full filtered set)
	      }
	    }
	"""

	serializer_class = AdminQueryLogSerializer
	permission_classes = [permissions.IsAdminUser]
	pagination_class = None
	MAX_ROWS = 500

	def get_queryset(self):
		queryset = QueryLog.objects.select_related('user').order_by('-created_at')

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(
				Q(query_text__icontains=search) | Q(llm_response__icontains=search)
			)

		min_conf = self.request.query_params.get('min_confidence')
		max_conf = self.request.query_params.get('max_confidence')
		try:
			if min_conf is not None:
				queryset = queryset.filter(retrieval_confidence__gte=float(min_conf))
			if max_conf is not None:
				queryset = queryset.filter(retrieval_confidence__lte=float(max_conf))
		except (TypeError, ValueError):
			pass

		return queryset

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		total = queryset.count()
		avg_lat = queryset.aggregate(Avg('latency_ms'))['latency_ms__avg']
		avg_conf = queryset.aggregate(Avg('retrieval_confidence'))['retrieval_confidence__avg']
		low_confidence_count = queryset.filter(retrieval_confidence__lt=0.5).count()
		stats = {
			'total_queries': total,
			'avg_latency_ms': float(avg_lat or 0),
			'avg_retrieval_confidence': float(avg_conf or 0),
			'low_confidence_count': low_confidence_count,
		}
		page_qs = queryset[: self.MAX_ROWS]
		serializer = self.get_serializer(page_qs, many=True)
		return Response(
			{
				'count': total,
				'results': serializer.data,
				'stats': stats,
			}
		)


class AdminFeedbackListView(generics.ListAPIView):
	"""
	GET /api/v1/feedback/

	Admin-only list of every feedback record on the system. Joins to the
	parent `QueryLog` so each row carries the original query/response
	text inline — the admin UI renders all four columns in a single
	table.

	Supports `?is_helpful=true|false` (filters by mapped rating) and
	`?search=` (against the joined query/response text). The dedicated
	endpoint is preferred over inferring counts from `analytics_view`
	because the SPA needs per-row metadata (the analytics view returns
	aggregate counts only).

	Pagination is disabled (see sibling admin views for rationale) and
	the result list is capped to the 500 most recent rows in ``list()``.

	Response envelope::

	    {
	      "count": <rows matching filters (uncapped)>,
	      "results": [ ... up to 500 ... ],
	      "stats": { "total", "helpful", "unhelpful" }  # GLOBAL, ignores ?search=
	    }
	"""

	serializer_class = AdminQueryFeedbackSerializer
	permission_classes = [permissions.IsAdminUser]
	pagination_class = None
	MAX_ROWS = 500

	def get_queryset(self):
		queryset = QueryFeedback.objects.select_related('query_log', 'user').order_by('-created_at')

		is_helpful = self.request.query_params.get('is_helpful')
		if is_helpful is not None:
			# Accept 'true'/'false'/'1'/'0' — robust to whatever the SPA emits.
			truthy = str(is_helpful).strip().lower() in {'1', 'true', 'yes'}
			rating = QueryFeedback.Rating.THUMBS_UP if truthy else QueryFeedback.Rating.THUMBS_DOWN
			queryset = queryset.filter(rating=rating)

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(
				Q(query_log__query_text__icontains=search)
				| Q(query_log__llm_response__icontains=search)
				| Q(comment__icontains=search)
			)

		return queryset

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		base = QueryFeedback.objects.all()
		stats = {
			'total': base.count(),
			'helpful': base.filter(rating=QueryFeedback.Rating.THUMBS_UP).count(),
			'unhelpful': base.filter(rating=QueryFeedback.Rating.THUMBS_DOWN).count(),
		}
		page_qs = queryset[: self.MAX_ROWS]
		serializer = self.get_serializer(page_qs, many=True)
		return Response(
			{
				'count': queryset.count(),
				'results': serializer.data,
				'stats': stats,
			}
		)
