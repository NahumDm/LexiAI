from __future__ import annotations

from django.db import transaction
from rest_framework import generics, permissions

from .models import Document
from .models import DocumentIngestionJob
from .serializers import DocumentIngestionJobSerializer, DocumentSerializer
from .tasks import process_tax_document_ingestion_job
from ai_engine.tasks import embed_document_chunks


class DocumentQuerysetMixin:
    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)


class DocumentListCreateView(DocumentQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        document = serializer.save()
        transaction.on_commit(lambda: embed_document_chunks.delay(document.pk))


class DocumentDetailView(DocumentQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class AdminDocumentIngestionJobListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentIngestionJobSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return DocumentIngestionJob.objects.select_related('owner', 'requested_by')

    def perform_create(self, serializer):
        job = serializer.save()
        transaction.on_commit(lambda: process_tax_document_ingestion_job.delay(job.pk))
        job.refresh_from_db()


class AdminDocumentIngestionJobDetailView(generics.RetrieveAPIView):
    serializer_class = DocumentIngestionJobSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return DocumentIngestionJob.objects.select_related('owner', 'requested_by')
