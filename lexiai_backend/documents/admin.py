from django.contrib import admin

from .models import Document, DocumentIngestionJob


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ('title', 'owner', 'status', 'updated_at')
	search_fields = ('title', 'owner__email', 'description')
	list_filter = ('status', 'created_at', 'updated_at')


@admin.register(DocumentIngestionJob)
class DocumentIngestionJobAdmin(admin.ModelAdmin):
	list_display = ('id', 'source_dir', 'owner', 'status', 'processed_files', 'total_files', 'created_at')
	search_fields = ('source_dir', 'owner__email', 'requested_by__email')
	list_filter = ('status',)
