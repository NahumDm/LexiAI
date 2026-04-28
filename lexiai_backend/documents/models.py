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
