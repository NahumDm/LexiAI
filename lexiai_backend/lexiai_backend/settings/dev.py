from .base import *  # noqa: F401,F403

# Honor env so the same dev settings can simulate production by setting DEBUG=False.
DEBUG = env_bool('DEBUG', True)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1', 'web'])

_default_local_origins = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
]
_cors = env_list('CORS_ALLOWED_ORIGINS')
CORS_ALLOWED_ORIGINS = _cors if _cors else _default_local_origins
_csrf = env_list('CSRF_TRUSTED_ORIGINS')
CSRF_TRUSTED_ORIGINS = _csrf if _csrf else _default_local_origins

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
