from __future__ import annotations

from rest_framework import serializers

from ai_engine.models import QueryFeedback


class ChatQuerySerializer(serializers.Serializer):
	"""Serializer for chat query requests."""
	query = serializers.CharField(max_length=2000, required=True, allow_blank=True)
	top_k = serializers.IntegerField(min_value=1, max_value=20, required=False, default=5)


class ChatResponseSerializer(serializers.Serializer):
	"""Serializer for chat responses with confidence and citations."""
	answer = serializers.CharField(allow_blank=True)
	sources = serializers.ListField()
	model_used = serializers.CharField()
	tokens_used = serializers.DictField()
	retrieval_confidence = serializers.FloatField()
	warnings = serializers.ListField(required=False, allow_empty=True)
	query_id = serializers.IntegerField(required=False, allow_null=True, help_text='QueryLog PK for feedback')


class AskQuerySerializer(serializers.Serializer):
	"""Request serializer for ``POST /api/v1/ask/``.

	Empty queries are rejected at the validation boundary so the QA service
	never has to defensively handle them.
	"""
	query = serializers.CharField(max_length=2000, required=True, allow_blank=False, trim_whitespace=True)
	# Capped at 10 to limit per-request LLM token cost (context length scales
	# linearly with k) and to keep retrieval latency predictable.
	top_k = serializers.IntegerField(min_value=1, max_value=10, required=False, default=5)
	min_similarity = serializers.FloatField(min_value=0.0, max_value=1.0, required=False, default=0.0)


class AskSourceSerializer(serializers.Serializer):
	"""Citation descriptor for one retrieved chunk."""
	source_number = serializers.IntegerField()
	chunk_id = serializers.IntegerField()
	document_id = serializers.IntegerField()
	document_title = serializers.CharField(allow_null=True, allow_blank=True)
	relevance = serializers.FloatField()
	excerpt = serializers.CharField(allow_blank=True)


class AskResponseSerializer(serializers.Serializer):
	"""Response serializer for ``POST /api/v1/ask/`` (documents the public shape)."""
	answer = serializers.CharField(allow_blank=True)
	sources = AskSourceSerializer(many=True)
	model_used = serializers.CharField()
	retrieval_confidence = serializers.FloatField()
	latency_ms = serializers.IntegerField()
	warnings = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
	query_log_id = serializers.IntegerField(required=False, allow_null=True)


class QueryFeedbackSerializer(serializers.ModelSerializer):
	"""Serializer for rating AI responses."""

	class Meta:
		model = QueryFeedback
		fields = ('id', 'rating', 'comment', 'created_at')
		read_only_fields = ('id', 'created_at')

	def create(self, validated_data):
		request = self.context.get('request')
		user = getattr(request, 'user', None)
		if user is None or not getattr(user, 'is_authenticated', False):
			raise serializers.ValidationError('Authenticated user required to submit feedback')
		validated_data['user'] = user
		return super().create(validated_data)
