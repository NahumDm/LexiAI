from __future__ import annotations

import logging

from django.db.models import Avg, Count
from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ai_engine.models import QueryFeedback, QueryLog
from ai_engine.serializers import ChatQuerySerializer, ChatResponseSerializer, QueryFeedbackSerializer
from conversations.models import Conversation
from conversations.permissions import IsConversationOwner

logger = logging.getLogger(__name__)


class ChatAskView(generics.CreateAPIView):
	"""
	Chat endpoint that runs the full RAG pipeline.
	Retrieves relevant chunks and generates a grounded answer.

	POST /api/v1/chat/{conversation_id}/ask/
	{
		"query": "What are the key clauses?",
		"top_k": 5
	}
	"""
	serializer_class = ChatQuerySerializer
	permission_classes = [permissions.IsAuthenticated, IsConversationOwner]

	def get_conversation(self) -> Conversation:
		"""Fetch and validate conversation ownership."""
		conversation = Conversation.objects.get(pk=self.kwargs['conversation_pk'])
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

		if not conversation.document:
			return Response(
				{'detail': 'This conversation has no document attached. Attach a document first.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

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

		response_serializer = ChatResponseSerializer(data={
			'answer': chat_response.answer,
			'sources': chat_response.sources,
			'model_used': chat_response.model_used,
			'tokens_used': chat_response.tokens_used,
			'retrieval_confidence': chat_response.retrieval_confidence,
			'warnings': chat_response.warnings,
		})
		response_serializer.is_valid(raise_exception=True)

		return Response(response_serializer.data, status=status.HTTP_200_OK)


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
	GET /api/v1/ai/analytics/
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

	stats = {
		'total_queries': recent_logs.count(),
		'avg_latency_ms': recent_logs.aggregate(Avg('latency_ms'))['latency_ms__avg'] or 0,
		'avg_retrieval_confidence': recent_logs.aggregate(Avg('retrieval_confidence'))['retrieval_confidence__avg'] or 0,
		'queries_by_model': dict(recent_logs.values('llm_model').annotate(count=Count('id')).values_list('llm_model', 'count')),
		'feedback_breakdown': {
			'helpful': QueryFeedback.objects.filter(
				created_at__gte=cutoff_date,
				rating=QueryFeedback.Rating.THUMBS_UP
			).count(),
			'not_helpful': QueryFeedback.objects.filter(
				created_at__gte=cutoff_date,
				rating=QueryFeedback.Rating.THUMBS_DOWN
			).count(),
		},
		'total_users': recent_logs.values('user').distinct().count(),
		'period_days': days_back,
	}

	return Response(stats)
