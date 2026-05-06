from __future__ import annotations

from django.conf import settings
from django.db import models


class DocumentChunk(models.Model):
	"""
	Represents a semantically chunked segment of a document.
	Stores the text, embedding vector, and metadata for retrieval.
	"""
	document = models.ForeignKey(
		'documents.Document',
		on_delete=models.CASCADE,
		related_name='chunks',
	)
	document_owner = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='document_chunks',
	)
	sequence_index = models.PositiveIntegerField()
	content = models.TextField()
	token_count = models.PositiveIntegerField()
	embedding = models.BinaryField(null=True, blank=True)
	metadata = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['document', 'sequence_index']
		indexes = [
			models.Index(fields=['document', 'sequence_index']),
			models.Index(fields=['document_owner']),
		]

	def __str__(self) -> str:
		return f'{self.document.title} chunk {self.sequence_index}'


class QueryLog(models.Model):
	"""
	Tracks AI queries for analytics and monitoring.
	"""
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='ai_queries',
	)
	conversation = models.ForeignKey(
		'conversations.Conversation',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='ai_queries',
	)
	query_text = models.TextField()
	query_embedding = models.BinaryField(null=True, blank=True)
	retrieved_chunk_ids = models.JSONField(default=list, blank=True)
	llm_response = models.TextField()
	llm_model = models.CharField(max_length=100, default='mistral')
	retrieval_confidence = models.FloatField(default=0.0, help_text='Average relevance score of retrieved chunks')
	latency_ms = models.PositiveIntegerField()
	token_usage = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self) -> str:
		return f'Query by {self.user.email} at {self.created_at}'

	@property
	def average_confidence(self) -> float:
		"""Get average confidence of this query's retrieval."""
		return self.retrieval_confidence


class QueryFeedback(models.Model):
	"""
	User feedback on AI query responses for quality monitoring.
	"""
	class Rating(models.TextChoices):
		THUMBS_UP = 'up', 'Helpful'
		THUMBS_DOWN = 'down', 'Not Helpful'

	query_log = models.OneToOneField(
		QueryLog,
		on_delete=models.CASCADE,
		related_name='feedback',
	)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='query_feedback',
	)
	rating = models.CharField(max_length=10, choices=Rating.choices)
	comment = models.TextField(blank=True, help_text='Optional feedback comment')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self) -> str:
		return f'{self.user.email} - {self.rating} on query {self.query_log.id}'
