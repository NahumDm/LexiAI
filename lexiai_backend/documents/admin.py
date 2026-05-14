from django.contrib import admin

from .models import Document, DocumentIngestionJob


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ('id', 'title', 'owner', 'status', 'page_count', 'file_size', 'updated_at')
	list_display_links = ('id', 'title')
	list_filter = ('status', 'created_at', 'updated_at')
	search_fields = ('title', 'description', 'owner__email', 'metadata')
	list_select_related = ('owner',)
	autocomplete_fields = ('owner',)
	readonly_fields = ('extracted_text', 'analysis_summary', 'page_count', 'file_size', 'created_at', 'updated_at')
	date_hierarchy = 'created_at'
	list_per_page = 50
	ordering = ('-updated_at',)


@admin.register(DocumentIngestionJob)
class DocumentIngestionJobAdmin(admin.ModelAdmin):
	list_display = (
		'id', 'source_dir', 'owner', 'requested_by', 'status',
		'processed_files', 'total_files', 'created_documents', 'updated_documents',
		'started_at', 'finished_at',
	)
	list_filter = ('status', 'created_at', 'finished_at')
	search_fields = ('source_dir', 'owner__email', 'requested_by__email', 'error_message')
	list_select_related = ('owner', 'requested_by')
	autocomplete_fields = ('owner', 'requested_by')
	readonly_fields = (
		'status', 'total_files', 'processed_files', 'created_documents', 'updated_documents',
		'current_file_name', 'error_message', 'started_at', 'finished_at',
		'created_at', 'updated_at',
	)
	date_hierarchy = 'created_at'
	list_per_page = 50
	ordering = ('-created_at',)
