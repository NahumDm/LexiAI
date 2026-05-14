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
	from documents.services import merge_document_metadata, populate_extracted_text_from_source_file

	result: dict[str, int] = {'created': 0, 'updated': 0}
	document: Document | None = None

	try:
		document = Document.objects.get(pk=document_id)
	except Document.DoesNotExist:
		logger.error('Document embedding pipeline: document id=%s not found', document_id)
		raise

	try:
		logger.info('Starting ingestion for document %s', document_id)

		if not populate_extracted_text_from_source_file(document):
			logger.warning(
				'Ingestion aborted for document %s: no extractable text (see metadata.ingestion_failed)',
				document_id,
			)
			# Explicit so ``finally`` persists a known state (populate may only touch metadata).
			document.status = Document.Status.UPLOADED
			return result

		document.refresh_from_db()
		logger.info(
			'Extracted text length: %s (document %s)',
			len((document.extracted_text or '').strip()),
			document_id,
		)

		document.status = Document.Status.PROCESSING

		try:
			chunks_data = ChunkingService.chunk_document(document.extracted_text)
		except Exception as exc:
			logger.error('Chunking failed for document %s: %s', document_id, exc)
			raise self.retry(exc=exc, countdown=60) from exc

		logger.info('Chunks created: %s (document %s)', len(chunks_data), document_id)

		if not chunks_data:
			logger.warning(
				'Document id=%s: chunking produced zero chunks — removing old chunks if any',
				document_id,
			)
			DocumentChunk.objects.filter(document=document).delete()
			merge_document_metadata(
				document,
				{'ingestion_failed': True, 'ingestion_error': 'no_chunkable_content'},
			)
			document.status = Document.Status.UPLOADED
			return result

		try:
			texts = [chunk['content'] for chunk in chunks_data]
			logger.info(
				'Calling EmbeddingService.generate_embeddings_batch (document=%s, chunks=%s)',
				document_id,
				len(texts),
			)
			embeddings = EmbeddingService.generate_embeddings_batch(texts)
			emb_count = len(embeddings)
		except Exception as exc:
			logger.error('Embedding failed for document %s: %s', document_id, exc)
			raise self.retry(exc=exc, countdown=60) from exc

		logger.info('Embeddings generated: %s (document %s)', emb_count, document_id)

		if emb_count != len(chunks_data):
			logger.error(
				'Embedding count mismatch for document %s: chunks=%s embeddings=%s',
				document_id,
				len(chunks_data),
				emb_count,
			)
			raise RuntimeError('EmbeddingService returned mismatched result count')

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
			'Document id=%s: chunk rows upserted created=%s updated=%s',
			document_id,
			created_count,
			updated_count,
		)

		try:
			DocumentChunk.objects.filter(document=document).exclude(sequence_index__in=processed_indices).delete()
			logger.info('Removed stale chunks for document %s', document_id)
		except Exception as exc:
			logger.warning('Failed to remove stale chunks for document %s: %s', document_id, exc)

		_clear_transient_failure_metadata(document)
		document.save(update_fields=['metadata', 'updated_at'])

		document.status = Document.Status.READY
		document.save(update_fields=['status'])
		print(f'Document ready: {document.pk}')
		logger.info(
			'Document ready: %s (chunks=%s, created=%s, updated=%s)',
			document_id,
			len(processed_indices),
			created_count,
			updated_count,
		)
		result = {'created': created_count, 'updated': updated_count}

	except Retry:
		raise
	except Exception as e:
		if document is not None:
			document.status = Document.Status.UPLOADED
			print(f'FAILED: {e}')
		raise
	finally:
		if document is not None:
			document.save(update_fields=['status'])

	return result
