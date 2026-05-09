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
		query_embedding: np.ndarray | None = None,
	) -> list[RetrievedChunk]:
		"""
		Find top-k most relevant chunks for a query.
		Can scope to a specific document or user's documents.
		"""
		try:
			q_emb = query_embedding
			if q_emb is None:
				q_emb = EmbeddingService.generate_embedding(query_text)
		except Exception as exc:
			logger.error(f'Failed to generate query embedding: {exc}')
			return []

		query_dim = int(q_emb.shape[0]) if hasattr(q_emb, 'shape') else len(q_emb)

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
				if not chunk.embedding:
					logger.debug('Skipping chunk %s: missing embedding bytes', chunk.id)
					continue
				chunk_embedding = EmbeddingService.bytes_to_embedding(chunk.embedding)
				if chunk_embedding.shape[0] != query_dim:
					logger.warning(
						'Skipping chunk %s: embedding dim %s != query dim %s',
						chunk.id,
						chunk_embedding.shape[0],
						query_dim,
					)
					continue
				similarity = EmbeddingService.cosine_similarity(q_emb, chunk_embedding)
				scored_chunks.append(RetrievedChunk(chunk=chunk, relevance_score=float(similarity)))
			except Exception as exc:
				logger.warning(f'Failed to score chunk {chunk.id}: {exc}')
				continue

		scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
		top = scored_chunks[:top_k]
		for rc in top:
			excerpt = rc.chunk.content[:120].replace('\n', ' ')
			logger.info(
				'Retrieval hit chunk_id=%s doc_id=%s score=%.4f excerpt=%r',
				rc.chunk.id,
				rc.chunk.document_id,
				rc.relevance_score,
				excerpt,
			)
		return top

	@staticmethod
	def retrieve_by_conversation(
		conversation,
		query_text: str,
		top_k: int = 5,
		query_embedding: np.ndarray | None = None,
	) -> list[RetrievedChunk]:
		"""
		Prefer chunks from the conversation's attached document; if none, search the owner's library.
		"""
		if conversation.document_id and conversation.document:
			logger.info(
				'Retrieval scope=document conversation_id=%s document_id=%s',
				conversation.id,
				conversation.document_id,
			)
			return RetrievalService.retrieve_relevant_chunks(
				query_text=query_text,
				document=conversation.document,
				top_k=top_k,
				query_embedding=query_embedding,
			)

		logger.info(
			'Retrieval fallback=user_chunks conversation_id=%s owner_id=%s (conversation.document is null)',
			conversation.id,
			getattr(conversation.owner, 'id', None),
		)
		return RetrievalService.retrieve_relevant_chunks(
			query_text=query_text,
			document=None,
			user=conversation.owner,
			top_k=top_k,
			query_embedding=query_embedding,
		)
