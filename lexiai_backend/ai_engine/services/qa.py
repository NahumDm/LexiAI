from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from django.conf import settings

from ai_engine.models import DocumentChunk, QueryLog
from ai_engine.query_classification import (
    ASK_GREETING_RESPONSE,
    ASK_OUT_OF_SCOPE_RESPONSE,
    LEGAL_NO_CONTEXT_RESPONSE,
    classify_intent,
)
from ai_engine.services.llm import LLMError, generate_completion
from ai_engine.services.search import semantic_search
from ai_engine.strict_grounding import (
    GENERAL_KNOWLEDGE_FALLBACK_SYSTEM_PROMPT,
    STRICT_LEGAL_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = STRICT_LEGAL_SYSTEM_PROMPT

DEFAULT_TOP_K = int(getattr(settings, 'RAG_DEFAULT_TOP_K', 3))
DEFAULT_MIN_SIMILARITY = float(getattr(settings, 'RAG_MIN_SIMILARITY', 0.2))
MAX_CONTEXT_CHARS = 10_000


def _confidence_percent(confidence: float) -> float:
	"""Human-readable percent (0–100) from cosine or routing score in ``[0, 1]``."""
	return round(float(confidence) * 100.0, 2)


def _deterministic_response(
    *,
    answer: str,
    confidence: float,
    latency_ms: int,
    save_log: bool,
    user,
    stripped: str,
    warnings: list[str],
    model_used: str = 'n/a',
) -> dict:
    """Build ask-API dict without invoking the LLM."""
    c = float(confidence)
    result: dict = {
        'answer': answer,
        'sources': [],
        'model_used': model_used,
        'retrieval_confidence': c,
        'confidence': c,
        'confidence_percent': _confidence_percent(c),
        'latency_ms': latency_ms,
        'warnings': warnings,
        'query_log_id': None,
    }
    if save_log and user is not None:
        result['query_log_id'] = _persist_query_log(
            user=user,
            query=stripped,
            retrieved_chunk_ids=[],
            answer=answer,
            model_used=model_used,
            retrieval_confidence=float(confidence),
            latency_ms=latency_ms,
        )
    return result


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
            'source': 'admin'
            if chunk.document_id
            and getattr(getattr(chunk, 'document', None), 'owner', None)
            and getattr(chunk.document.owner, 'is_staff', False)
            else 'user',
        })
    return sources


def generate_answer(
    query: str,
    *,
    user=None,
    top_k: int | None = None,
    min_similarity: float | None = None,
    max_context_chars: int = MAX_CONTEXT_CHARS,
    save_log: bool = True,
) -> dict:
    """
    Intent is classified before retrieval (greeting / out-of-scope skip search).

    Legal or unknown queries run ``semantic_search``; strict RAG when chunks qualify.

    ``confidence`` is ``1.0`` for greeting / out-of-scope short-circuits, ``0.0`` when
    nothing qualifies, otherwise the **maximum** cosine among chunks used for the
    LLM (``retrieval_confidence`` stays the **mean** for analytics). ``confidence_percent``
    is ``round(confidence * 100, 2)``.
    """
    started_at = time.perf_counter()
    warnings: list[str] = []

    eff_top_k = int(getattr(settings, 'RAG_DEFAULT_TOP_K', 3)) if top_k is None else int(top_k)
    floor = float(getattr(settings, 'RAG_MIN_SIMILARITY', 0.2))
    eff_min = max(floor, float(min_similarity)) if min_similarity is not None else floor

    stripped = (query or '').strip()
    if not stripped:
        logger.info('generate_answer: empty query rejected user=%s', getattr(user, 'pk', None))
        return {
            'answer': '',
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': 0.0,
            'confidence': 0.0,
            'confidence_percent': 0.0,
            'latency_ms': int((time.perf_counter() - started_at) * 1000),
            'warnings': ['Query was empty.'],
            'query_log_id': None,
        }

    intent = classify_intent(stripped)
    if intent == 'greeting':
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info('generate_answer: intent=greeting user=%s', getattr(user, 'pk', None))
        return _deterministic_response(
            answer=ASK_GREETING_RESPONSE,
            confidence=1.0,
            latency_ms=latency_ms,
            save_log=save_log,
            user=user,
            stripped=stripped,
            warnings=['Intent=greeting; retrieval skipped.'],
        )
    if intent == 'out_of_scope':
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info('generate_answer: intent=out_of_scope user=%s', getattr(user, 'pk', None))
        return _deterministic_response(
            answer=ASK_OUT_OF_SCOPE_RESPONSE,
            confidence=1.0,
            latency_ms=latency_ms,
            save_log=save_log,
            user=user,
            stripped=stripped,
            warnings=['Intent=out_of_scope; retrieval skipped.'],
        )

    retrieved, retrieval_max_score = semantic_search(
        stripped,
        top_k=eff_top_k,
        user=user,
        min_similarity=eff_min,
    )
    logger.info(
        'generate_answer: intent=%s retrieved=%s max_sim=%.4f user=%s query_chars=%s top_k=%s min_sim=%s',
        intent,
        len(retrieved),
        retrieval_max_score,
        getattr(user, 'pk', None),
        len(stripped),
        eff_top_k,
        eff_min,
    )

    if not retrieved:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            'generate_answer: zero chunks above threshold — LLM general-knowledge fallback user=%s',
            getattr(user, 'pk', None),
        )
        warnings.append('No indexed passages met the similarity threshold.')
        user_prompt = (
            'No relevant documents were found in the indexed library for this question. '
            'Answer based on general knowledge only; do not cite specific uploaded files.\n\n'
            f'Question:\n{stripped}'
        )
        model_used = 'unknown'
        try:
            from ai_engine.services.llm_client import get_llm_client

            model_used = getattr(get_llm_client(), 'model', 'stub')
            answer = generate_completion(
                user_prompt,
                system_prompt=GENERAL_KNOWLEDGE_FALLBACK_SYSTEM_PROMPT,
            )
        except LLMError as exc:
            logger.exception('generate_answer: LLM fallback error: %s', exc)
            warnings.append(f'LLM provider error: {exc}')
            answer = (
                'No indexed passages matched your question, and the language model is '
                'temporarily unavailable. Please retry in a moment.'
            )

        query_log_id: int | None = None
        if save_log and user is not None:
            query_log_id = _persist_query_log(
                user=user,
                query=stripped,
                retrieved_chunk_ids=[],
                answer=answer,
                model_used=str(model_used),
                retrieval_confidence=0.0,
                latency_ms=latency_ms,
            )

        return {
            'answer': answer,
            'sources': [],
            'model_used': str(model_used),
            'retrieval_confidence': 0.0,
            'confidence': 0.0,
            'confidence_percent': 0.0,
            'latency_ms': latency_ms,
            'warnings': warnings,
            'query_log_id': query_log_id,
        }

    context_text, used_chunks = _build_context(retrieved, max_chars=max_context_chars)
    if not used_chunks:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info('generate_answer: context build yielded zero chunks; no-context fallback')
        no_ctx_answer = (
            LEGAL_NO_CONTEXT_RESPONSE if intent == 'legal' else ASK_OUT_OF_SCOPE_RESPONSE
        )
        return _deterministic_response(
            answer=no_ctx_answer,
            confidence=0.0,
            latency_ms=latency_ms,
            save_log=save_log,
            user=user,
            stripped=stripped,
            warnings=['Context window could not fit retrieved passages; LLM was not called.'],
        )

    if len(used_chunks) < len(retrieved):
        warnings.append(
            f'Context truncated to {len(used_chunks)} of {len(retrieved)} chunks '
            f'(max_context_chars={max_context_chars}).'
        )

    avg_confidence = sum(
        float(getattr(c, 'relevance_score', 0.0)) for c in used_chunks
    ) / max(len(used_chunks), 1)
    max_confidence = max(float(getattr(c, 'relevance_score', 0.0)) for c in used_chunks)

    user_prompt = (
        f'Question:\n{stripped}\n\n'
        f'Context:\n{context_text}\n\n'
        'Answer using ONLY the context above. If you cannot answer from this context alone, '
        "respond EXACTLY with: I don't know.\n"
        'Otherwise cite every factual claim with [Source N] matching the context labels.'
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
        'generate_answer: done user=%s chunks_used=%s avg_sim=%.4f max_sim=%.4f model=%s latency_ms=%s',
        getattr(user, 'pk', None),
        len(used_chunks),
        avg_confidence,
        max_confidence,
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
        'confidence': float(max_confidence),
        'confidence_percent': _confidence_percent(max_confidence),
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
