from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from ai_engine.models import QueryLog
from ai_engine.confidence import (
	LOW_EVIDENCE_MAX_SIMILARITY,
	MIN_ANSWER_MAX_SIMILARITY,
	calculate_confidence,
	confidence_percent_to_unit,
	max_bracket_citation_index,
)
from ai_engine.query_classification import (
	ASK_GREETING_RESPONSE,
	ASK_OUT_OF_SCOPE_RESPONSE,
	classify_intent,
)
from ai_engine.strict_grounding import (
	STRICT_NO_RETRIEVAL_ANSWER,
	answer_signals_insufficient_documents,
	cap_confidence_when_absence_indicated,
	legal_response_has_required_structure,
)
from ai_engine.services.embedding import EmbeddingService
from ai_engine.services.llm_client import ChatResponse, LLMClient
from ai_engine.services.retrieval import RetrievalService, db_user_for_chunk_corpus, user_visible_chunk_queryset

if TYPE_CHECKING:
	from conversations.models import Conversation

logger = logging.getLogger(__name__)

_LOW_EVIDENCE_NOTE = '⚠️ Note: Limited supporting evidence found in documents.'


def _rag_final_check(
	*,
	chunk_ids: list[int],
	max_similarity: float,
	confidence: float,
	refused: bool,
) -> None:
	logger.info(
		'[RAG_FINAL_CHECK] retrieved_chunks=%s max_similarity=%.4f confidence=%.4f refused=%s',
		chunk_ids,
		max_similarity,
		confidence,
		refused,
	)


def _get_pipeline_llm() -> LLMClient:
	"""Resolve LLM client from Django settings (see AI_LLM_BACKEND, MISTRAL_*)."""
	from ai_engine.services.llm_client import get_llm_client

	return get_llm_client()


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
	confidence: float | None = None,
) -> ChatResponse:
	"""Return a reply without calling the LLM."""
	latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
	conf = float(confidence) if confidence is not None else float(retrieval_confidence)
	response = ChatResponse(
		answer=answer,
		sources=[],
		model_used='n/a',
		tokens_used={'prompt': 0, 'completion': 0, 'total': 0},
		retrieval_confidence=float(retrieval_confidence),
		confidence=conf,
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


def _general_knowledge_enabled() -> bool:
	return bool(getattr(settings, 'ALLOW_GENERAL_KNOWLEDGE_FALLBACK', True))


def _answer_from_general_knowledge(
	pipeline: RAGPipeline,
	*,
	start_time,
	conversation: Conversation,
	work: str,
	query_embedding,
	save_log: bool,
) -> ChatResponse:
	logger.info('[RAG] No chunks — using Mistral general knowledge for query=%r', work[:200])
	response = pipeline.llm_client.generate_general_knowledge_response(work)
	response.answer_source = 'general_knowledge'

	_rag_final_check(chunk_ids=[], max_similarity=0.0, confidence=0.0, refused=False)

	if save_log:
		latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
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
		except Exception as exc:
			logger.error('RAG: failed to log general knowledge answer: %s', exc)

	return response


class RAGPipeline:
	"""
	Orchestrates document-grounded RAG.

	Rule-based intent (greeting / out-of-scope) short-circuits before retrieval.
	When passages qualify and max similarity meets the quality gate, the LLM answers
	from context only; otherwise the pipeline returns a deterministic refusal without
	calling the model.
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
			_rag_final_check(chunk_ids=[], max_similarity=0.0, confidence=0.0, refused=True)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=None,
				save_log=save_log,
				warnings=['Query was empty.'],
				answer='',
				retrieval_confidence=0.0,
				confidence=0.0,
			)

		intent = classify_intent(work)
		if intent == 'greeting':
			logger.info('RAG[1/5] intent=greeting — skipping retrieval')
			_rag_final_check(chunk_ids=[], max_similarity=-1.0, confidence=1.0, refused=False)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=None,
				save_log=save_log,
				warnings=['Intent=greeting; retrieval skipped.'],
				answer=ASK_GREETING_RESPONSE,
				retrieval_confidence=1.0,
				confidence=1.0,
			)
		if intent == 'out_of_scope':
			logger.info('RAG[1/5] intent=out_of_scope — skipping retrieval')
			_rag_final_check(chunk_ids=[], max_similarity=-1.0, confidence=1.0, refused=False)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=None,
				save_log=save_log,
				warnings=['Intent=out_of_scope; retrieval skipped.'],
				answer=ASK_OUT_OF_SCOPE_RESPONSE,
				retrieval_confidence=1.0,
				confidence=1.0,
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
			_rag_final_check(chunk_ids=[], max_similarity=0.0, confidence=0.0, refused=True)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=query_embedding,
				save_log=save_log,
				warnings=[f'Retrieval error: {exc}'],
				answer=STRICT_NO_RETRIEVAL_ANSWER,
				retrieval_confidence=0.0,
				confidence=0.0,
			)

		if not retrieved_chunks:
			if _general_knowledge_enabled():
				return _answer_from_general_knowledge(
					self,
					start_time=start_time,
					conversation=conversation,
					work=work,
					query_embedding=query_embedding,
					save_log=save_log,
				)
			logger.info('RAG[3/5] zero chunks — strict refusal (no LLM)')
			_rag_final_check(chunk_ids=[], max_similarity=0.0, confidence=0.0, refused=True)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=query_embedding,
				save_log=save_log,
				warnings=[],
				answer=STRICT_NO_RETRIEVAL_ANSWER,
				retrieval_confidence=0.0,
				confidence=0.0,
			)

		filtered = [
			c for c in retrieved_chunks if float(c.relevance_score) >= MIN_ANSWER_MAX_SIMILARITY
		]
		context_chunks = filtered[:eff_top_k]
		if not context_chunks:
			logger.info('RAG[3/5] no chunks at or above quality similarity — strict refusal (no LLM)')
			_rag_final_check(
				chunk_ids=[c.chunk.id for c in retrieved_chunks],
				max_similarity=max(float(c.relevance_score) for c in retrieved_chunks),
				confidence=0.0,
				refused=True,
			)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=query_embedding,
				save_log=save_log,
				warnings=[],
				answer=STRICT_NO_RETRIEVAL_ANSWER,
				retrieval_confidence=0.0,
				confidence=0.0,
			)

		similarities = [float(chunk.relevance_score) for chunk in context_chunks]
		avg_confidence = sum(similarities) / len(similarities)
		max_confidence = max(similarities)
		chunk_ids_all = [c.chunk.id for c in context_chunks]

		if max_confidence < MIN_ANSWER_MAX_SIMILARITY:
			logger.info(
				'RAG[3/5] max_similarity below quality gate — strict refusal (no LLM) max_sim=%.4f',
				max_confidence,
			)
			_rag_final_check(
				chunk_ids=chunk_ids_all,
				max_similarity=max_confidence,
				confidence=0.0,
				refused=True,
			)
			return _deterministic_chat_response(
				start_time=start_time,
				conversation=conversation,
				query=work,
				query_embedding=query_embedding,
				save_log=save_log,
				warnings=[],
				answer=STRICT_NO_RETRIEVAL_ANSWER,
				retrieval_confidence=0.0,
				confidence=0.0,
			)

		logger.info(
			'RAG[3/5] context for LLM: n=%s (top_k=%s) ids_scores=%s',
			len(context_chunks),
			eff_top_k,
			[(c.chunk.id, round(c.relevance_score, 4)) for c in context_chunks],
		)

		try:
			response = self.llm_client.generate_response(
				query=work,
				context_chunks=context_chunks,
			)
		except Exception as exc:
			logger.error('LLM generation failed: %s', exc)
			raise

		n = len(context_chunks)
		response.sources = (response.sources or [])[:n]

		raw_answer = response.answer
		citation_ok = max_bracket_citation_index(raw_answer) <= n
		if not citation_ok:
			logger.warning(
				'RAG: model reply rejected — citation index exceeds %s provided excerpt(s) (max seen=%s)',
				n,
				max_bracket_citation_index(raw_answer),
			)
			response.answer = STRICT_NO_RETRIEVAL_ANSWER
			response.sources = []
			response.warnings = list(response.warnings or [])

		format_ok = legal_response_has_required_structure(raw_answer) and citation_ok
		insufficient = answer_signals_insufficient_documents(raw_answer)
		if not format_ok:
			logger.warning('RAG: model reply rejected — missing required legal headings (no LLM retry)')
			response.answer = STRICT_NO_RETRIEVAL_ANSWER
			response.sources = []
			response.warnings = list(response.warnings or [])

		refused_answer = (response.answer or '').strip() == STRICT_NO_RETRIEVAL_ANSWER
		if insufficient and format_ok:
			confidence_pct = 0.0
			confidence_unit = 0.0
		elif not format_ok or refused_answer:
			confidence_pct = 0.0
			confidence_unit = 0.0
		else:
			confidence_pct = calculate_confidence(similarities, n)
			confidence_unit = confidence_percent_to_unit(confidence_pct)

		if confidence_unit > 0.0:
			confidence_unit = cap_confidence_when_absence_indicated(confidence_unit, raw_answer)
			confidence_pct = round(confidence_unit * 100, 1)

		response.retrieval_confidence = avg_confidence
		response.confidence = confidence_unit

		wlist = list(response.warnings or [])
		if (
			format_ok
			and not refused_answer
			and not insufficient
			and MIN_ANSWER_MAX_SIMILARITY <= max_confidence < LOW_EVIDENCE_MAX_SIMILARITY
		):
			if _LOW_EVIDENCE_NOTE not in wlist:
				wlist.append(_LOW_EVIDENCE_NOTE)
			note_block = f'\n\n{_LOW_EVIDENCE_NOTE}'
			body = (response.answer or '').rstrip()
			if _LOW_EVIDENCE_NOTE not in body:
				response.answer = body + note_block
		response.warnings = wlist

		refused = refused_answer or not format_ok
		_rag_final_check(
			chunk_ids=chunk_ids_all,
			max_similarity=max_confidence,
			confidence=float(response.confidence),
			refused=refused,
		)

		logger.info(
			'RAG[4/5] llm ok model=%s answer_chars=%s warnings=%s max_sim=%.4f avg_sim=%.4f conf_unit=%.4f',
			response.model_used,
			len(response.answer or ''),
			len(response.warnings or []),
			max_confidence,
			avg_confidence,
			response.confidence,
		)

		latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
		logger.info(
			'RAG[5/5] complete latency_ms=%s avg_sim=%.4f max_sim=%.4f',
			latency_ms,
			avg_confidence,
			max_confidence,
		)

		response.answer_source = 'rag'

		if save_log:
			try:
				log = QueryLog.objects.create(
					user=conversation.owner,
					conversation=conversation,
					query_text=work,
					query_embedding=EmbeddingService.embedding_to_bytes(query_embedding)
					if query_embedding is not None
					else None,
					retrieved_chunk_ids=[chunk.chunk.id for chunk in context_chunks],
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
