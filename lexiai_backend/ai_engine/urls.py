from django.urls import path

from ai_engine.views import AskView, ChatAskView, ChatFeedbackView, analytics_view

urlpatterns = [
	path('ask/', AskView.as_view(), name='ask'),
	path('chat/<int:conversation_pk>/ask/', ChatAskView.as_view(), name='chat-ask'),
	path('chat/feedback/<int:query_log_pk>/', ChatFeedbackView.as_view(), name='chat-feedback'),
	path('ai/analytics/', analytics_view, name='ai-analytics'),
]
