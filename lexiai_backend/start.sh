#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=lexiai_backend.settings.prod

if [ -z "${SECRET_KEY:-}" ]; then
  echo "ERROR: SECRET_KEY is unset. In Railway: open THIS service (the one running this image) → Variables → add SECRET_KEY (>=32 chars). Then redeploy." >&2
  exit 1
fi
if [ "${#SECRET_KEY}" -lt 32 ]; then
  echo "ERROR: SECRET_KEY must be at least 32 characters (length is ${#SECRET_KEY}). Regenerate and update Railway Variables." >&2
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is unset. Railway: add PostgreSQL (New → Database → Postgres). In the Postgres service, copy DATABASE_URL (Variables tab) into THIS web service's Variables as DATABASE_URL, or use Variable Reference. Redeploy." >&2
  exit 1
fi
if [ -z "${REDIS_URL:-}" ]; then
  echo "ERROR: REDIS_URL is unset. Railway: add Redis, then set REDIS_URL on THIS service (same pattern as DATABASE_URL). Required for Celery/cache in production." >&2
  exit 1
fi
if [ -z "${CORS_ALLOWED_ORIGINS:-}" ]; then
  echo "ERROR: CORS_ALLOWED_ORIGINS is unset. Set comma-separated HTTPS frontend origins (e.g. https://your-app.vercel.app)." >&2
  exit 1
fi
# CSRF_TRUSTED_ORIGINS is optional: prod settings mirror CORS when it is unset.

python manage.py migrate --noinput
# JWT blacklist tables are required for login/guest (OutstandingToken); explicit app avoids silent skips.
python manage.py migrate token_blacklist --noinput
python manage.py collectstatic --noinput

gunicorn lexiai_backend.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --timeout 120
