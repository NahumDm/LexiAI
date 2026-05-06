from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

import numpy as np

from ai_engine.models import DocumentChunk
from ai_engine.services.embedding import EmbeddingService

if TYPE_CHECKING:
	from documents.models import Document

logger = logging.getLogger(__name__)


class RetrievedChunk(NamedTuple):
	chunk: DocumentChunk
	relevance_score: float


class RetrievalService:
	"""
	Retrieves relevant document chunks using semantic similarity.
	Uses vector/cosine similarity for ranking.
	"""

	@staticmethod
	def retrieve_relevant_chunks(
		query_text: str,
		document: Document | None = None,
		user=None,
		top_k: int = 5,
	) -> list[RetrievedChunk]:
		"""
		Find top-k most relevant chunks for a query.
		Can scope to a specific document or user's documents.
		"""
		try:
			query_embedding = EmbeddingService.generate_embedding(query_text)
		except Exception as exc:
			logger.error(f'Failed to generate query embedding: {exc}')
			return []

		queryset = DocumentChunk.objects.select_related('document')

		if document:
			queryset = queryset.filter(document=document)
		elif user:
			queryset = queryset.filter(document_owner=user)
		else:
			return []

		chunks = list(queryset)
		if not chunks:
			logger.warning('No chunks found for search')
			return []

		scored_chunks = []
		for chunk in chunks:
			try:
				chunk_embedding = EmbeddingService.bytes_to_embedding(chunk.embedding)
				similarity = EmbeddingService.cosine_similarity(query_embedding, chunk_embedding)
				scored_chunks.append(RetrievedChunk(chunk=chunk, relevance_score=float(similarity)))
			except Exception as exc:
				logger.warning(f'Failed to score chunk {chunk.id}: {exc}')
				continue

		scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
		return scored_chunks[:top_k]

	@staticmethod
	def retrieve_by_conversation(
		conversation,
		query_text: str,
		top_k: int = 5,
	) -> list[RetrievedChunk]:
		"""
		Retrieve chunks scoped to a conversation's attached document.
		"""
		if not conversation.document:
			logger.warning(f'Conversation {conversation.id} has no document attached')
			return []

		return RetrievalService.retrieve_relevant_chunks(
			query_text=query_text,
			document=conversation.document,
			top_k=top_k,
		)
