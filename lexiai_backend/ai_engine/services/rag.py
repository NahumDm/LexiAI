from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_engine.models import QueryLog
from ai_engine.services.embedding import EmbeddingService
from ai_engine.services.llm_client import LLMClient
from ai_engine.services.retrieval import RetrievalService
from django.utils import timezone

if TYPE_CHECKING:
    from conversations.models import Conversation

logger = logging.getLogger(__name__)


def _get_pipeline_llm() -> LLMClient:
	"""Resolve LLM client from Django settings (see AI_LLM_BACKEND, MISTRAL_*)."""
	from ai_engine.services.llm_client import get_llm_client

	return get_llm_client()


class RAGPipeline:
    """
    Orchestrates the full RAG (Retrieval-Augmented Generation) flow.
    Handles: query embedding -> retrieval -> LLM generation -> response.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or _get_pipeline_llm()

    def process_query(
        self,
        query: str,
        conversation: Conversation,
        top_k: int = 5,
        save_log: bool = True,
    ) -> ChatResponse:
        """
        Process a user query through the full RAG pipeline.

        Steps:
        1. Embed the query
        2. Retrieve relevant chunks from conversation document
        3. Generate response with LLM
        4. Log the query for analytics
        5. Return response with sources
        """
        start_time = timezone.now()

        logger.info('RAG[1/5] received query conversation_id=%s has_document=%s preview=%r',
                    conversation.id, bool(conversation.document), query[:200])

        # Fast path: avoid expensive embedding/model warmup when there are no candidate chunks.
        if conversation.document_id:
            has_candidate_chunks = conversation.document.chunks.exists()
        else:
            has_candidate_chunks = conversation.owner.document_chunks.exists()
        if not has_candidate_chunks:
            logger.info('RAG[2/5] skipped embedding/retrieval: no candidate chunks available')
            response = self.llm_client.generate_response(query=query, context_chunks=[])
            response.retrieval_confidence = 0.0
            latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            logger.info('RAG[5/5] complete latency_ms=%s retrieval_confidence=0.0000', latency_ms)
            if save_log:
                try:
                    log = QueryLog.objects.create(
                        user=conversation.owner,
                        conversation=conversation,
                        query_text=query,
                        query_embedding=None,
                        retrieved_chunk_ids=[],
                        llm_response=response.answer,
                        llm_model=response.model_used,
                        retrieval_confidence=0.0,
                        latency_ms=latency_ms,
                        token_usage=response.tokens_used,
                    )
                    response.query_log_id = log.id
                    logger.info('Logged query to QueryLog id=%s preview=%r', log.id, query[:50])
                except Exception as exc:
                    logger.error(f'Failed to log query: {exc}')
            return response

        query_embedding = None
        try:
            query_embedding = EmbeddingService.generate_embedding(query)
            dim = int(query_embedding.shape[0]) if hasattr(query_embedding, 'shape') else len(query_embedding)
            logger.info('RAG[2/5] query embedding ok dim=%s', dim)
        except Exception as exc:
            # Do not fail the request: retrieval can embed internally, or we fall back to general chat with no chunks.
            logger.warning('RAG[2/5] query embedding skipped (general chat / retrieval may still run): %s', exc)

        retrieved_chunks = []
        try:
            retrieved_chunks = RetrievalService.retrieve_by_conversation(
                conversation=conversation,
                query_text=query,
                top_k=top_k,
                query_embedding=query_embedding,
            )
            mode = 'rag' if retrieved_chunks else 'general_chat'
            logger.info(
                'RAG[3/5] retrieval mode=%s count=%s ids_scores=%s',
                mode,
                len(retrieved_chunks),
                [(c.chunk.id, round(c.relevance_score, 4)) for c in retrieved_chunks],
            )
        except Exception as exc:
            # Never fail the HTTP layer for retrieval — LLM answers without context (general chat).
            logger.warning(
                'RAG[3/5] retrieval raised %s; continuing with zero chunks (general chat)',
                exc,
                exc_info=True,
            )
            retrieved_chunks = []

        avg_confidence = (
            sum(chunk.relevance_score for chunk in retrieved_chunks) / len(retrieved_chunks)
            if retrieved_chunks
            else 0.0
        )

        try:
            response = self.llm_client.generate_response(
                query=query,
                context_chunks=retrieved_chunks,
            )
            response.retrieval_confidence = avg_confidence
            logger.info(
                'RAG[4/5] llm ok model=%s answer_chars=%s warnings=%s',
                response.model_used,
                len(response.answer or ''),
                len(response.warnings or []),
            )
        except Exception as exc:
            logger.error(f'LLM generation failed: {exc}')
            raise

        latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)
        logger.info('RAG[5/5] complete latency_ms=%s retrieval_confidence=%.4f', latency_ms, avg_confidence)

        if save_log:
            try:
                log = QueryLog.objects.create(
                    user=conversation.owner,
                    conversation=conversation,
                    query_text=query,
                    query_embedding=EmbeddingService.embedding_to_bytes(query_embedding) if query_embedding is not None else None,
                    retrieved_chunk_ids=[chunk.chunk.id for chunk in retrieved_chunks],
                    llm_response=response.answer,
                    llm_model=response.model_used,
                    retrieval_confidence=avg_confidence,
                    latency_ms=latency_ms,
                    token_usage=response.tokens_used,
                )
                response.query_log_id = log.id
                logger.info('Logged query to QueryLog id=%s preview=%r', log.id, query[:50])
            except Exception as exc:
                logger.error(f'Failed to log query: {exc}')

        return response
