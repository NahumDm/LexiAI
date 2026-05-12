from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ai_engine.models import DocumentChunk, QueryLog
from ai_engine.services.llm import LLMError, generate_completion
from ai_engine.services.search import semantic_search

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a legal assistant.\n\n"
    "Answer the user's question using ONLY the provided context.\n\n"
    "Rules:\n"
    "- Do NOT use outside knowledge.\n"
    "- Cite sources using [Source N] markers that match the labels in the context.\n"
    "- If the answer is not in the context, say you don't know.\n"
    "- Be precise and formal."
)

DEFAULT_TOP_K = 5
DEFAULT_MIN_SIMILARITY = 0.0
MAX_CONTEXT_CHARS = 12_000  # ~3K tokens; conservative ceiling for short-context models.

FALLBACK_NO_CHUNKS_ANSWER = (
    'I could not find any indexed passages relevant to that question. '
    'Try rephrasing, or ingest additional documents before asking again.'
)


def _build_context(chunks: list[DocumentChunk], max_chars: int) -> tuple[str, list[DocumentChunk]]:
    """
    Render the retrieved chunks into a single ``[Source N]``-labelled context
    block, truncating once ``max_chars`` is reached.

    Returns the context string and the list of chunks actually used (so the
    caller can report only the sources that influenced the answer).
    """
    parts: list[str] = []
    used: list[DocumentChunk] = []
    total = 0
    for idx, chunk in enumerate(chunks, start=1):
        document_title = getattr(chunk.document, 'title', None) if chunk.document_id else None
        label = document_title or f'Document #{chunk.document_id}'
        segment = f'[Source {idx}: {label}]\n{chunk.content}'
        if total + len(segment) > max_chars and parts:
            break
        parts.append(segment)
        used.append(chunk)
        total += len(segment)
    return '\n\n'.join(parts), used


def _build_sources(chunks: list[DocumentChunk]) -> list[dict]:
    """JSON-safe source descriptors for the API response."""
    sources: list[dict] = []
    for idx, chunk in enumerate(chunks, start=1):
        document_title = getattr(chunk.document, 'title', None) if chunk.document_id else None
        sources.append({
            'source_number': idx,
            'chunk_id': int(chunk.id),
            'document_id': int(chunk.document_id),
            'document_title': document_title,
            'relevance': round(float(getattr(chunk, 'relevance_score', 0.0)), 4),
            'excerpt': chunk.content[:200],
        })
    return sources


def generate_answer(
    query: str,
    *,
    user=None,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    max_context_chars: int = MAX_CONTEXT_CHARS,
    save_log: bool = True,
) -> dict:
    """
    Run the full retrieval-augmented question-answering flow.

    Pipeline:
        1. Validate the query.
        2. ``semantic_search`` for the top-k most similar chunks (user-scoped
           when ``user`` is provided).
        3. Build a labelled ``[Source N]`` context block, capped at
           ``max_context_chars``.
        4. Call :func:`ai_engine.services.llm.generate_completion` with the
           context and a legal-assistant system prompt.
        5. Persist a :class:`QueryLog` row when ``user`` is provided.

    Returns:
        A dict with the shape::

            {
                "answer": str,
                "sources": list[dict],   # one entry per cited chunk
                "model_used": str,
                "retrieval_confidence": float,
                "latency_ms": int,
                "warnings": list[str],
                "query_log_id": int | None,
            }

    Edge cases:
        * Empty / whitespace-only query → 400-shaped response with empty answer.
        * No chunks retrieved → returns ``FALLBACK_NO_CHUNKS_ANSWER`` and
          ``sources=[]`` (no LLM call).
        * LLM provider failure → caught and surfaced via ``warnings``;
          a generic apology is returned so the API never 500s on a flaky LLM.
    """
    started_at = time.perf_counter()
    warnings: list[str] = []

    stripped = (query or '').strip()
    if not stripped:
        logger.info('generate_answer: empty query rejected user=%s', getattr(user, 'pk', None))
        return {
            'answer': '',
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': 0.0,
            'latency_ms': int((time.perf_counter() - started_at) * 1000),
            'warnings': ['Query was empty.'],
            'query_log_id': None,
        }

    retrieved = semantic_search(
        stripped,
        top_k=top_k,
        user=user,
        min_similarity=min_similarity,
    )
    logger.info(
        'generate_answer: retrieved=%s user=%s query_chars=%s',
        len(retrieved),
        getattr(user, 'pk', None),
        len(stripped),
    )

    if not retrieved:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        result = {
            'answer': FALLBACK_NO_CHUNKS_ANSWER,
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': 0.0,
            'latency_ms': latency_ms,
            'warnings': ['No relevant passages were retrieved for this query.'],
            'query_log_id': None,
        }
        if save_log and user is not None:
            result['query_log_id'] = _persist_query_log(
                user=user,
                query=stripped,
                retrieved_chunk_ids=[],
                answer=result['answer'],
                model_used=result['model_used'],
                retrieval_confidence=0.0,
                latency_ms=latency_ms,
            )
        return result

    context_text, used_chunks = _build_context(retrieved, max_chars=max_context_chars)
    if len(used_chunks) < len(retrieved):
        warnings.append(
            f'Context truncated to {len(used_chunks)} of {len(retrieved)} chunks '
            f'(max_context_chars={max_context_chars}).'
        )

    avg_confidence = sum(
        float(getattr(c, 'relevance_score', 0.0)) for c in used_chunks
    ) / max(len(used_chunks), 1)

    user_prompt = (
        f'Question:\n{stripped}\n\n'
        f'Context:\n{context_text}\n\n'
        f'Answer the question using ONLY the context above. Cite supporting passages with [Source N].'
    )

    model_used = 'unknown'
    try:
        from ai_engine.services.llm_client import get_llm_client

        model_used = getattr(get_llm_client(), 'model', 'stub')
        answer = generate_completion(user_prompt, system_prompt=SYSTEM_PROMPT)
    except LLMError as exc:
        logger.exception('generate_answer: LLM error: %s', exc)
        warnings.append(f'LLM provider error: {exc}')
        answer = (
            'I retrieved relevant passages but the language model is temporarily unavailable. '
            'Please retry in a moment.'
        )

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    sources = _build_sources(used_chunks)

    logger.info(
        'generate_answer: done user=%s chunks_used=%s avg_confidence=%.4f model=%s latency_ms=%s',
        getattr(user, 'pk', None),
        len(used_chunks),
        avg_confidence,
        model_used,
        latency_ms,
    )

    query_log_id: int | None = None
    if save_log and user is not None:
        query_log_id = _persist_query_log(
            user=user,
            query=stripped,
            retrieved_chunk_ids=[int(c.id) for c in used_chunks],
            answer=answer,
            model_used=str(model_used),
            retrieval_confidence=float(avg_confidence),
            latency_ms=latency_ms,
        )

    return {
        'answer': answer,
        'sources': sources,
        'model_used': str(model_used),
        'retrieval_confidence': float(avg_confidence),
        'latency_ms': latency_ms,
        'warnings': warnings,
        'query_log_id': query_log_id,
    }


def _persist_query_log(
    *,
    user,
    query: str,
    retrieved_chunk_ids: list[int],
    answer: str,
    model_used: str,
    retrieval_confidence: float,
    latency_ms: int,
) -> int | None:
    """Persist a ``QueryLog`` row; swallow & log failures so QA is never blocked."""
    try:
        log = QueryLog.objects.create(
            user=user,
            conversation=None,
            query_text=query,
            query_embedding=None,
            retrieved_chunk_ids=retrieved_chunk_ids,
            llm_response=answer,
            llm_model=model_used,
            retrieval_confidence=retrieval_confidence,
            latency_ms=latency_ms,
            token_usage={},
        )
        return int(log.id)
    except Exception as exc:
        logger.error('generate_answer: failed to persist QueryLog: %s', exc)
        return None
