from __future__ import annotations

from rest_framework import serializers

from ai_engine.models import QueryFeedback


class ChatQuerySerializer(serializers.Serializer):
	"""Serializer for chat query requests."""
	query = serializers.CharField(max_length=2000, required=True)
	top_k = serializers.IntegerField(min_value=1, max_value=20, required=False, default=5)


class ChatResponseSerializer(serializers.Serializer):
	"""Serializer for chat responses with confidence and citations."""
	answer = serializers.CharField()
	sources = serializers.ListField()
	model_used = serializers.CharField()
	tokens_used = serializers.DictField()
	retrieval_confidence = serializers.FloatField()
	warnings = serializers.ListField(required=False, allow_empty=True)


class QueryFeedbackSerializer(serializers.ModelSerializer):
	"""Serializer for rating AI responses."""

	class Meta:
		model = QueryFeedback
		fields = ('id', 'rating', 'comment', 'created_at')
		read_only_fields = ('id', 'created_at')

	def create(self, validated_data):
		validated_data['user'] = self.context['request'].user
		return super().create(validated_data)
