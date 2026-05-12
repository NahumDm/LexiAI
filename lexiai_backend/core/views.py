from __future__ import annotations

import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _probe_database() -> tuple[str, str | None]:
    """Round-trip ``SELECT 1`` against the default DB. Returns (status, error)."""
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return 'ok', None
    except Exception as exc:
        logger.warning('health: database probe failed: %s', exc)
        return 'down', str(exc)


class HealthCheckView(APIView):
    """
    Liveness + LLM/RAG/DB configuration probe.

    GET /api/v1/health/  → 200
    {
        "status": "ok" | "degraded",
        "service": "LexiAI",
        "llm": "stub" | "mistral" | "unknown",
        "embeddings_loaded": true | false,
        "database": "ok" | "down"
    }

    Intentionally unauthenticated so uptime monitors, load balancers, and
    Kubernetes-style probes can poll it. Never raises: any internal probe
    failure is reported as ``status="degraded"`` with a best-effort body.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        llm_kind = 'unknown'
        embeddings_loaded = False
        status_label = 'ok'
        error: str | None = None

        try:
            from ai_engine.services.embedding import EmbeddingService
            from ai_engine.services.llm_client import MistralLLMClient, get_llm_client

            try:
                client = get_llm_client()
                llm_kind = 'mistral' if isinstance(client, MistralLLMClient) else 'stub'
            except Exception as exc:
                logger.warning('health: LLM resolver failed: %s', exc)
                llm_kind = 'unknown'
                status_label = 'degraded'
                error = str(exc)

            embeddings_loaded = EmbeddingService._model is not None
        except Exception as exc:
            logger.exception('health: AI probe failed: %s', exc)
            status_label = 'degraded'
            error = str(exc)

        database_status, db_error = _probe_database()
        if database_status != 'ok':
            status_label = 'degraded'
            error = error or db_error

        body = {
            'status': status_label,
            'service': 'LexiAI',
            'llm': llm_kind,
            'embeddings_loaded': embeddings_loaded,
            'database': database_status,
        }
        if error is not None:
            body['error'] = error
        return Response(body)
