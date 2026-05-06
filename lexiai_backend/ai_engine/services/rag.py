from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_engine.models import QueryLog
from ai_engine.services.embedding import EmbeddingService
from ai_engine.services.llm_client import ChatResponse, StubLLMClient, LLMClient
from ai_engine.services.retrieval import RetrievalService
from django.utils import timezone

if TYPE_CHECKING:
    from conversations.models import Conversation

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Orchestrates the full RAG (Retrieval-Augmented Generation) flow.
    Handles: query embedding -> retrieval -> LLM generation -> response.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or StubLLMClient()

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

        query_embedding = None
        try:
            query_embedding = EmbeddingService.generate_embedding(query)
            logger.info(f'Generated query embedding for: {query[:100]}')
        except Exception as exc:
            logger.error(f'Embedding generation failed: {exc}')
            raise

        try:
            retrieved_chunks = RetrievalService.retrieve_by_conversation(
                conversation=conversation,
                query_text=query,
                top_k=top_k,
            )
            logger.info(f'Retrieved {len(retrieved_chunks)} relevant chunks')
        except Exception as exc:
            logger.error(f'Retrieval failed: {exc}')
            raise

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
            logger.info(f'Generated LLM response using {response.model_used}')
        except Exception as exc:
            logger.error(f'LLM generation failed: {exc}')
            raise

        latency_ms = int((timezone.now() - start_time).total_seconds() * 1000)

        if save_log:
            try:
                QueryLog.objects.create(
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
                logger.info(f'Logged query to QueryLog: {query[:50]}...')
            except Exception as exc:
                logger.error(f'Failed to log query: {exc}')

        return response
