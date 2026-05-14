from __future__ import annotations

import logging
import os

from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lexiai_backend.settings.dev')

logger = logging.getLogger(__name__)

app = Celery('lexiai_backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@worker_process_init.connect
def _embedding_worker_process_init(**_kwargs) -> None:
	"""
	Each prefork child must not reuse a SentenceTransformer loaded in the parent.

	See ``EmbeddingService.reset_after_fork`` — prevents hangs/deadlocks inside
	``model.encode()`` after ``fork()`` (OpenMP / PyTorch thread pools).
	"""
	from ai_engine.services.embedding import EmbeddingService

	EmbeddingService.reset_after_fork()
	logger.info('celery.worker_process_init: embedding fork-safety reset applied')
