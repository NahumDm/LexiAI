from django.contrib import admin

from ai_engine.models import DocumentChunk, QueryFeedback, QueryLog


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
	list_display = ('id', 'document', 'document_owner', 'sequence_index', 'token_count', 'created_at')
	list_display_links = ('id',)
	list_filter = ('created_at',)
	search_fields = ('document__title', 'document_owner__email', 'content')
	list_select_related = ('document', 'document_owner')
	autocomplete_fields = ('document', 'document_owner')
	# Embedding is a BinaryField — never useful in the form, would crash the admin.
	exclude = ('embedding',)
	readonly_fields = ('token_count', 'metadata', 'created_at', 'updated_at')
	date_hierarchy = 'created_at'
	list_per_page = 100
	ordering = ('document', 'sequence_index')


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
	list_display = (
		'id', 'user', 'conversation', 'llm_model',
		'retrieval_confidence', 'latency_ms', 'created_at',
	)
	list_filter = ('llm_model', 'created_at')
	search_fields = ('user__email', 'query_text', 'llm_response')
	list_select_related = ('user', 'conversation')
	autocomplete_fields = ('user', 'conversation')
	exclude = ('query_embedding',)
	readonly_fields = (
		'query_text', 'llm_response', 'llm_model', 'retrieval_confidence',
		'latency_ms', 'retrieved_chunk_ids', 'token_usage', 'created_at',
	)
	date_hierarchy = 'created_at'
	list_per_page = 50
	ordering = ('-created_at',)


@admin.register(QueryFeedback)
class QueryFeedbackAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'query_log', 'rating', 'created_at')
	list_filter = ('rating', 'created_at')
	search_fields = ('user__email', 'comment', 'query_log__query_text')
	list_select_related = ('user', 'query_log')
	autocomplete_fields = ('user', 'query_log')
	readonly_fields = ('created_at', 'updated_at')
	date_hierarchy = 'created_at'
	list_per_page = 50
	ordering = ('-created_at',)
