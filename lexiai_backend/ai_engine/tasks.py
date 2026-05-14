from __future__ import annotations

import logging

from celery import shared_task
from celery.exceptions import Retry

from ai_engine.models import DocumentChunk
from ai_engine.services.chunking import ChunkingService
from ai_engine.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

_METADATA_KEYS_TO_CLEAR_ON_SUCCESS = (
	'ingestion_failed',
	'ingestion_error',
	'ingestion_detail',
	'embedding_failed',
	'embedding_error',
	'failed',
)


def _clear_transient_failure_metadata(document) -> None:
	"""Mutate ``document.metadata`` in memory only (caller saves)."""
	meta = dict(document.metadata or {})
	for key in _METADATA_KEYS_TO_CLEAR_ON_SUCCESS:
		meta.pop(key, None)
	document.metadata = meta


@shared_task(bind=True, max_retries=3, soft_time_limit=600, time_limit=720)
def embed_document_chunks(self, document_id: int) -> dict[str, int]:
	"""
	Background task: extract text (if needed), chunk, embed, persist ``DocumentChunk`` rows.

	``document.status`` is always persisted in ``finally`` so rows never stay stuck in
	``processing`` when the worker process crashes after chunk writes. Celery ``Retry``
	does not reset status to ``uploaded``.

	Returns: {created: int, updated: int}
	"""
	from documents.models import Document
	from documents.services import (
		INGESTION_STATUS_COMPLETED,
		INGESTION_STATUS_FAILED,
		INGESTION_STATUS_PROCESSING,
		merge_document_metadata,
		populate_extracted_text_from_source_file,
		set_document_ingestion_status,
	)

	task_id = getattr(getattr(self, 'request', None), 'id', None)
	result: dict[str, int] = {'created': 0, 'updated': 0}
	document: Document | None = None

	logger.info(
		'[INGESTION] TASK_STARTED task=embed_document_chunks document_id=%s celery_task_id=%s',
		document_id,
		task_id,
	)

	try:
		document = Document.objects.select_related('owner').get(pk=document_id)
	except Document.DoesNotExist:
		logger.error(
			'[INGESTION] DOCUMENT_NOT_FOUND document_id=%s celery_task_id=%s',
			document_id,
			task_id,
		)
		raise

	logger.info(
		'[INGESTION] DOCUMENT_FETCHED document_id=%s owner_id=%s title=%r status=%s '
		'celery_task_id=%s',
		document.pk,
		document.owner_id,
		document.title,
		document.status,
		task_id,
	)

	has_file = bool(document.source_file and document.source_file.name)
	logger.info(
		'[INGESTION] DOCUMENT_SNAPSHOT document_id=%s owner_id=%s has_source_file=%s '
		'extracted_text_len=%s metadata_ingestion_status=%s celery_task_id=%s',
		document_id,
		document.owner_id,
		has_file,
		len((document.extracted_text or '').strip()),
		(document.metadata or {}).get('ingestion_status'),
		task_id,
	)

	try:
		if not populate_extracted_text_from_source_file(document):
			logger.warning(
				'[INGESTION] TEXT_EXTRACT_FAILED document_id=%s owner_id=%s — no extractable text '
				'(see metadata) celery_task_id=%s',
				document_id,
				document.owner_id,
				task_id,
			)
			set_document_ingestion_status(
				document,
				INGESTION_STATUS_FAILED,
				ingestion_failure_stage='populate_extracted_text',
			)
			document.status = Document.Status.UPLOADED
			return result

		document.refresh_from_db()
		text_len = len((document.extracted_text or '').strip())
		logger.info(
			'[INGESTION] TEXT_EXTRACTED document_id=%s owner_id=%s length=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			text_len,
			task_id,
		)

		set_document_ingestion_status(document, INGESTION_STATUS_PROCESSING, ingestion_started_task_id=str(task_id))
		document.status = Document.Status.PROCESSING
		document.save(update_fields=['status', 'metadata', 'updated_at'])

		try:
			chunks_data = ChunkingService.chunk_document(document.extracted_text)
		except Exception as exc:
			logger.exception(
				'[INGESTION] CHUNKING_EXCEPTION document_id=%s owner_id=%s celery_task_id=%s',
				document_id,
				document.owner_id,
				task_id,
			)
			raise self.retry(exc=exc, countdown=60) from exc

		n_chunks = len(chunks_data)
		logger.info(
			'[INGESTION] CHUNKS_CREATED document_id=%s owner_id=%s count=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			n_chunks,
			task_id,
		)

		if not chunks_data:
			logger.warning(
				'[INGESTION] CHUNKS_ZERO document_id=%s owner_id=%s celery_task_id=%s',
				document_id,
				document.owner_id,
				task_id,
			)
			DocumentChunk.objects.filter(document=document).delete()
			merge_document_metadata(
				document,
				{
					'ingestion_failed': True,
					'ingestion_error': 'no_chunkable_content',
					'ingestion_status': INGESTION_STATUS_FAILED,
					'ingestion_failure_stage': 'chunking_empty',
				},
			)
			document.status = Document.Status.UPLOADED
			document.save(update_fields=['status', 'metadata', 'updated_at'])
			return result

		logger.info(
			'[INGESTION] EMBEDDING_START document_id=%s owner_id=%s texts=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			n_chunks,
			task_id,
		)
		try:
			texts = [chunk['content'] for chunk in chunks_data]
			embeddings = EmbeddingService.generate_embeddings_batch(texts)
			emb_count = len(embeddings)
		except Exception as exc:
			logger.exception(
				'[INGESTION] EMBEDDING_EXCEPTION document_id=%s owner_id=%s celery_task_id=%s',
				document_id,
				document.owner_id,
				task_id,
			)
			raise self.retry(exc=exc, countdown=60) from exc

		logger.info(
			'[INGESTION] EMBEDDING_END document_id=%s owner_id=%s embeddings=%s shape=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			emb_count,
			getattr(embeddings, 'shape', None),
			task_id,
		)

		if emb_count != len(chunks_data):
			logger.error(
				'[INGESTION] EMBEDDING_COUNT_MISMATCH document_id=%s chunks=%s embeddings=%s celery_task_id=%s',
				document_id,
				len(chunks_data),
				emb_count,
				task_id,
			)
			raise RuntimeError('EmbeddingService returned mismatched result count')

		logger.info(
			'[INGESTION] DB_SAVE_START document_id=%s owner_id=%s rows=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			len(chunks_data),
			task_id,
		)
		created_count = 0
		updated_count = 0
		processed_indices: list[int] = []

		for chunk_data, embedding in zip(chunks_data, embeddings, strict=True):
			_chunk_obj, created = DocumentChunk.objects.update_or_create(
				document=document,
				sequence_index=chunk_data['sequence_index'],
				defaults={
					'document_owner': document.owner,
					'content': chunk_data['content'],
					'token_count': chunk_data['token_count'],
					'embedding': EmbeddingService.embedding_to_bytes(embedding),
					'metadata': {
						'source_document': document.title,
						'embedding_model': 'all-MiniLM-L6-v2',
					},
				},
			)
			if created:
				created_count += 1
			else:
				updated_count += 1
			processed_indices.append(chunk_data['sequence_index'])

		logger.info(
			'[INGESTION] DB_SAVE_END document_id=%s owner_id=%s created=%s updated=%s '
			'total_written=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			created_count,
			updated_count,
			len(processed_indices),
			task_id,
		)

		try:
			deleted, _ = DocumentChunk.objects.filter(document=document).exclude(
				sequence_index__in=processed_indices
			).delete()
			if deleted:
				logger.info(
					'[INGESTION] DB_STALE_CHUNKS_DELETED document_id=%s deleted=%s celery_task_id=%s',
					document_id,
					deleted,
					task_id,
				)
		except Exception as exc:
			logger.warning(
				'[INGESTION] DB_STALE_DELETE_WARN document_id=%s: %s celery_task_id=%s',
				document_id,
				exc,
				task_id,
			)

		_clear_transient_failure_metadata(document)
		set_document_ingestion_status(
			document,
			INGESTION_STATUS_COMPLETED,
			ingestion_chunk_count=len(processed_indices),
			ingestion_completed_task_id=str(task_id),
		)

		document.status = Document.Status.READY
		document.save(update_fields=['status', 'metadata', 'updated_at'])

		logger.info(
			'[INGESTION] TASK_COMPLETED document_id=%s owner_id=%s chunks=%s created=%s updated=%s celery_task_id=%s',
			document_id,
			document.owner_id,
			len(processed_indices),
			created_count,
			updated_count,
			task_id,
		)
		result = {'created': created_count, 'updated': updated_count}

	except Retry:
		logger.info(
			'[INGESTION] TASK_RETRY document_id=%s owner_id=%s celery_task_id=%s',
			document_id,
			getattr(document, 'owner_id', None),
			task_id,
		)
		raise
	except Exception as exc:
		logger.exception(
			'[INGESTION] TASK_FAILED document_id=%s owner_id=%s celery_task_id=%s',
			document_id,
			getattr(document, 'owner_id', None),
			task_id,
		)
		if document is not None:
			try:
				merge_document_metadata(
					document,
					{
						'embedding_failed': True,
						'embedding_error': type(exc).__name__,
						'embedding_detail': str(exc)[:500],
						'ingestion_status': INGESTION_STATUS_FAILED,
						'ingestion_failure_stage': 'task_exception',
					},
				)
				document.status = Document.Status.UPLOADED
				document.save(update_fields=['status', 'metadata', 'updated_at'])
			except Exception as save_exc:
				logger.exception(
					'[INGESTION] FAILURE_METADATA_SAVE_ERROR document_id=%s: %s',
					document_id,
					save_exc,
				)
		raise
	finally:
		if document is not None:
			try:
				document.save(update_fields=['status', 'updated_at'])
			except Exception as fin_exc:
				logger.error(
					'[INGESTION] FINALLY_STATUS_SAVE_ERROR document_id=%s: %s',
					document_id,
					fin_exc,
				)

	return result
