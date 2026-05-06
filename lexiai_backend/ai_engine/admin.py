from django.contrib import admin

from ai_engine.models import DocumentChunk, QueryLog, QueryFeedback


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
	list_display = ('id', 'document', 'sequence_index', 'token_count', 'created_at')
	list_filter = ('created_at', 'document')
	search_fields = ('document__title', 'content')
	readonly_fields = ('created_at', 'updated_at')


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'conversation', 'llm_model', 'retrieval_confidence', 'latency_ms', 'created_at')
	list_filter = ('llm_model', 'created_at')
	search_fields = ('user__email', 'query_text')
	readonly_fields = ('created_at',)


@admin.register(QueryFeedback)
class QueryFeedbackAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'query_log', 'rating', 'created_at')
	list_filter = ('rating', 'created_at')
	search_fields = ('user__email', 'comment')
	readonly_fields = ('created_at',)
