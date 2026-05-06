from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from .models import Conversation, ConversationMessage
from .permissions import IsConversationOwner
from .selectors import get_conversation_messages, get_user_conversations
from .serializers import ConversationMessageSerializer, ConversationSerializer


class ConversationQuerysetMixin:
    def get_queryset(self):
        return get_user_conversations(self.request.user)


class ConversationListCreateView(ConversationQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]


class ConversationDetailView(ConversationQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated, IsConversationOwner]

    def get_object(self):
        conversation = get_object_or_404(Conversation.objects.select_related('document'), pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, conversation)
        return conversation


class ConversationMessageListCreateView(generics.ListCreateAPIView):
    serializer_class = ConversationMessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsConversationOwner]

    def get_conversation(self):
        if hasattr(self, '_conversation') and getattr(self, '_conversation') is not None:
            return self._conversation
        conversation = get_object_or_404(Conversation, pk=self.kwargs['conversation_pk'])
        self.check_object_permissions(self.request, conversation)
        self._conversation = conversation
        return conversation

    def get_queryset(self):
        return get_conversation_messages(self.get_conversation())

    def perform_create(self, serializer):
        serializer.save(conversation=self.get_conversation())

