from __future__ import annotations

from rest_framework import serializers

from ai_engine.models import QueryFeedback, QueryLog


class ChatQuerySerializer(serializers.Serializer):
	"""Serializer for chat query requests."""
	query = serializers.CharField(max_length=2000, required=True, allow_blank=True)
	top_k = serializers.IntegerField(min_value=1, max_value=20, required=False, default=3)
	min_similarity = serializers.FloatField(min_value=0.0, max_value=1.0, required=False, default=0.2)


class ChatResponseSerializer(serializers.Serializer):
	"""Serializer for chat responses with confidence and citations."""
	answer = serializers.CharField(allow_blank=True)
	sources = serializers.ListField()
	model_used = serializers.CharField()
	tokens_used = serializers.DictField()
	retrieval_confidence = serializers.FloatField()
	confidence = serializers.FloatField()
	confidence_percent = serializers.FloatField(required=False)
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
	top_k = serializers.IntegerField(min_value=1, max_value=10, required=False, default=3)
	min_similarity = serializers.FloatField(min_value=0.0, max_value=1.0, required=False, default=0.2)


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
	confidence = serializers.FloatField(
		help_text='Max cosine among passages used for the answer, or routing score when no LLM.',
	)
	confidence_percent = serializers.FloatField(help_text='confidence × 100, rounded to 2 decimals.')
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


class AdminQueryLogSerializer(serializers.ModelSerializer):
	"""
	Read-only serializer for the admin Query Logs page.

	Maps the QueryLog model to the field names the admin SPA expects:
	`query` (←query_text) and `response` (←llm_response). Both `source`
	naming and the original column names are preserved for backwards
	compatibility with any internal tooling that already consumes
	QueryLog rows directly.
	"""

	query = serializers.CharField(source='query_text', read_only=True)
	response = serializers.CharField(source='llm_response', read_only=True)
	user_email = serializers.EmailField(source='user.email', read_only=True)

	class Meta:
		model = QueryLog
		fields = (
			'id',
			'user',
			'user_email',
			'query',
			'response',
			'llm_model',
			'retrieval_confidence',
			'latency_ms',
			'created_at',
		)
		read_only_fields = fields


class AdminQueryFeedbackSerializer(serializers.ModelSerializer):
	"""
	Read-only serializer for the admin Feedback page.

	Renames the storage-level `rating` enum into the boolean `is_helpful`
	the admin SPA renders (thumbs-up = helpful = True; thumbs-down =
	False). Joins to the associated QueryLog to surface `query` and
	`response` text inline so the admin page doesn't need a second
	round-trip per row.
	"""

	is_helpful = serializers.SerializerMethodField()
	query = serializers.CharField(source='query_log.query_text', read_only=True)
	response = serializers.CharField(source='query_log.llm_response', read_only=True)
	user_email = serializers.EmailField(source='user.email', read_only=True)

	class Meta:
		model = QueryFeedback
		fields = (
			'id',
			'query_log',
			'user',
			'user_email',
			'query',
			'response',
			'is_helpful',
			'rating',
			'comment',
			'created_at',
		)
		read_only_fields = fields

	def get_is_helpful(self, obj) -> bool:
		return obj.rating == QueryFeedback.Rating.THUMBS_UP
