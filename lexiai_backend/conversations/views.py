from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from .models import Conversation, ConversationMessage
from .serializers import ConversationMessageSerializer, ConversationSerializer


class ConversationQuerysetMixin:
    def get_queryset(self):
        return Conversation.objects.filter(owner=self.request.user).select_related('document')


class ConversationListCreateView(ConversationQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]


class ConversationDetailView(ConversationQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]


class ConversationMessageListCreateView(generics.ListCreateAPIView):
    serializer_class = ConversationMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_conversation(self):
        return get_object_or_404(Conversation, pk=self.kwargs['conversation_pk'], owner=self.request.user)

    def get_queryset(self):
        return self.get_conversation().messages.all()

    def perform_create(self, serializer):
        serializer.save(conversation=self.get_conversation())

