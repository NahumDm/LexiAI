from django.urls import path

from .views import (
    AdminDocumentDestroyView,
    AdminDocumentIngestionJobDetailView,
    AdminDocumentIngestionJobListCreateView,
    AdminDocumentListView,
    AdminDocumentReprocessView,
    DocumentDetailView,
    DocumentLibraryStatsView,
    DocumentListCreateView,
)

urlpatterns = [
    path('', DocumentListCreateView.as_view(), name='document-list'),
    path('library-stats/', DocumentLibraryStatsView.as_view(), name='document-library-stats'),
    path('<int:pk>/ingest/', AdminDocumentReprocessView.as_view(), name='document-reprocess'),
    path('<int:pk>/', DocumentDetailView.as_view(), name='document-detail'),
    # Admin-only GLOBAL listing. Registered BEFORE `admin/ingestions/` so the
    # router prefix-resolves correctly: '' first, then '<int:pk>/', then the
    # `admin/...` namespace.
    path('admin/', AdminDocumentListView.as_view(), name='admin-document-list'),
    path('admin/<int:pk>/', AdminDocumentDestroyView.as_view(), name='admin-document-destroy'),
    path('admin/ingestions/', AdminDocumentIngestionJobListCreateView.as_view(), name='document-ingestion-list'),
    path('admin/ingestions/<int:pk>/', AdminDocumentIngestionJobDetailView.as_view(), name='document-ingestion-detail'),
]