#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=lexiai_backend.settings.prod

# region agent log
# Non-secret preflight: which required env vars are present in THIS container.
# Prints one DEBUG_NDJSON line to stdout (visible in Railway deploy logs).
python - <<'PY'
import json, os, time
from pathlib import Path

required = [
    "SECRET_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "CORS_ALLOWED_ORIGINS",
    "PORT",
    "DJANGO_SETTINGS_MODULE",
]
aliases = ["DJANGO_SECRET_KEY", "SECRET", "JWT_SECRET", "DJANGO_SECRET"]
presence = {k: ("set" if (os.environ.get(k) or "").strip() else "missing") for k in required}
alias_presence = {k: ("set" if (os.environ.get(k) or "").strip() else "missing") for k in aliases}
sk = (os.environ.get("SECRET_KEY") or "").strip().strip('"').strip("'")
payload = {
    "sessionId": "e89385",
    "runId": "railway-preflight",
    "hypothesisId": "A",
    "location": "start.sh:preflight",
    "message": "container env presence (no secret values)",
    "data": {
        "presence": presence,
        "aliases": alias_presence,
        "SECRET_KEY_len": len(sk) if sk else 0,
        "bind_port": (os.environ.get("PORT") or "8000"),
        "cwd": os.getcwd(),
    },
    "timestamp": int(time.time() * 1000),
}
line = json.dumps(payload, separators=(",", ":"))
print(f"DEBUG_NDJSON {line}", flush=True)
for candidate in (
    Path("debug-e89385.log"),
    Path("/app/lexiai_backend/debug-e89385.log"),
    Path("/app/debug-e89385.log"),
):
    try:
        with candidate.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        break
    except OSError:
        continue
PY
# endregion

if [ -z "${SECRET_KEY:-}" ]; then
  echo "ERROR: SECRET_KEY is unset. In Railway: open THIS service (the one running this image) → Variables → add SECRET_KEY (>=32 chars). Then redeploy." >&2
  # region agent log
  echo 'DEBUG_NDJSON {"sessionId":"e89385","hypothesisId":"A","location":"start.sh:secret_check","message":"abort SECRET_KEY missing","timestamp":0}' >&2
  # endregion
  exit 1
fi
if [ "${#SECRET_KEY}" -lt 32 ]; then
  echo "ERROR: SECRET_KEY must be at least 32 characters (length is ${#SECRET_KEY}). Regenerate and update Railway Variables." >&2
  # region agent log
  echo "DEBUG_NDJSON {\"sessionId\":\"e89385\",\"hypothesisId\":\"C\",\"location\":\"start.sh:secret_len\",\"message\":\"abort SECRET_KEY too short\",\"data\":{\"len\":${#SECRET_KEY}},\"timestamp\":0}" >&2
  # endregion
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is unset. Railway: add PostgreSQL (New → Database → Postgres). In the Postgres service, copy DATABASE_URL (Variables tab) into THIS web service's Variables as DATABASE_URL, or use Variable Reference. Redeploy." >&2
  # region agent log
  echo 'DEBUG_NDJSON {"sessionId":"e89385","hypothesisId":"D","location":"start.sh:db_check","message":"abort DATABASE_URL missing","timestamp":0}' >&2
  # endregion
  exit 1
fi
if [ -z "${REDIS_URL:-}" ]; then
  echo "ERROR: REDIS_URL is unset. Railway: add Redis, then set REDIS_URL on THIS service (same pattern as DATABASE_URL). Required for Celery/cache in production." >&2
  # region agent log
  echo 'DEBUG_NDJSON {"sessionId":"e89385","hypothesisId":"D","location":"start.sh:redis_check","message":"abort REDIS_URL missing","timestamp":0}' >&2
  # endregion
  exit 1
fi
if [ -z "${CORS_ALLOWED_ORIGINS:-}" ]; then
  echo "ERROR: CORS_ALLOWED_ORIGINS is unset. Set comma-separated HTTPS frontend origins (e.g. https://your-app.vercel.app)." >&2
  # region agent log
  echo 'DEBUG_NDJSON {"sessionId":"e89385","hypothesisId":"D","location":"start.sh:cors_check","message":"abort CORS_ALLOWED_ORIGINS missing","timestamp":0}' >&2
  # endregion
  exit 1
fi
# CSRF_TRUSTED_ORIGINS is optional: prod settings mirror CORS when it is unset.

# region agent log
echo 'DEBUG_NDJSON {"sessionId":"e89385","hypothesisId":"E","location":"start.sh:pre_migrate","message":"env checks passed; starting migrate","timestamp":0}' >&2
# endregion

python manage.py migrate --noinput
# JWT blacklist tables are required for login/guest (OutstandingToken); explicit app avoids silent skips.
python manage.py migrate token_blacklist --noinput
python manage.py collectstatic --noinput

# region agent log
echo "DEBUG_NDJSON {\"sessionId\":\"e89385\",\"hypothesisId\":\"E\",\"location\":\"start.sh:pre_gunicorn\",\"message\":\"starting gunicorn\",\"data\":{\"bind\":\"0.0.0.0:${PORT:-8000}\"},\"timestamp\":0}" >&2
# endregion

gunicorn lexiai_backend.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --timeout 120
