#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=lexiai_backend.settings.prod

celery -A lexiai_backend worker \
  --loglevel=info \
  --concurrency=2
