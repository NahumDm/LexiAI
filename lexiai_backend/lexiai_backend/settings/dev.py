from .base import *  # noqa: F401,F403

# Honor env so the same dev settings can simulate production by setting DEBUG=False.
DEBUG = env_bool('DEBUG', True)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1', 'web'])
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
