"""
DRF throttles that never take down auth/API when Redis cache is unreachable.

Production uses Redis for ``CACHES['default']``; a bad ``REDIS_URL`` or TLS mismatch
otherwise makes *every* throttled view return HTTP 500 during ``cache.get`` / ``cache.incr``.
"""

from __future__ import annotations

import logging

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


class _CacheSafeThrottleMixin:
    """Skip rate limiting when the cache backend errors (log once per request path)."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception as exc:
            logger.warning(
                'Throttle cache unavailable (%s); allowing request %s %s',
                exc,
                request.method,
                getattr(request, 'path', ''),
            )
            return True


class SafeAnonRateThrottle(_CacheSafeThrottleMixin, AnonRateThrottle):
    pass


class SafeUserRateThrottle(_CacheSafeThrottleMixin, UserRateThrottle):
    pass
