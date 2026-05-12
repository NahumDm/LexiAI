from __future__ import annotations

import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


def _warmup_models() -> None:
    """Pre-load heavy ML assets so the first user request doesn't pay the cost.

    Currently warms the sentence-transformer used by ``EmbeddingService``.
    Failures are swallowed and logged — the app must always start, even when
    HuggingFace is unreachable, the model cache is stale, or the embedding
    backend changes.
    """
    try:
        from ai_engine.services.embedding import EmbeddingService

        logger.info('warmup: loading embedding model in background...')
        EmbeddingService.generate_embedding('warmup')
        logger.info('warmup: embedding model ready')
    except Exception as exc:
        logger.error('warmup: embedding model failed to load: %s', exc, exc_info=True)


class AiEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_engine'

    def ready(self) -> None:
        """Gated, non-blocking startup hook.

        Warmup runs in a daemon thread so worker import time is unaffected.
        Gated on ``AI_WARMUP_ON_STARTUP`` so management commands (migrate,
        shell, makemigrations, ...) don't trigger a model download.
        """
        from django.conf import settings

        if not getattr(settings, 'AI_WARMUP_ON_STARTUP', False):
            return

        thread = threading.Thread(
            target=_warmup_models,
            daemon=True,
            name='ai-engine-warmup',
        )
        thread.start()
        logger.info('warmup: scheduled (daemon thread started, app not blocked)')
