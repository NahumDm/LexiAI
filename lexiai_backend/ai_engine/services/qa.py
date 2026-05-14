from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from django.conf import settings

from ai_engine.confidence import (
    LOW_EVIDENCE_MAX_SIMILARITY,
    MIN_ANSWER_MAX_SIMILARITY,
    calculate_confidence,
    confidence_percent_to_unit,
    max_bracket_citation_index,
)
from ai_engine.models import DocumentChunk, QueryLog
from ai_engine.query_classification import (
    ASK_GREETING_RESPONSE,
    ASK_OUT_OF_SCOPE_RESPONSE,
    classify_intent,
)
from ai_engine.services.llm import LLMError, generate_completion
from ai_engine.services.search import semantic_search
from ai_engine.strict_grounding import (
    STRICT_LEGAL_SYSTEM_PROMPT,
    STRICT_NO_RETRIEVAL_ANSWER,
    answer_signals_insufficient_documents,
    cap_confidence_when_absence_indicated,
    format_source_citation_label,
    legal_response_has_required_structure,
)

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = STRICT_LEGAL_SYSTEM_PROMPT

_QA_LOW_EVIDENCE_NOTE = '⚠️ Note: Limited supporting evidence found in documents.'

DEFAULT_TOP_K = int(getattr(settings, 'RAG_DEFAULT_TOP_K', 3))
DEFAULT_MIN_SIMILARITY = float(getattr(settings, 'RAG_MIN_SIMILARITY', 0.2))
MAX_CONTEXT_CHARS = 10_000


def _confidence_percent(confidence: float) -> float:
    """Human-readable percent (0–100) from a 0–1 routing or cosine score."""
    return round(float(confidence) * 100.0, 1)


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
    Render the retrieved chunks into a single bracket-numbered context block,
    truncating once ``max_chars`` is reached.

    Returns the context string and the list of chunks actually used (so the
    caller can report only the sources that influenced the answer).
    """
    parts: list[str] = []
    used: list[DocumentChunk] = []
    total = 0
    for idx, chunk in enumerate(chunks, start=1):
        document_title = getattr(chunk.document, 'title', None) if chunk.document_id else None
        md = getattr(chunk, 'metadata', None)
        header = format_source_citation_label(idx, document_title, md)
        segment = f'{header}\n{chunk.content}'
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
        citation_label = format_source_citation_label(idx, document_title, getattr(chunk, 'metadata', None))
        sources.append({
            'source_number': idx,
            'chunk_id': int(chunk.id),
            'document_id': int(chunk.document_id),
            'document_title': document_title,
            'citation_label': citation_label,
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

    ``retrieval_confidence`` is the mean cosine similarity of chunks used in context.
    ``confidence`` is a 0–1 blend of similarity and passage coverage (see
    :func:`ai_engine.confidence.calculate_confidence`). ``confidence_percent`` is that
    blend as a percent with one decimal. Greeting / out-of-scope use ``1.0``; strict
    no-retrieval uses ``0.0``.
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
            'generate_answer: zero chunks above threshold — strict refusal user=%s',
            getattr(user, 'pk', None),
        )
        warnings.append('No indexed passages met the similarity threshold.')
        query_log_id: int | None = None
        if save_log and user is not None:
            query_log_id = _persist_query_log(
                user=user,
                query=stripped,
                retrieved_chunk_ids=[],
                answer=STRICT_NO_RETRIEVAL_ANSWER,
                model_used='n/a',
                retrieval_confidence=0.0,
                latency_ms=latency_ms,
            )
        return {
            'answer': STRICT_NO_RETRIEVAL_ANSWER,
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': 0.0,
            'confidence': 0.0,
            'confidence_percent': 0.0,
            'latency_ms': latency_ms,
            'warnings': warnings,
            'query_log_id': query_log_id,
        }

    filtered = [
        c for c in retrieved if float(getattr(c, 'relevance_score', 0.0)) >= MIN_ANSWER_MAX_SIMILARITY
    ]
    retrieved_for_llm = filtered[:eff_top_k]
    if not retrieved_for_llm:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info('generate_answer: no chunks at or above quality similarity — strict refusal')
        query_log_id: int | None = None
        if save_log and user is not None:
            query_log_id = _persist_query_log(
                user=user,
                query=stripped,
                retrieved_chunk_ids=[],
                answer=STRICT_NO_RETRIEVAL_ANSWER,
                model_used='n/a',
                retrieval_confidence=0.0,
                latency_ms=latency_ms,
            )
        return {
            'answer': STRICT_NO_RETRIEVAL_ANSWER,
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': 0.0,
            'confidence': 0.0,
            'confidence_percent': 0.0,
            'latency_ms': latency_ms,
            'warnings': warnings,
            'query_log_id': query_log_id,
        }

    context_text, used_chunks = _build_context(retrieved_for_llm, max_chars=max_context_chars)
    if not used_chunks:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info('generate_answer: context build yielded zero usable chunks — strict refusal')
        warnings.append('Context window could not fit retrieved passages; LLM was not called.')
        query_log_id: int | None = None
        if save_log and user is not None:
            query_log_id = _persist_query_log(
                user=user,
                query=stripped,
                retrieved_chunk_ids=[],
                answer=STRICT_NO_RETRIEVAL_ANSWER,
                model_used='n/a',
                retrieval_confidence=0.0,
                latency_ms=latency_ms,
            )
        return {
            'answer': STRICT_NO_RETRIEVAL_ANSWER,
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': 0.0,
            'confidence': 0.0,
            'confidence_percent': 0.0,
            'latency_ms': latency_ms,
            'warnings': warnings,
            'query_log_id': query_log_id,
        }

    if len(used_chunks) < len(retrieved_for_llm):
        warnings.append(
            f'Context truncated to {len(used_chunks)} of {len(retrieved_for_llm)} chunks '
            f'(max_context_chars={max_context_chars}).'
        )

    similarities = [float(getattr(c, 'relevance_score', 0.0)) for c in used_chunks]
    avg_confidence = sum(similarities) / max(len(similarities), 1)
    max_confidence = max(similarities)

    if max_confidence < MIN_ANSWER_MAX_SIMILARITY:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            'generate_answer: max_similarity below quality gate — strict refusal (no LLM) max_sim=%.4f',
            max_confidence,
        )
        query_log_id: int | None = None
        if save_log and user is not None:
            query_log_id = _persist_query_log(
                user=user,
                query=stripped,
                retrieved_chunk_ids=[int(c.id) for c in used_chunks],
                answer=STRICT_NO_RETRIEVAL_ANSWER,
                model_used='n/a',
                retrieval_confidence=float(avg_confidence),
                latency_ms=latency_ms,
            )
        logger.info(
            '[QA_FINAL_CHECK] retrieved_chunks=%s max_similarity=%.4f confidence=%.4f refused=True',
            [int(c.id) for c in used_chunks],
            max_confidence,
            0.0,
        )
        return {
            'answer': STRICT_NO_RETRIEVAL_ANSWER,
            'sources': [],
            'model_used': 'n/a',
            'retrieval_confidence': float(avg_confidence),
            'confidence': 0.0,
            'confidence_percent': 0.0,
            'latency_ms': latency_ms,
            'warnings': warnings,
            'query_log_id': query_log_id,
        }

    user_prompt = (
        f'Question:\n{stripped}\n\n'
        f'Context:\n{context_text}\n\n'
        'Answer using ONLY the context above. Your reply MUST include exactly these headings '
        '(with colons): Answer:, Legal Basis:, Explanation:, Sources:\n'
        'Only cite the provided sources: valid tags are [1] through [N] where N is the number of excerpt '
        'blocks above. Do not invent or exceed them.\n'
        'Under Legal Basis: list ONLY provisions that directly answer the question—do not add adjacent '
        'or related articles unless the question explicitly asks for them.\n'
        "If you cannot answer from this context alone, reply with ONLY this exact line: I don't know.\n"
        'Otherwise cite every factual claim using [n] tags matching the bracketed heading before each passage.'
    )

    model_used = 'unknown'
    llm_failed = False
    try:
        from ai_engine.services.llm_client import get_llm_client

        model_used = getattr(get_llm_client(), 'model', 'stub')
        answer = generate_completion(user_prompt, system_prompt=SYSTEM_PROMPT)
    except LLMError as exc:
        logger.exception('generate_answer: LLM error: %s', exc)
        warnings.append(f'LLM provider error: {exc}')
        llm_failed = True
        answer = (
            'I retrieved relevant passages but the language model is temporarily unavailable. '
            'Please retry in a moment.'
        )

    sources = _build_sources(used_chunks)
    sources = sources[: len(used_chunks)]

    if llm_failed:
        confidence_pct = 0.0
        confidence_unit = 0.0
    else:
        raw_answer = answer
        n = len(used_chunks)
        citation_ok = max_bracket_citation_index(raw_answer) <= n
        format_ok = legal_response_has_required_structure(raw_answer) and citation_ok
        insufficient = answer_signals_insufficient_documents(raw_answer)
        if not format_ok:
            if not citation_ok:
                logger.warning(
                    'generate_answer: citation index exceeds %s excerpt(s) (max seen=%s)',
                    n,
                    max_bracket_citation_index(raw_answer),
                )
            answer = STRICT_NO_RETRIEVAL_ANSWER
            sources = []
            confidence_pct = 0.0
            confidence_unit = 0.0
        elif insufficient:
            confidence_pct = 0.0
            confidence_unit = 0.0
        else:
            confidence_pct = calculate_confidence(similarities, len(used_chunks))
            confidence_unit = confidence_percent_to_unit(confidence_pct)

        if confidence_unit > 0.0:
            confidence_unit = cap_confidence_when_absence_indicated(confidence_unit, raw_answer)
            confidence_pct = round(confidence_unit * 100, 1)

        if (
            format_ok
            and not insufficient
            and MIN_ANSWER_MAX_SIMILARITY <= max_confidence < LOW_EVIDENCE_MAX_SIMILARITY
        ):
            if _QA_LOW_EVIDENCE_NOTE not in warnings:
                warnings.append(_QA_LOW_EVIDENCE_NOTE)
            note_block = f'\n\n{_QA_LOW_EVIDENCE_NOTE}'
            body = (answer or '').rstrip()
            if _QA_LOW_EVIDENCE_NOTE not in body:
                answer = body + note_block

    latency_ms = int((time.perf_counter() - started_at) * 1000)

    refused = (answer or '').strip() == STRICT_NO_RETRIEVAL_ANSWER
    logger.info(
        '[QA_FINAL_CHECK] retrieved_chunks=%s max_similarity=%.4f confidence=%.4f refused=%s',
        [int(c.id) for c in used_chunks],
        max_confidence,
        float(confidence_unit),
        refused,
    )

    logger.info(
        'generate_answer: done user=%s chunks_used=%s avg_sim=%.4f max_sim=%.4f conf_pct=%s model=%s latency_ms=%s',
        getattr(user, 'pk', None),
        len(used_chunks),
        avg_confidence,
        max_confidence,
        confidence_pct,
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
        'confidence': float(confidence_unit),
        'confidence_percent': float(confidence_pct),
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
