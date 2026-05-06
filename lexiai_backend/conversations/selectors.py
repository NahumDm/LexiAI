from __future__ import annotations

from django.db.models import Count, QuerySet

from .models import Conversation, ConversationMessage


def get_user_conversations(user) -> QuerySet[Conversation]:
    return (
        Conversation.objects.filter(owner=user)
        .select_related('document')
        .annotate(message_count=Count('messages'))
    )


def get_user_conversation(user, conversation_id: int) -> Conversation | None:
    return get_user_conversations(user).filter(pk=conversation_id).first()


def get_conversation_messages(conversation: Conversation) -> QuerySet[ConversationMessage]:
    return conversation.messages.select_related('conversation')