from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ai_engine.models import DocumentChunk
from ai_engine.services.embedding import EmbeddingService

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
    min_similarity: float = 0.0,
) -> list[DocumentChunk]:
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
        user: If provided, restrict the search to chunks owned by this user.
        min_similarity: Drop results whose cosine similarity is strictly less
            than this threshold (default 0.0 keeps everything).

    Returns:
        A list of ``DocumentChunk`` instances ordered by similarity DESC.
        Each instance has a ``relevance_score`` attribute monkey-patched onto
        it so callers (e.g. the QA layer) can inspect the score without a
        second pass.
    """
    started_at = time.perf_counter()

    if not query or not query.strip():
        logger.info('semantic_search: empty query → returning no chunks')
        return []
    if top_k <= 0:
        return []

    try:
        query_embedding = EmbeddingService.generate_embedding(query)
    except Exception as exc:
        logger.error('semantic_search: failed to embed query: %s', exc)
        return []

    query_embedding = np.asarray(query_embedding, dtype=np.float32)
    query_dim = int(query_embedding.shape[0])

    queryset = (
        DocumentChunk.objects
        .filter(embedding__isnull=False)
        .select_related('document')
        .only('id', 'content', 'embedding', 'document_id', 'document_owner_id', 'document__title')
    )
    if user is not None:
        queryset = queryset.filter(document_owner=user)

    chunks: list[DocumentChunk] = list(queryset)
    if not chunks:
        logger.info('semantic_search: no candidate chunks (user=%s)', getattr(user, 'pk', None))
        return []

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
        return []

    matrix = np.stack(valid_vectors)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    query_norm = float(np.linalg.norm(query_embedding))
    denom = matrix_norms * query_norm
    similarities = np.zeros(matrix.shape[0], dtype=np.float32)
    nonzero = denom > 0
    similarities[nonzero] = (matrix[nonzero] @ query_embedding) / denom[nonzero]

    k = min(top_k, similarities.shape[0])
    partial = np.argpartition(-similarities, k - 1)[:k]
    ordered_top = partial[np.argsort(-similarities[partial])]

    results: list[DocumentChunk] = []
    for idx in ordered_top:
        score = float(similarities[idx])
        if score < min_similarity:
            continue
        chunk = valid_chunks[idx]
        chunk.relevance_score = score
        results.append(chunk)

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

    return results


def semantic_search_scored(
    query: str,
    top_k: int = 5,
    *,
    user=None,
    min_similarity: float = 0.0,
) -> list[ScoredChunk]:
    """
    Variant of :func:`semantic_search` that returns ``ScoredChunk`` records.

    Use this when callers need the score in a structured way (e.g. analytics,
    serializers) without relying on the ``relevance_score`` attribute attached
    to model instances by :func:`semantic_search`.
    """
    chunks = semantic_search(query, top_k=top_k, user=user, min_similarity=min_similarity)
    return [ScoredChunk(chunk=c, score=getattr(c, 'relevance_score', 0.0)) for c in chunks]
