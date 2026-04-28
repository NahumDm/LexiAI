from __future__ import annotations

from django.conf import settings
from django.db import models


class Conversation(models.Model):
	class Status(models.TextChoices):
		OPEN = 'open', 'Open'
		CLOSED = 'closed', 'Closed'
		ARCHIVED = 'archived', 'Archived'

	owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
	title = models.CharField(max_length=255)
	document = models.ForeignKey(
		'documents.Document',
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='conversations',
	)
	summary = models.TextField(blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
	metadata = models.JSONField(default=dict, blank=True)
	last_message_at = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-updated_at', '-created_at']

	def __str__(self) -> str:
		return self.title


class ConversationMessage(models.Model):
	class Sender(models.TextChoices):
		USER = 'user', 'User'
		ASSISTANT = 'assistant', 'Assistant'
		SYSTEM = 'system', 'System'

	conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
	sender = models.CharField(max_length=20, choices=Sender.choices)
	content = models.TextField()
	metadata = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['created_at']

	def __str__(self) -> str:
		return f'{self.sender}: {self.content[:40]}'
