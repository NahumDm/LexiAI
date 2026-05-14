from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from django.conf import settings

from ai_engine.models import DocumentChunk
from ai_engine.services.embedding import EmbeddingService
from ai_engine.services.retrieval import chunk_knowledge_source, user_visible_chunk_queryset

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoredChunk:
    """A chunk paired with its cosine-similarity score against a query."""
    chunk: DocumentChunk
    score: float


def semantic_search(
    query: str,
    top_k: int = 5,
    *,
    user=None,
    min_similarity: float | None = None,
) -> tuple[list[DocumentChunk], float]:
    """
    Return the ``top_k`` most relevant ``DocumentChunk`` rows for ``query``.

    The query is embedded with the same ``EmbeddingService`` used to embed the
    chunks at ingestion time. Cosine similarity is computed in a single
    vectorized numpy pass; top-k selection uses ``np.argpartition`` to avoid
    a full sort over every chunk.

    Why we materialize embeddings in Python:
    - ``DocumentChunk.embedding`` is a ``BinaryField`` (no pgvector extension is
      installed in this database). Without a vector type or HNSW/ivfflat index,
      similarity must be computed in application code.
    - This function therefore loads only the columns it needs (``id``,
      ``content``, ``embedding``, document title via ``select_related``) so
      Django does not pull large unrelated columns. For large corpora, the
      recommended next step is to add ``pgvector`` and switch this function to
      ``DocumentChunk.objects.order_by(L2Distance('embedding', q_emb))[:top_k]``.

    Args:
        query: User question; must be non-empty after ``strip``.
        top_k: Maximum number of chunks to return (clipped to corpus size).
        user: Authenticated user; search includes staff-owned (global) documents and this user's own documents.
        min_similarity: Minimum cosine similarity (0–1). Values below
            ``settings.RAG_MIN_SIMILARITY`` are never used; the effective floor
            is ``max(RAG_MIN_SIMILARITY, min_similarity or RAG_MIN_SIMILARITY)``.

    Returns:
        ``(chunks, max_similarity)`` where ``chunks`` are ordered by similarity
        DESC (each has ``relevance_score``). ``max_similarity`` is the highest
        cosine among **returned** rows (``0.0`` when the list is empty).
    """
    started_at = time.perf_counter()

    if not query or not query.strip():
        logger.info('semantic_search: empty query → returning no chunks')
        return [], 0.0
    if top_k <= 0:
        return [], 0.0
    if user is None:
        logger.info('semantic_search: user is None → empty corpus')
        return [], 0.0

    floor = float(getattr(settings, 'RAG_MIN_SIMILARITY', 0.2))
    if min_similarity is None:
        effective_min = floor
    else:
        effective_min = max(floor, float(min_similarity))

    try:
        query_embedding = EmbeddingService.generate_embedding(query)
    except Exception as exc:
        logger.error('semantic_search: failed to embed query: %s', exc)
        return [], 0.0

    query_embedding = np.asarray(query_embedding, dtype=np.float32)
    query_dim = int(query_embedding.shape[0])

    queryset = (
        user_visible_chunk_queryset(user)
        .filter(embedding__isnull=False)
        .select_related('document', 'document__owner')
        .only(
            'id',
            'content',
            'embedding',
            'document_id',
            'document_owner_id',
            'document__title',
            'document__owner_id',
            'document__owner__is_staff',
        )
    )

    chunks: list[DocumentChunk] = list(queryset)
    if not chunks:
        logger.info('semantic_search: no candidate chunks (user=%s)', getattr(user, 'pk', None))
        return [], 0.0

    n_admin = sum(1 for c in chunks if getattr(c.document.owner, 'is_staff', False))
    n_user_owned = sum(1 for c in chunks if c.document.owner_id == user.pk)
    logger.info(
        '[RETRIEVAL] scope=global+user admin_chunks=%s user_owned_chunks=%s total=%s',
        n_admin,
        n_user_owned,
        len(chunks),
    )

    valid_chunks: list[DocumentChunk] = []
    valid_vectors: list[np.ndarray] = []
    skipped_dim_mismatch = 0
    for chunk in chunks:
        try:
            vec = np.frombuffer(chunk.embedding, dtype=np.float32)
        except Exception as exc:
            logger.warning('semantic_search: chunk %s unreadable embedding: %s', chunk.id, exc)
            continue
        if vec.shape[0] != query_dim:
            skipped_dim_mismatch += 1
            continue
        valid_chunks.append(chunk)
        valid_vectors.append(vec)

    if not valid_chunks:
        logger.warning(
            'semantic_search: 0 usable chunks (query_dim=%s skipped_dim_mismatch=%s)',
            query_dim,
            skipped_dim_mismatch,
        )
        return [], 0.0

    matrix = np.stack(valid_vectors)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    query_norm = float(np.linalg.norm(query_embedding))
    denom = matrix_norms * query_norm
    similarities = np.zeros(matrix.shape[0], dtype=np.float32)
    nonzero = denom > 0
    similarities[nonzero] = (matrix[nonzero] @ query_embedding) / denom[nonzero]

    n = int(similarities.shape[0])
    sim_np = np.asarray(similarities, dtype=np.float64)
    max_global = float(np.max(sim_np)) if n > 0 else 0.0
    top5 = np.sort(sim_np)[::-1][: min(5, n)].tolist() if n > 0 else []
    logger.info(
        'semantic_search: debug top_similarities_global=%s max_similarity_global=%.4f eff_min=%s '
        'candidates=%s user=%s',
        [round(float(x), 4) for x in top5],
        max_global,
        effective_min,
        n,
        getattr(user, 'pk', None),
    )

    passing_indices = [i for i in range(n) if float(similarities[i]) >= effective_min]
    if not passing_indices:
        logger.info(
            'semantic_search: no chunks >= min_similarity=%s (candidates=%s user=%s)',
            effective_min,
            n,
            getattr(user, 'pk', None),
        )
        return [], 0.0

    passing_indices.sort(key=lambda i: float(similarities[i]), reverse=True)
    take = min(top_k, len(passing_indices))
    ordered_top = passing_indices[:take]

    results: list[DocumentChunk] = []
    for idx in ordered_top:
        score = float(similarities[idx])
        chunk = valid_chunks[idx]
        chunk.relevance_score = score
        results.append(chunk)

    n_hit_admin = sum(1 for c in results if chunk_knowledge_source(c) == 'admin')
    n_hit_user = sum(1 for c in results if chunk_knowledge_source(c) == 'user')
    logger.info(
        '[RETRIEVAL] final_retrieved=%s admin_hits=%s user_hits=%s top_k=%s',
        len(results),
        n_hit_admin,
        n_hit_user,
        top_k,
    )

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        'semantic_search: query_chars=%s candidates=%s usable=%s returned=%s '
        'top_score=%.4f elapsed_ms=%s user=%s',
        len(query),
        len(chunks),
        len(valid_chunks),
        len(results),
        results[0].relevance_score if results else 0.0,
        elapsed_ms,
        getattr(user, 'pk', None),
    )

    max_score = float(similarities[ordered_top[0]]) if ordered_top else 0.0
    return results, max_score


def semantic_search_scored(
    query: str,
    top_k: int = 5,
    *,
    user=None,
    min_similarity: float | None = None,
) -> list[ScoredChunk]:
    """
    Variant of :func:`semantic_search` that returns ``ScoredChunk`` records.

    Use this when callers need the score in a structured way (e.g. analytics,
    serializers) without relying on the ``relevance_score`` attribute attached
    to model instances by :func:`semantic_search`.
    """
    chunks, _max_sim = semantic_search(query, top_k=top_k, user=user, min_similarity=min_similarity)
    return [ScoredChunk(chunk=c, score=getattr(c, 'relevance_score', 0.0)) for c in chunks]
