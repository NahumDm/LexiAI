from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document
from .models import DocumentIngestionJob
from .serializers import AdminDocumentSerializer, DocumentIngestionJobSerializer, DocumentSerializer
from .tasks import process_tax_document_ingestion_job

logger = logging.getLogger(__name__)


class DocumentQuerysetMixin:
    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)


class DocumentListCreateView(DocumentQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        document = serializer.save()
        logger.info(
            'Document upload received: id=%s owner_id=%s title=%s',
            document.pk,
            document.owner_id,
            document.title,
        )
        from ai_engine.tasks import embed_document_chunks

        transaction.on_commit(lambda: embed_document_chunks.delay(document.pk))


class DocumentDetailView(DocumentQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class AdminDocumentReprocessView(APIView):
    """
    POST /api/v1/documents/<id>/ingest/

    Admin-only: re-queue chunking + embedding for an existing document.
    Reuses ``ai_engine.tasks.embed_document_chunks`` (same pipeline as
    ``DocumentListCreateView`` uploads). ``DocumentIngestionJob`` remains
    directory-based bulk import only — it is not used for per-document reprocess.

    Response includes the Celery task id as ``job_id`` for correlation with
    workers / Flower.
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk, *args, **kwargs):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not (document.extracted_text or '').strip():
            return Response(
                {'detail': 'Document has no extracted text to reprocess.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from ai_engine.tasks import embed_document_chunks

        try:
            async_result = embed_document_chunks.delay(document.pk)
            task_id = async_result.id
        except Exception as exc:
            logger.exception('Admin reprocess: failed to queue embed_document_chunks: %s', exc)
            return Response(
                {'detail': 'Could not queue reprocessing task.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                'message': 'Reprocessing started',
                'document_id': document.pk,
                'job_id': task_id,
                'status': 'queued',
            },
            status=status.HTTP_200_OK,
        )


def _global_document_admin_stats() -> dict[str, int]:
    """
    System-wide document counts for admin stat cards (not affected by ?search=).
    Bucket rules align with AdminDocumentSerializer pipeline `status`.
    """
    qs = Document.objects.all()
    total = qs.count()
    failed_q = (
        Q(metadata__embedding_failed=True)
        | Q(metadata__ingestion_failed=True)
        | Q(metadata__failed=True)
    )
    failed = qs.filter(failed_q).count()
    ready = qs.filter(status=Document.Status.READY).count()
    processing = qs.filter(status=Document.Status.PROCESSING).count()
    archived = qs.filter(status=Document.Status.ARCHIVED).count()
    pending = qs.filter(status=Document.Status.UPLOADED).exclude(failed_q).count()
    return {
        'total': total,
        'ready': ready,
        'processing': processing,
        'pending': pending,
        'failed': failed,
        'archived': archived,
    }


class AdminDocumentListView(generics.ListAPIView):
    """
    GET /api/v1/documents/admin/
    
    Admin-only list of EVERY document on the system, regardless of owner.
    Differs from `DocumentListCreateView`, which is intentionally scoped
    by `owner=request.user` so a regular user can only see their own
    uploads. The admin dashboard needs the global view to compute counts
    correctly.
    
    Optional `?search=` does an `icontains` match against **title** only.

    Response envelope (admin SPA contract):
        {
          "count": <number of rows matching search>,
          "results": [ ... ],
          "stats": { "total", "ready", "processing", "pending", "failed", "archived" }
        }
    `stats` are always GLOBAL so dashboard cards stay truthful while the
    table reflects `?search=`.

    Pagination is disabled here so the admin SPA can compute per-status
    counts (ready / processing / failed / awaiting) from a complete
    result set; DRF's default 20-row page would truncate them. If
    document volume ever justifies pagination, add a dedicated
    `documents/admin/stats/` endpoint first, THEN paginate this view.
    """

    serializer_class = AdminDocumentSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = None

    def get_queryset(self):
        # `select_related('owner')` keeps the per-row queries down — the admin
        # serializer doesn't currently dereference owner, but ingestion-status
        # joins are likely to in the near future, and this is cheap.
        queryset = Document.objects.select_related('owner').all().order_by('-updated_at', '-created_at')
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(title__icontains=search)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                'count': queryset.count(),
                'results': serializer.data,
                'stats': _global_document_admin_stats(),
            }
        )


class AdminDocumentDestroyView(generics.DestroyAPIView):
    """
    DELETE /api/v1/documents/admin/<id>/

    Admin-only hard delete for any document (global), regardless of owner.
    Regular `DELETE /documents/<id>/` remains owner-scoped for normal users.
    """

    permission_classes = [permissions.IsAdminUser]
    queryset = Document.objects.all()
    lookup_field = 'pk'


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
