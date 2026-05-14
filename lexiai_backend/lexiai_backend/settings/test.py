from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = 'test-secret-key'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'lexiai-test-cache',
    }
}

CORS_ALLOWED_ORIGINS = ['http://testserver']
CSRF_TRUSTED_ORIGINS = ['http://testserver']

CELERY_BROKER_URL = env('CELERY_BROKER_URL') or env('REDIS_URL') or 'redis://127.0.0.1:6379/15'
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND') or CELERY_BROKER_URL
