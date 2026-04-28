from __future__ import annotations

from rest_framework import serializers

from .models import Conversation, ConversationMessage


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ('id', 'sender', 'content', 'metadata', 'created_at')
        read_only_fields = ('id', 'created_at')


class ConversationSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source='document.title', read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            'id',
            'title',
            'document',
            'document_title',
            'summary',
            'status',
            'metadata',
            'message_count',
            'last_message_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'document_title', 'message_count', 'created_at', 'updated_at')

    def create(self, validated_data):
        request = self.context['request']
        return Conversation.objects.create(owner=request.user, **validated_data)

    def get_message_count(self, instance):
        return instance.messages.count()