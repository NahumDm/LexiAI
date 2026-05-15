#!/usr/bin/env bash
set -euo pipefail

# Same as start.sh — loads prod.py (CELERY_*_USE_SSL, REDIS_URL, cache, etc.).
export DJANGO_SETTINGS_MODULE=lexiai_backend.settings.prod

if [ -z "${SECRET_KEY:-}" ]; then
  echo "ERROR: SECRET_KEY is unset. Railway → Celery worker service → Variables → add SECRET_KEY (same value as web)." >&2
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is unset on the worker. Copy the same DATABASE_URL from Postgres into this worker service's Variables." >&2
  exit 1
fi
if [ -z "${REDIS_URL:-}" ]; then
  echo "ERROR: REDIS_URL is unset on the worker. Copy REDIS_URL into this worker service (Celery broker)." >&2
  exit 1
fi
if [ -z "${CORS_ALLOWED_ORIGINS:-}" ]; then
  echo "ERROR: CORS_ALLOWED_ORIGINS is unset on the worker. Copy the same CORS_ALLOWED_ORIGINS as the web service (prod mirrors CSRF from CORS if CSRF_TRUSTED_ORIGINS is unset)." >&2
  exit 1
fi

exec celery -A lexiai_backend worker \
  --loglevel=info \
  --concurrency=2

