#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=lexiai_backend.settings.prod

if [ -z "${SECRET_KEY:-}" ]; then
  echo "ERROR: SECRET_KEY is unset. Railway → Celery worker service → Variables → add SECRET_KEY (same value as web)." >&2
  exit 1
fi

celery -A lexiai_backend worker \
  --loglevel=info \
  --concurrency=2
