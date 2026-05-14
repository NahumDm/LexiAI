from __future__ import annotations

import logging
import os

from celery import Celery
from celery.signals import task_failure, task_prerun, worker_process_init

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lexiai_backend.settings.prod')

logger = logging.getLogger(__name__)

app = Celery('lexiai_backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

_EMBED_TASK = 'ai_engine.tasks.embed_document_chunks'


@task_prerun.connect
def _log_embed_task_prerun(sender=None, task_id=None, args=None, kwargs=None, **_kw):
	name = getattr(sender, 'name', None)
	if name != _EMBED_TASK:
		return
	logger.info(
		'[CELERY] TASK_PRERUN name=%s celery_id=%s args=%s kwargs=%s',
		name,
		task_id,
		args,
		kwargs,
	)


@task_failure.connect
def _log_embed_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_kw):
	name = getattr(sender, 'name', None)
	if name != _EMBED_TASK:
		return
	logger.error(
		'[CELERY] TASK_FAILURE name=%s celery_id=%s exception=%s args=%s',
		name,
		task_id,
		exception,
		args,
		exc_info=exception is not None,
	)


@worker_process_init.connect
def _embedding_worker_process_init(**_kwargs) -> None:
	"""
	Each prefork child must not reuse a SentenceTransformer loaded in the parent.

	See ``EmbeddingService.reset_after_fork`` — prevents hangs/deadlocks inside
	``model.encode()`` after ``fork()`` (OpenMP / PyTorch thread pools).
	"""
	broker = os.environ.get('CELERY_BROKER_URL', '')
	broker_tail = broker.split('@', 1)[-1] if '@' in broker else broker[-80:]
	logger.info(
		'[CELERY] worker_process_init broker_tail=%s (queue default: celery)',
		broker_tail,
	)
	from ai_engine.services.embedding import EmbeddingService

	EmbeddingService.reset_after_fork()
	logger.info('celery.worker_process_init: embedding fork-safety reset applied')
