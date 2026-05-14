from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from django.conf import settings
from django.db.models import Q

from ai_engine.models import DocumentChunk
from ai_engine.services.embedding import EmbeddingService

if TYPE_CHECKING:
	from documents.models import Document

logger = logging.getLogger(__name__)


def db_user_for_chunk_corpus(user):
	"""
	Return a real DB row for ``user`` so ``Q(document__owner=user)`` never binds a
	``SimpleLazyObject`` / anonymous placeholder (which can yield an empty corpus
	even when chunks exist).
	"""
	if user is None:
		return None
	pk = getattr(user, 'pk', None)
	if pk is None:
		logger.warning('[RETRIEVAL] db_user_for_chunk_corpus: missing pk user=%r', user)
		return None
	from django.contrib.auth import get_user_model

	User = get_user_model()
	try:
		return User.objects.only('pk', 'is_staff', 'email').get(pk=pk)
	except User.DoesNotExist:
		logger.warning('[RETRIEVAL] db_user_for_chunk_corpus: User pk=%s does not exist', pk)
		return None


class RetrievedChunk(NamedTuple):
	chunk: DocumentChunk
	relevance_score: float
	# ``admin`` = document owned by staff (global KB); ``user`` = personal library.
	source: str


def user_visible_chunk_queryset(user):
	"""Chunks readable for RAG: global staff-owned docs plus the user’s own documents."""
	if user is None:
		return DocumentChunk.objects.none()
	db = db_user_for_chunk_corpus(user)
	if db is None:
		return DocumentChunk.objects.none()
	return DocumentChunk.objects.filter(
		Q(document__owner__is_staff=True) | Q(document__owner=db),
	)


def chunk_knowledge_source(chunk: DocumentChunk) -> str:
	owner = getattr(getattr(chunk, 'document', None), 'owner', None)
	if owner is not None and getattr(owner, 'is_staff', False):
		return 'admin'
	return 'user'


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
		min_similarity: float | None = None,
		*,
		accessing_user=None,
	) -> list[RetrievedChunk]:
		"""
		Find top-k most relevant chunks for a query.

		- If ``document`` is set: search only that document (callers must attach a
		  document the user may access). When ``accessing_user`` is set, the
		  document must be owned by that user or by a staff user (global KB).
		- Else if ``user`` is set: staff-owned documents (global) plus that user’s
		  own documents (private), ranked by cosine similarity only.
		- Else: no corpus (returns empty list).

		Only chunks with cosine similarity >= effective minimum (at least
		``settings.RAG_MIN_SIMILARITY``) are returned; ``top_k`` applies after filtering.
		"""
		floor = float(getattr(settings, 'RAG_MIN_SIMILARITY', 0.2))
		if min_similarity is None:
			effective_min = floor
		else:
			effective_min = max(floor, float(min_similarity))

		try:
			q_emb = query_embedding
			if q_emb is None:
				q_emb = EmbeddingService.generate_embedding(query_text)
		except Exception as exc:
			logger.error(f'Failed to generate query embedding: {exc}')
			return []

		query_dim = int(q_emb.shape[0]) if hasattr(q_emb, 'shape') else len(q_emb)

		db_user = None
		if document:
			scope_label = 'document'
			if accessing_user is not None:
				db_acc = db_user_for_chunk_corpus(accessing_user)
				if db_acc is None:
					logger.warning('[RETRIEVAL] scope=document aborted: accessing_user unresolved')
					return []
				queryset = user_visible_chunk_queryset(db_acc).filter(document=document).select_related(
					'document',
					'document__owner',
				)
			else:
				queryset = DocumentChunk.objects.select_related('document', 'document__owner').filter(
					document=document,
				)
		elif user:
			db_user = db_user_for_chunk_corpus(user)
			if db_user is None:
				logger.warning('[RETRIEVAL] scope=global+user aborted: user unresolved')
				return []
			queryset = user_visible_chunk_queryset(db_user).select_related('document', 'document__owner')
			scope_label = 'global+user'
		else:
			return []

		chunks = list(queryset)
		if not chunks:
			logger.warning('[RETRIEVAL] scope=%s no_chunks_in_db', scope_label)
			return []

		if scope_label == 'global+user':
			n_admin = sum(1 for c in chunks if getattr(c.document.owner, 'is_staff', False))
			n_user_owned = sum(1 for c in chunks if c.document.owner_id == db_user.pk)
			logger.info(
				'[RETRIEVAL] scope=%s admin_chunks=%s user_owned_chunks=%s total=%s',
				scope_label,
				n_admin,
				n_user_owned,
				len(chunks),
			)
		else:
			logger.info(
				'[RETRIEVAL] scope=%s document_id=%s total=%s',
				scope_label,
				getattr(document, 'pk', None),
				len(chunks),
			)

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
				src = chunk_knowledge_source(chunk)
				scored_chunks.append(
					RetrievedChunk(chunk=chunk, relevance_score=float(similarity), source=src),
				)
			except Exception as exc:
				logger.warning(f'Failed to score chunk {chunk.id}: {exc}')
				continue

		filtered = [rc for rc in scored_chunks if rc.relevance_score >= effective_min]
		if not filtered:
			logger.info(
				'retrieve_relevant_chunks: no chunks >= min_similarity=%s (scored=%s)',
				effective_min,
				len(scored_chunks),
			)
			return []

		filtered.sort(key=lambda x: x.relevance_score, reverse=True)
		top = filtered[:top_k]
		n_hit_admin = sum(1 for rc in top if rc.source == 'admin')
		n_hit_user = sum(1 for rc in top if rc.source == 'user')
		logger.info(
			'[RETRIEVAL] final_retrieved=%s admin_hits=%s user_hits=%s top_k=%s',
			len(top),
			n_hit_admin,
			n_hit_user,
			top_k,
		)
		for rc in top:
			excerpt = rc.chunk.content[:120].replace('\n', ' ')
			logger.info(
				'Retrieval hit chunk_id=%s doc_id=%s source=%s score=%.4f excerpt=%r',
				rc.chunk.id,
				rc.chunk.document_id,
				rc.source,
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
		min_similarity: float | None = None,
		*,
		retrieval_user=None,
	) -> list[RetrievedChunk]:
		"""
		Prefer chunks from the conversation's attached document.

		If there is no attachment, the attached document has no indexed chunks, or
		document-scoped retrieval yields no qualifying passages, fall back to
		global staff documents plus the conversation owner's documents.
		"""
		owner_raw = retrieval_user if retrieval_user is not None else conversation.owner
		owner = db_user_for_chunk_corpus(owner_raw)
		if owner is None:
			logger.error(
				'[RETRIEVAL] retrieve_by_conversation: unresolved corpus user raw_pk=%s '
				'conversation_id=%s',
				getattr(owner_raw, 'pk', None),
				conversation.id,
			)
			return []
		owner_id = owner.pk

		doc = conversation.document if getattr(conversation, 'document_id', None) else None
		if doc is not None and doc.chunks.exists():
			logger.info(
				'Retrieval scope=document conversation_id=%s document_id=%s',
				conversation.id,
				doc.pk,
			)
			doc_hits = RetrievalService.retrieve_relevant_chunks(
				query_text=query_text,
				document=doc,
				top_k=top_k,
				query_embedding=query_embedding,
				min_similarity=min_similarity,
				accessing_user=owner,
			)
			if doc_hits:
				return doc_hits
			logger.info(
				'Retrieval document scope returned 0 qualifying chunks; '
				'fallback=global+user conversation_id=%s owner_id=%s document_id=%s',
				conversation.id,
				owner_id,
				doc.pk,
			)
		elif doc is not None:
			logger.info(
				'Retrieval attached document has no indexed chunks; '
				'fallback=global+user conversation_id=%s owner_id=%s document_id=%s',
				conversation.id,
				owner_id,
				doc.pk,
			)
		else:
			logger.info(
				'Retrieval no attached document; scope=global+user conversation_id=%s owner_id=%s',
				conversation.id,
				owner_id,
			)

		return RetrievalService.retrieve_relevant_chunks(
			query_text=query_text,
			document=None,
			user=owner,
			top_k=top_k,
			query_embedding=query_embedding,
			min_similarity=min_similarity,
		)
