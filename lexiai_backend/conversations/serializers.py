from __future__ import annotations

from rest_framework import serializers

from documents.models import Document

from .models import Conversation, ConversationMessage


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ('id', 'sender', 'content', 'metadata', 'created_at')
        read_only_fields = ('id', 'created_at')

    def validate_sender(self, value):
        if value != ConversationMessage.Sender.USER:
            raise serializers.ValidationError('Only user messages can be created through this endpoint.')
        return value


class ConversationSerializer(serializers.ModelSerializer):
    document = serializers.PrimaryKeyRelatedField(queryset=Document.objects.all(), required=False, allow_null=True)
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

    def validate_document(self, value):
        if value is not None and value.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError('You can only attach your own documents.')
        return value

    def get_message_count(self, instance):
        return getattr(instance, 'message_count', instance.messages.count())