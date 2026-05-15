import os

import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False


def _secret_key_from_environ() -> str:
    raw = (os.environ.get('SECRET_KEY') or '').strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        raw = raw[1:-1].strip()
    return raw


_secret_raw = _secret_key_from_environ()
if not _secret_raw:
    raise RuntimeError(
        'SECRET_KEY is not set. In Railway: Service → Variables → add '
        'SECRET_KEY (shared variable or raw value). It must be at least 32 characters. '
        'Generate locally: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
if len(_secret_raw) < 32:
    raise RuntimeError(
        'SECRET_KEY must be at least 32 characters in production. '
        'Railway Variables → SECRET_KEY — use a new token_urlsafe(64) value.'
    )
SECRET_KEY = _secret_raw

database_url = (os.environ.get('DATABASE_URL') or '').strip()
if not database_url:
    raise RuntimeError('DATABASE_URL must be set for production.')

redis_url = (os.environ.get('REDIS_URL') or '').strip()
if not redis_url:
    raise RuntimeError('REDIS_URL must be set for production.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
if not ALLOWED_HOSTS:
    raise RuntimeError('ALLOWED_HOSTS must be set for production.')

DATABASES = {
    'default': dj_database_url.config(
        default=database_url,
        conn_max_age=600,
        ssl_require=True,
    )
}

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', True)
