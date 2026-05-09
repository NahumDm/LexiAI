from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from .models import DocumentIngestionJob
from .services import _agent_debug_log, ingest_tax_documents


@shared_task(bind=True)
def process_tax_document_ingestion_job(self, job_id: int) -> None:
    job = DocumentIngestionJob.objects.select_related('owner', 'requested_by').get(pk=job_id)
    _agent_debug_log(
        'process_tax_document_ingestion_job entered',
        {'job_id': job_id, 'source_dir': job.source_dir, 'job_status': job.status},
        'H4',
    )
    if job.status in {DocumentIngestionJob.Status.RUNNING, DocumentIngestionJob.Status.SUCCEEDED}:
        _agent_debug_log(
            'process_tax_document_ingestion_job skipped',
            {'job_id': job_id, 'source_dir': job.source_dir, 'job_status': job.status},
            'H4',
        )
        return

    job.status = DocumentIngestionJob.Status.RUNNING
    job.started_at = timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])

    try:
        ingest_tax_documents(job.source_dir, job.owner, requested_by=job.requested_by, job=job)
    except Exception as exc:
        _agent_debug_log(
            'process_tax_document_ingestion_job exception',
            {
                'job_id': job_id,
                'source_dir': job.source_dir,
                'exc_type': type(exc).__name__,
                'exc': str(exc)[:800],
            },
            'H5',
        )
        job.status = DocumentIngestionJob.Status.FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        raise

    job.status = DocumentIngestionJob.Status.SUCCEEDED
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'finished_at', 'updated_at'])