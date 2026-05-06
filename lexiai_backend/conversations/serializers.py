from __future__ import annotations

from rest_framework import serializers

from documents.models import Document

from .models import Conversation, ConversationMessage
from .services import create_conversation_message


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ('id', 'sender', 'content', 'metadata', 'created_at')
        read_only_fields = ('id', 'sender', 'created_at')

    def validate(self, attrs):
        sender = self.initial_data.get('sender')
        if sender not in (None, '', ConversationMessage.Sender.USER):
            raise serializers.ValidationError({'sender': 'Only user messages can be created through this endpoint.'})
        return attrs

    def create(self, validated_data):
        conversation = validated_data.pop('conversation', None)
        if conversation is None:
            raise serializers.ValidationError({'conversation': 'Conversation is required.'})
        return create_conversation_message(
            conversation=conversation,
            content=validated_data['content'],
            metadata=validated_data.get('metadata', {}),
        )


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