from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = env('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY must be set for production.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
if not ALLOWED_HOSTS:
    raise RuntimeError('ALLOWED_HOSTS must be set for production.')

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', True)
