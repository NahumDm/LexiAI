from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from .models import DocumentIngestionJob
from .services import ingest_tax_documents


@shared_task(bind=True)
def process_tax_document_ingestion_job(self, job_id: int) -> None:
    job = DocumentIngestionJob.objects.select_related('owner', 'requested_by').get(pk=job_id)
    if job.status in {DocumentIngestionJob.Status.RUNNING, DocumentIngestionJob.Status.SUCCEEDED}:
        return

    job.status = DocumentIngestionJob.Status.RUNNING
    job.started_at = timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])

    try:
        ingest_tax_documents(job.source_dir, job.owner, requested_by=job.requested_by, job=job)
    except Exception as exc:
        job.status = DocumentIngestionJob.Status.FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        raise

    job.status = DocumentIngestionJob.Status.SUCCEEDED
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'finished_at', 'updated_at'])