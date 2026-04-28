from django.urls import path

from .views import ConversationDetailView, ConversationListCreateView, ConversationMessageListCreateView

urlpatterns = [
    path('', ConversationListCreateView.as_view(), name='conversation-list'),
    path('<int:pk>/', ConversationDetailView.as_view(), name='conversation-detail'),
    path('<int:conversation_pk>/messages/', ConversationMessageListCreateView.as_view(), name='conversation-messages'),
]