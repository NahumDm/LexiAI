from __future__ import annotations

from django.db import transaction

from .models import Conversation, ConversationMessage


@transaction.atomic
def create_conversation_message(
    *,
    conversation: Conversation,
    content: str,
    metadata: dict | None = None,
) -> ConversationMessage:
    message = ConversationMessage.objects.create(
        conversation=conversation,
        sender=ConversationMessage.Sender.USER,
        content=content,
        metadata=metadata or {},
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=['last_message_at'])
    return message