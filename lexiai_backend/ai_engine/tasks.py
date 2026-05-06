from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from ai_engine.models import DocumentChunk
from ai_engine.services.chunking import ChunkingService
from ai_engine.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def embed_document_chunks(self, document_id: int) -> dict[str, int]:
	"""
	Background task to chunk and embed a document.
	Runs asynchronously so document uploads don't block.

	Returns: {created: int, updated: int}
	"""
	from documents.models import Document

	try:
		document = Document.objects.get(pk=document_id)
	except Document.DoesNotExist:
		logger.error(f'Document {document_id} not found')
		return {'error': f'Document {document_id} not found'}

	if not document.extracted_text:
		logger.warning(f'Document {document_id} has no extracted text')
		return {'created': 0, 'updated': 0}

	try:
		chunks_data = ChunkingService.chunk_document(document.extracted_text)
		logger.info(f'Chunked document {document_id} into {len(chunks_data)} chunks')
	except Exception as exc:
		logger.error(f'Chunking failed for document {document_id}: {exc}')
		raise self.retry(exc=exc, countdown=60)

	try:
		texts = [chunk['content'] for chunk in chunks_data]
		embeddings = EmbeddingService.generate_embeddings_batch(texts)
		logger.info(f'Generated embeddings for {len(embeddings)} chunks')
	except Exception as exc:
		logger.error(f'Embedding failed for document {document_id}: {exc}')
		raise self.retry(exc=exc, countdown=60)

	created_count = 0
	updated_count = 0

	for chunk_data, embedding in zip(chunks_data, embeddings):
		chunk_obj, created = DocumentChunk.objects.update_or_create(
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

	logger.info(
		f'Created {created_count} new chunks, updated {updated_count} existing chunks for document {document_id}'
	)

	return {'created': created_count, 'updated': updated_count}
