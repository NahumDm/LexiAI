#!/usr/bin/env bash
set -euo pipefail

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
if [ -z "${CORS_ALLOWED_ORIGINS:-}" ] || [ -z "${CSRF_TRUSTED_ORIGINS:-}" ]; then
  echo "ERROR: CORS_ALLOWED_ORIGINS and CSRF_TRUSTED_ORIGINS must be set (Django loads prod settings). Copy from web service." >&2
  exit 1
fi

celery -A lexiai_backend worker \
  --loglevel=info \
  --concurrency=2
