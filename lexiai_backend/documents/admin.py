from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ('title', 'owner', 'status', 'updated_at')
	search_fields = ('title', 'owner__email', 'description')
	list_filter = ('status', 'created_at', 'updated_at')
