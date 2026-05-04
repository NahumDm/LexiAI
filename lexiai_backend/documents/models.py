from __future__ import annotations

from django.conf import settings
from django.db import models


class Document(models.Model):
	class Status(models.TextChoices):
		UPLOADED = 'uploaded', 'Uploaded'
		PROCESSING = 'processing', 'Processing'
		READY = 'ready', 'Ready'
		ARCHIVED = 'archived', 'Archived'

	owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='documents')
	title = models.CharField(max_length=255)
	description = models.TextField(blank=True)
	source_file = models.FileField(upload_to='documents/%Y/%m/%d/', blank=True, null=True)
	extracted_text = models.TextField(blank=True)
	analysis_summary = models.TextField(blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
	metadata = models.JSONField(default=dict, blank=True)
	page_count = models.PositiveIntegerField(blank=True, null=True)
	file_size = models.BigIntegerField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-updated_at', '-created_at']

	def __str__(self) -> str:
		return self.title


class DocumentIngestionJob(models.Model):
	class Status(models.TextChoices):
		QUEUED = 'queued', 'Queued'
		RUNNING = 'running', 'Running'
		SUCCEEDED = 'succeeded', 'Succeeded'
		FAILED = 'failed', 'Failed'

	source_dir = models.CharField(max_length=500, default='tax_doc')
	owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='document_ingestion_jobs')
	requested_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='requested_document_ingestion_jobs',
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
	total_files = models.PositiveIntegerField(default=0)
	processed_files = models.PositiveIntegerField(default=0)
	created_documents = models.PositiveIntegerField(default=0)
	updated_documents = models.PositiveIntegerField(default=0)
	current_file_name = models.CharField(max_length=255, blank=True)
	error_message = models.TextField(blank=True)
	started_at = models.DateTimeField(blank=True, null=True)
	finished_at = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self) -> str:
		return f'{self.source_dir} [{self.status}]'
