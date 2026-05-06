from __future__ import annotations

from typing import TYPE_CHECKING

from ai_engine.models import DocumentChunk, QueryLog

if TYPE_CHECKING:
	from documents.models import Document


def get_document_chunks(document: Document) -> list[DocumentChunk]:
	"""Fetch all chunks for a document, ordered by sequence."""
	return DocumentChunk.objects.filter(document=document).order_by('sequence_index')


def get_chunks_count(document: Document) -> int:
	"""Get total chunk count for a document."""
	return DocumentChunk.objects.filter(document=document).count()


def get_user_query_logs(user, limit: int = 100) -> list[QueryLog]:
	"""Fetch recent query logs for a user."""
	return QueryLog.objects.filter(user=user).order_by('-created_at')[:limit]


def get_conversation_query_logs(conversation, limit: int = 50) -> list[QueryLog]:
	"""Fetch query logs for a specific conversation."""
	return QueryLog.objects.filter(conversation=conversation).order_by('-created_at')[:limit]
