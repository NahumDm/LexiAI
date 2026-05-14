from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from ai_engine.models import QueryLog
from ai_engine.query_classification import (
	ASK_GREETING_RESPONSE,
	ASK_OUT_OF_SCOPE_RESPONSE,
	LEGAL_NO_CONTEXT_RESPONSE,
	classify_intent,
)
from ai_engine.services.embedding import EmbeddingService
from ai_engine.services.llm_client import ChatResponse, LLMClient
from ai_engine.services.retrieval import RetrievalService, db_user_for_chunk_corpus, user_visible_chunk_queryset

if TYPE_CHECKING:
	from conversations.models import Conversation

logger = logging.getLogger(__name__)


def _get_pipeline_llm() -> LLMClient:
	"""Resolve LLM client from Django settings (see AI_LLM_BACKEND, MISTRAL_*)."""
	from ai_engine.services.llm_client import get_llm_client

	return get_llm_client()


def _no_passages_answer_for_intent(intent: str) -> tuple[str, float]:
	"""Deterministic body when nothing qualifies; mirrors ``generate_answer`` routing."""
	if intent == 'legal':
		return LEGAL_NO_CONTEXT_RESPONSE, 0.0
	return ASK_OUT_OF_SCOPE_RESPONSE, 0.0


def _deterministic_chat_response(
	*,
	start_time,
	conversation,
	query: str,
	query_embedding,
	save_log: bool,
	warnings: list[str],
	answer: str,
	retrieval_confidence: float,
) -> ChatResponse:
	"""Return a document-grounded reply without calling the LLM."""
	latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
	response = ChatResponse(
		answer=answer,
		sources=[],
		model_used='n/a',
		tokens_used={'prompt': 0, 'completion': 0, 'total': 0},
		retrieval_confidence=float(retrieval_confidence),
		confidence=float(retrieval_confidence),
		warnings=warnings,
	)
	if save_log:
		try:
			log = QueryLog.objects.create(
				user=conversation.owner,
				conversation=conversation,
				query_text=query,
				query_embedding=EmbeddingService.embedding_to_bytes(query_embedding)
				if query_embedding is not None
				else None,
				retrieved_chunk_ids=[],
				llm_response=response.answer,
				llm_model=response.model_used,
				retrieval_confidence=float(retrieval_confidence),
				latency_ms=latency_ms,
				token_usage=response.tokens_used,
			)
			response.query_log_id = log.id
		except Exception as exc:
			logger.error('RAG: failed to log strict refusal: %s', exc)
	return response


class RAGPipeline:
	"""
	Orchestrates document-grounded RAG.

	Rule-based intent (greeting / out-of-scope) short-circuits before retrieval.
	When passages qualify, the LLM answers strictly from context. When nothing
	meets the similarity floor, the LLM still runs with a general-knowledge fallback
	prompt (not a hardcoded refusal).
	"""

	def __init__(self, llm_client: LLMClient | None = None):
		self.llm_client = llm_client or _get_pipeline_llm()

	def process_query(
		self,
		query: str,
		conversation: Conversation,
		top_k: int | None = None,
		save_log: bool = True,
		min_similarity: float | None = None,
		*,
		retrieval_user=None,
	) -> ChatResponse:
		start_time = timezone.now()
		eff_top_k = int(getattr(settings, 'RAG_DEFAULT_TOP_K', 3)) if top_k is None else int(top_k)
		floor = float(getattr(settings, 'RAG_MIN_SIMILARITY', 0.2))
		eff_min = max(floor, float(min_similarity)) if min_similarity is not None else floor

		subject = db_user_for_chunk_corpus(
			retrieval_user if retrieval_user is not None else conversation.owner
		)
		lib_count = user_visible_chunk_queryset(subject).count() if subject is not None else 0
		raw_user = retrieval_user if retrieval_user is not None else conversation.owner
		logger.info(
			'[DEBUG_RAG] user_id=%s is_authenticated=%s conversation_owner_id=%s '
			'visible_chunks_count=%s retrieval_user_kwarg=%s subject_resolved=%s',
			getattr(subject, 'pk', None),
			getattr(raw_user, 'is_authenticated', False),
			conversation.owner_id,
			lib_count,
			retrieval_user is not None,
			subject is not None,
		)
		logger.info(
			'RAG[1/5] received query conversation_id=%s has_document=%s corpus_user_id=%s '
			'corpus_chunk_count=%s (global+user) preview=%r top_k=%s min_sim=%s',
			conversation.id,
			bool(conversation.document),
			getattr(subject, 'pk', None),
			lib_count,
			(query or '')[:200],
			eff_top_k,
			eff_min,
		)

		work = (query or '').strip()
		if not work:
			logger.info('RAG[1/5] empty query — skipping retrieval')
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=None,
				save_log=save_log,
				warnings=['Query was empty.'],
				answer='',
				retrieval_confidence=0.0,
			)

		intent = classify_intent(work)
		if intent == 'greeting':
			logger.info('RAG[1/5] intent=greeting — skipping retrieval')
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=None,
				save_log=save_log,
				warnings=['Intent=greeting; retrieval skipped.'],
				answer=ASK_GREETING_RESPONSE,
				retrieval_confidence=1.0,
			)
		if intent == 'out_of_scope':
			logger.info('RAG[1/5] intent=out_of_scope — skipping retrieval')
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=None,
				save_log=save_log,
				warnings=['Intent=out_of_scope; retrieval skipped.'],
				answer=ASK_OUT_OF_SCOPE_RESPONSE,
				retrieval_confidence=1.0,
			)

		query_embedding = None
		try:
			query_embedding = EmbeddingService.generate_embedding(work)
			dim = int(query_embedding.shape[0]) if hasattr(query_embedding, 'shape') else len(query_embedding)
			logger.info('RAG[2/5] query embedding ok dim=%s', dim)
		except Exception as exc:
			logger.warning('RAG[2/5] query embedding failed: %s', exc)

		retrieved_chunks = []
		try:
			retrieved_chunks = RetrievalService.retrieve_by_conversation(
				conversation=conversation,
				query_text=work,
				top_k=eff_top_k,
				query_embedding=query_embedding,
				min_similarity=eff_min,
				retrieval_user=subject,
			)
			logger.info(
				'RAG[3/5] retrieval count=%s admin_hits=%s user_hits=%s ids_scores=%s',
				len(retrieved_chunks),
				sum(1 for c in retrieved_chunks if c.source == 'admin'),
				sum(1 for c in retrieved_chunks if c.source == 'user'),
				[(c.chunk.id, round(c.relevance_score, 4), c.source) for c in retrieved_chunks],
			)
		except Exception as exc:
			logger.exception('RAG[3/5] retrieval failed: %s', exc)
			msg, conf = _no_passages_answer_for_intent(intent)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=query_embedding,
				save_log=save_log,
				warnings=[f'Retrieval error: {exc}'],
				answer=msg,
				retrieval_confidence=conf,
			)

		if not retrieved_chunks:
			logger.info('RAG[3/5] zero chunks above threshold — LLM general-knowledge fallback')
			try:
				response = self.llm_client.generate_response(
					query=work,
					context_chunks=[],
				)
				response.retrieval_confidence = 0.0
				response.confidence = 0.0
			except Exception as exc:
				logger.error('RAG[3/5] LLM fallback failed: %s', exc)
				raise

			latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
			logger.info(
				'RAG[4/5] llm fallback ok model=%s answer_chars=%s',
				response.model_used,
				len(response.answer or ''),
			)
			logger.info('RAG[5/5] complete latency_ms=%s (no retrieval)', latency_ms)

			if save_log:
				try:
					log = QueryLog.objects.create(
						user=conversation.owner,
						conversation=conversation,
						query_text=work,
						query_embedding=EmbeddingService.embedding_to_bytes(query_embedding)
						if query_embedding is not None
						else None,
						retrieved_chunk_ids=[],
						llm_response=response.answer,
						llm_model=response.model_used,
						retrieval_confidence=0.0,
						latency_ms=latency_ms,
						token_usage=response.tokens_used,
					)
					response.query_log_id = log.id
					logger.info('Logged query to QueryLog id=%s preview=%r', log.id, work[:50])
				except Exception as exc:
					logger.error('Failed to log query: %s', exc)

			return response

		avg_confidence = sum(chunk.relevance_score for chunk in retrieved_chunks) / len(retrieved_chunks)
		max_confidence = max(chunk.relevance_score for chunk in retrieved_chunks)

		try:
			response = self.llm_client.generate_response(
				query=work,
				context_chunks=retrieved_chunks,
			)
			response.retrieval_confidence = avg_confidence
			response.confidence = max_confidence
			logger.info(
				'RAG[4/5] llm ok model=%s answer_chars=%s warnings=%s max_sim=%.4f avg_sim=%.4f',
				response.model_used,
				len(response.answer or ''),
				len(response.warnings or []),
				max_confidence,
				avg_confidence,
			)
		except Exception as exc:
			logger.error('LLM generation failed: %s', exc)
			raise

		latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
		logger.info(
			'RAG[5/5] complete latency_ms=%s avg_sim=%.4f max_sim=%.4f',
			latency_ms,
			avg_confidence,
			max_confidence,
		)

		if save_log:
			try:
				log = QueryLog.objects.create(
					user=conversation.owner,
					conversation=conversation,
					query_text=work,
					query_embedding=EmbeddingService.embedding_to_bytes(query_embedding)
					if query_embedding is not None
					else None,
					retrieved_chunk_ids=[chunk.chunk.id for chunk in retrieved_chunks],
					llm_response=response.answer,
					llm_model=response.model_used,
					retrieval_confidence=avg_confidence,
					latency_ms=latency_ms,
					token_usage=response.tokens_used,
				)
				response.query_log_id = log.id
				logger.info('Logged query to QueryLog id=%s preview=%r', log.id, work[:50])
			except Exception as exc:
				logger.error('Failed to log query: %s', exc)

		return response
