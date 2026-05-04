from django.urls import path

from .views import (
    AdminDocumentIngestionJobDetailView,
    AdminDocumentIngestionJobListCreateView,
    DocumentDetailView,
    DocumentListCreateView,
)

urlpatterns = [
    path('', DocumentListCreateView.as_view(), name='document-list'),
    path('<int:pk>/', DocumentDetailView.as_view(), name='document-detail'),
    path('admin/ingestions/', AdminDocumentIngestionJobListCreateView.as_view(), name='document-ingestion-list'),
    path('admin/ingestions/<int:pk>/', AdminDocumentIngestionJobDetailView.as_view(), name='document-ingestion-detail'),
]