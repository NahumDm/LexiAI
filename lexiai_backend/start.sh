#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=lexiai_backend.settings.prod

python manage.py migrate --noinput
python manage.py collectstatic --noinput

gunicorn lexiai_backend.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --timeout 120
