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

python manage.py migrate --noinput
python manage.py collectstatic --noinput

gunicorn lexiai_backend.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --timeout 120
