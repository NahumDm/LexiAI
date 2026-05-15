import os
import re
from urllib.parse import urlparse

import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False


def _strip_quoted(raw: str) -> str:
    s = (raw or '').strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        s = s[1:-1].strip()
    return s


def _env_stripped(name: str) -> str:
    return _strip_quoted(os.environ.get(name, ''))


def _require_env(name: str, guidance: str) -> str:
    value = _env_stripped(name)
    if not value:
        raise RuntimeError(f'{name} is missing or empty. {guidance}')
    return value


_secret_raw = _env_stripped('SECRET_KEY')
if not _secret_raw:
    raise RuntimeError(
        'SECRET_KEY is missing or empty. Railway → this service → Variables → SECRET_KEY '
        '(>=32 characters). Generate: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
if len(_secret_raw) < 32:
    raise RuntimeError(
        f'SECRET_KEY must be at least 32 characters (got {len(_secret_raw)}). '
        'Regenerate with token_urlsafe(64) and update Railway Variables.'
    )
SECRET_KEY = _secret_raw

database_url = _require_env(
    'DATABASE_URL',
    'Add PostgreSQL (New → Database → Postgres), open the database service → Variables, '
    'then copy or reference DATABASE_URL on this web service and redeploy.',
)
_db_scheme = urlparse(database_url).scheme
if _db_scheme not in {'postgres', 'postgresql'}:
    raise RuntimeError(
        f'DATABASE_URL must use postgres or postgresql (got {_db_scheme!r}). '
        'Fix the value or the Railway variable reference.'
    )


def _extract_embedded_redis_url(s: str) -> str | None:
    """First redis:// or rediss:// token in a longer paste (e.g. redis-cli -u 'rediss://…')."""
    m = re.search(r'(redis|rediss)://\S+', s, re.IGNORECASE)
    if not m:
        return None
    return m.group(0).rstrip('"\').,;)]}\\')


def _finalize_redis_url(raw: str) -> tuple[str, str]:
    """Return (canonical_url, scheme). Accepts redis/rediss; tolerates Railway quoting/BOM quirks."""
    s = (raw or '').strip().lstrip('\ufeff')
    if len(s) >= 2 and s[0] in '"\'' and s[-1] == s[0]:
        s = s[1:-1].strip()
    s = s.strip()
    if not s:
        raise RuntimeError('REDIS_URL is empty after trimming.')
    if s.startswith('://'):
        raise RuntimeError(
            'REDIS_URL is invalid: it starts with "://" (scheme was cut off). '
            'Paste the full value starting with rediss:// or redis:// from Upstash / Railway Redis.'
        )
    if '{{' in s or '${' in s:
        raise RuntimeError(
            'REDIS_URL contains template syntax that did not resolve (e.g. ${{ ... }}). '
            'In Railway, set REDIS_URL via the variable reference picker or paste the literal URL.'
        )
    low = s.lower()
    if low.startswith('https://') or low.startswith('http://'):
        raise RuntimeError(
            'REDIS_URL must not be an https:// or http:// URL (e.g. Upstash UPSTASH_REDIS_REST_URL). '
            'Use the TLS TCP URL from Upstash -> Connect: rediss://default:PASSWORD@HOST:6379'
        )
    # Pasted Upstash "redis-cli --tls -u …" line without the actual DSN (truncated after -u).
    if re.match(r'^\s*(?:[$#]\s*)?(?:sudo\s+)?redis-cli\b', s, re.IGNORECASE) and not re.search(
        r'(redis|rediss)://', s, re.IGNORECASE
    ):
        raise RuntimeError(
            'REDIS_URL looks like a redis-cli command, but there is no redis:// or rediss:// URL in it '
            '(often the value after -u was cut off). In Upstash: your database -> Connect, copy only the '
            'connection string that starts with rediss://..., not the redis-cli wrapper.'
        )
    if not re.match(r'^(redis|rediss)://', s, re.IGNORECASE):
        embedded = _extract_embedded_redis_url(s)
        if embedded:
            s = embedded
    m = re.match(r'^(redis|rediss)://', s, re.IGNORECASE)
    if m:
        return s, m.group(1).lower()
    if '://' not in s:
        s = f'redis://{s.lstrip("/")}'
    parsed = urlparse(s)
    if parsed.scheme in {'redis', 'rediss'}:
        return s, parsed.scheme
    raise RuntimeError(
        'REDIS_URL must start with redis:// or rediss:// (TLS). '
        f'Parsed scheme was {parsed.scheme!r}. First 24 chars: {s[:24]!r}. '
        'Remove stray quotes/newlines in Railway Variables and paste the full Upstash TCP URL.'
    )


redis_url = _env_stripped('REDIS_URL')
if not redis_url:
    if _env_stripped('UPSTASH_REDIS_REST_URL'):
        raise RuntimeError(
            'REDIS_URL is unset but UPSTASH_REDIS_REST_URL is set. '
            'UPSTASH_REDIS_REST_URL is the HTTP REST endpoint only - Django cache and Celery need the Redis TCP URL. '
            'In the Upstash console open your database -> Connect / redis-cli and copy '
            'rediss://default:PASSWORD@....upstash.io:6379 into Railway as REDIS_URL '
            '(same on the worker service).'
        )
    raise RuntimeError(
        'REDIS_URL is missing or empty. Add Redis (Upstash, Railway Redis, etc.), then set REDIS_URL on this service. '
        'Required for Celery broker and Django cache in production.'
    )
redis_url, _redis_scheme = _finalize_redis_url(redis_url)

# `base` read REDIS_URL before normalization; align cache + Celery with the canonical URL.
REDIS_URL = redis_url
CACHES['default'] = {
    'BACKEND': 'django.core.cache.backends.redis.RedisCache',
    'LOCATION': REDIS_URL,
}
_celery_broker = _env_stripped('CELERY_BROKER_URL')
_celery_result = _env_stripped('CELERY_RESULT_BACKEND')
CELERY_BROKER_URL = _celery_broker or REDIS_URL
CELERY_RESULT_BACKEND = _celery_result or CELERY_BROKER_URL

# Default `*` when unset so deploy works before the public hostname / frontend URL is known.
# Set explicit comma-separated hosts in Railway Variables before exposing real traffic.
_allowed = env_list('ALLOWED_HOSTS', ['*'])
ALLOWED_HOSTS = _allowed if _allowed else ['*']

def _split_origins_no_path(csv: str) -> list[str]:
    """django-cors-headers E014: each origin must be scheme+host+port only (no path, no trailing /)."""
    out: list[str] = []
    for part in csv.split(','):
        p = part.strip()
        if not p:
            continue
        while p.endswith('/'):
            p = p[:-1].rstrip()
        out.append(p)
    return out


# Do not rely on base.py localhost default in production: require explicit browser origins.
_cors_env = _env_stripped('CORS_ALLOWED_ORIGINS')
if not _cors_env:
    raise RuntimeError(
        'CORS_ALLOWED_ORIGINS is missing or empty. Set comma-separated HTTPS origins for your '
        'frontend (e.g. https://your-app.vercel.app). Browsers will block API calls without this.'
    )
CORS_ALLOWED_ORIGINS = _split_origins_no_path(_cors_env)

_csrf_env = _env_stripped('CSRF_TRUSTED_ORIGINS')
if _csrf_env:
    CSRF_TRUSTED_ORIGINS = _split_origins_no_path(_csrf_env)
else:
    CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)

_db_ssl_require = env_bool('DB_SSL_REQUIRE', True)
try:
    DATABASES = {
        'default': dj_database_url.config(
            default=database_url,
            conn_max_age=env_int('DB_CONN_MAX_AGE', 600),
            ssl_require=_db_ssl_require,
        )
    }
except Exception as exc:
    raise RuntimeError(
        'Could not build Django database config from DATABASE_URL. '
        'Check for typos, truncated paste, or special characters in the password (URL-encode if needed). '
        'If Railway private networking rejects TLS, you may set DB_SSL_REQUIRE=false only after confirming risk.'
    ) from exc

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', True)
