from __future__ import annotations

import logging
import time

from ai_engine.services.llm_client import (
    LLMClient,
    LLMError,
    MistralLLMClient,
    StubLLMClient,
    get_llm_client,
)

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = 'You are a helpful assistant.'

# Re-exported for backward compatibility. ``LLMError`` is canonically defined
# in ``ai_engine.services.llm_client`` so both modules can raise the same type
# without a circular import. Callers may continue to import it from here.
__all__ = ['LLMError', 'generate_completion']


def generate_completion(
    prompt: str,
    *,
    system_prompt: str | None = None,
    client: LLMClient | None = None,
) -> str:
    """
    Generate a single text completion for ``prompt``.

    The backend is resolved at runtime from Django settings
    (``AI_LLM_BACKEND`` / ``MISTRAL_API_KEY`` / ``MISTRAL_BASE_URL``) via
    :func:`ai_engine.services.llm_client.get_llm_client`, so the same call site
    works against Mistral cloud, a local vLLM/Ollama OpenAI server, or the
    in-process stub. Pass an explicit ``client`` to override (useful in tests).

    Args:
        prompt: User-facing prompt.
        system_prompt: Optional system instruction. Defaults to a generic
            helpful-assistant message.
        client: Optional ``LLMClient`` to use instead of the settings-derived
            one. Must implement either the underlying ``_chat`` method
            (MistralLLMClient) or be a ``StubLLMClient``.

    Returns:
        The model's reply as a stripped string.

    Raises:
        LLMError: when the configured provider raises during generation, when
            the prompt is empty, or when the resolved client type is unknown.
    """
    if not prompt or not prompt.strip():
        raise LLMError('Refusing to call LLM with empty prompt.')

    effective_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    client = client or get_llm_client()

    if isinstance(client, MistralLLMClient):
        logger.info(
            'LLM call: model=%s prompt_chars=%s temperature=%s max_tokens=%s',
            client.model,
            len(prompt),
            client.temperature,
            client.max_tokens,
        )
        started_at = time.perf_counter()
        try:
            text, tokens = client._chat(effective_system_prompt, prompt)
        except LLMError as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            logger.error('LLM fail: model=%s latency_ms=%s err=%s', client.model, latency_ms, exc)
            raise
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception('LLM fail: model=%s latency_ms=%s err=%s', client.model, latency_ms, exc)
            raise LLMError(f'LLM request failed: {exc}') from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            'LLM ok: model=%s latency_ms=%s answer_chars=%s tokens=%s',
            client.model,
            latency_ms,
            len(text),
            tokens.get('total', 0),
        )
        return text

    if isinstance(client, StubLLMClient):
        started_at = time.perf_counter()
        logger.warning('Using StubLLMClient — no API key configured')
        logger.info('LLM call: model=stub prompt_chars=%s', len(prompt))
        preview = prompt.strip().splitlines()[0][:240] if prompt.strip() else ''
        text = (
            'Stub LLM (configure Mistral via MISTRAL_API_KEY / MISTRAL_BASE_URL '
            'for semantic answers).\n\n'
            f'Echoing prompt preview: {preview}'
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info('LLM ok: model=stub latency_ms=%s answer_chars=%s', latency_ms, len(text))
        return text

    raise LLMError(
        f'Unsupported LLM client type: {type(client).__name__}. '
        'Implement a compatible adapter or use Mistral/Stub.'
    )
