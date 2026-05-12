from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1', 'web'])
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
