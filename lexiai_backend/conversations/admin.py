from django.contrib import admin

from .models import Conversation, ConversationMessage


class ConversationMessageInline(admin.TabularInline):
	model = ConversationMessage
	extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
	list_display = ('title', 'owner', 'document', 'status', 'updated_at')
	search_fields = ('title', 'owner__email', 'summary')
	list_filter = ('status', 'created_at', 'updated_at')
	inlines = [ConversationMessageInline]


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
	list_display = ('conversation', 'sender', 'created_at')
	search_fields = ('conversation__title', 'content')
	list_filter = ('sender', 'created_at')
