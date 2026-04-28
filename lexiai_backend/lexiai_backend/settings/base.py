from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR.parent / '.env'
load_dotenv(ENV_PATH, override=False)


def env(name: str, default: Any | None = None) -> Any:
    value = os.getenv(name)
    return default if value in (None, '') else value


def env_bool(name: str, default: bool = False) -> bool:
    value = str(env(name, default)).strip().lower()
    return value in {'1', 'true', 'yes', 'on'}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw_value = env(name)
    if raw_value is None:
        return default or []
    return [item.strip() for item in raw_value.split(',') if item.strip()]


def env_int(name: str, default: int) -> int:
    raw_value = env(name)
    return int(raw_value) if raw_value not in (None, '') else default


def build_database_config() -> dict[str, Any]:
    database_url = env('DATABASE_URL')
    if database_url:
        parsed = urlparse(database_url)
        if parsed.scheme in {'postgres', 'postgresql'}:
            return {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': parsed.path.lstrip('/'),
                'USER': parsed.username or '',
                'PASSWORD': parsed.password or '',
                'HOST': parsed.hostname or 'db',
                'PORT': str(parsed.port or '5432'),
                'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', 60),
                'OPTIONS': {'sslmode': env('DB_SSLMODE', 'prefer')},
            }
        if parsed.scheme == 'sqlite':
            return {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': parsed.path or str(BASE_DIR / 'db.sqlite3'),
            }
        raise RuntimeError(f'Unsupported DATABASE_URL scheme: {parsed.scheme}')

    engine = env('DB_ENGINE', 'django.db.backends.sqlite3')
    if engine == 'django.db.backends.sqlite3':
        return {
            'ENGINE': engine,
            'NAME': env('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        }

    return {
        'ENGINE': engine,
        'NAME': env('DB_NAME', ''),
        'USER': env('DB_USER', ''),
        'PASSWORD': env('DB_PASSWORD', ''),
        'HOST': env('DB_HOST', 'db'),
        'PORT': env('DB_PORT', '5432'),
        'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', 60),
        'OPTIONS': {'sslmode': env('DB_SSLMODE', 'prefer')},
    }


SECRET_KEY = env('SECRET_KEY', 'dev-unsafe-secret-key-change-me')
DEBUG = env_bool('DEBUG', False)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1', 'web'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'accounts.apps.AccountsConfig',
    'conversations.apps.ConversationsConfig',
    'documents.apps.DocumentsConfig',
    'feedback.apps.FeedbackConfig',
    'core.apps.CoreConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'lexiai_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lexiai_backend.wsgi.application'
ASGI_APPLICATION = 'lexiai_backend.asgi.application'

DATABASES = {'default': build_database_config()}

AUTH_USER_MODEL = 'accounts.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': env_int('PAGE_SIZE', 20),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': env('ANON_RATE_LIMIT', '100/day'),
        'user': env('USER_RATE_LIMIT', '1000/day'),
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'LexiAI API',
    'DESCRIPTION': 'AI-powered legal document analysis and chat platform.',
    'VERSION': 'v1',
    'SERVE_INCLUDE_SCHEMA': False,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS', ['http://localhost:3000', 'http://127.0.0.1:3000'])
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', ['http://localhost:3000', 'http://127.0.0.1:3000'])

EMAIL_BACKEND = env('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'noreply@lexiai.local')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'lexiai-cache',
    }
}

REDIS_URL = env('REDIS_URL')
if REDIS_URL:
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }

CELERY_BROKER_URL = env('CELERY_BROKER_URL', REDIS_URL or 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', REDIS_URL or CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
REFERRER_POLICY = 'same-origin'

FILE_UPLOAD_MAX_MEMORY_SIZE = env_int('FILE_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int('DATA_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': env('LOG_LEVEL', 'INFO'),
    },
}
