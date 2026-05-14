from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_engine.models import DocumentChunk

from .models import Document
from .models import DocumentIngestionJob
from .serializers import AdminDocumentSerializer, DocumentIngestionJobSerializer, DocumentSerializer
from .services import INGESTION_STATUS_PENDING, set_document_ingestion_status
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
        set_document_ingestion_status(document, INGESTION_STATUS_PENDING)
        from ai_engine.tasks import embed_document_chunks

        logger.info(
            '[INGESTION] DISPATCH_ON_COMMIT_REGISTER document_id=%s owner_id=%s DEBUG=%s',
            document.pk,
            document.owner_id,
            settings.DEBUG,
        )

        def _queue_embed(doc_pk: int, owner_id: int) -> None:
            logger.info(
                '[INGESTION] ON_COMMIT_FIRE document_id=%s owner_id=%s DEBUG=%s',
                doc_pk,
                owner_id,
                settings.DEBUG,
            )
            try:
                if settings.DEBUG:
                    logger.info(
                        '[INGESTION] DISPATCH_SYNC_DEBUG apply() document_id=%s owner_id=%s',
                        doc_pk,
                        owner_id,
                    )
                    sync_result = embed_document_chunks.apply(args=[doc_pk])
                    logger.info(
                        '[INGESTION] DISPATCH_SYNC_AFTER task_id=%s document_id=%s owner_id=%s',
                        sync_result.id,
                        doc_pk,
                        owner_id,
                    )
                    sync_result.get()
                else:
                    logger.info(
                        '[INGESTION] DISPATCH_DELAY_BEFORE document_id=%s owner_id=%s',
                        doc_pk,
                        owner_id,
                    )
                    async_result = embed_document_chunks.delay(doc_pk)
                    logger.info(
                        '[INGESTION] DISPATCH_DELAY_AFTER task_id=%s document_id=%s owner_id=%s',
                        async_result.id,
                        doc_pk,
                        owner_id,
                    )
            except Exception as exc:
                logger.exception(
                    '[INGESTION] DISPATCH_FAILED document_id=%s owner_id=%s DEBUG=%s — '
                    'ingestion will not run until re-queued: %s',
                    doc_pk,
                    owner_id,
                    settings.DEBUG,
                    exc,
                )

        transaction.on_commit(
            lambda: _queue_embed(document.pk, document.owner_id),
        )


class DocumentDetailView(DocumentQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class DocumentLibraryStatsView(APIView):
    """
    GET /api/v1/documents/library-stats/

    Authenticated: returns chunk counts for the current user (ingestion health).
    Use after upload to confirm ``embed_document_chunks`` populated ``DocumentChunk`` rows.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        chunk_total = DocumentChunk.objects.filter(document_owner=user).count()
        docs = (
            Document.objects.filter(owner=user)
            .annotate(chunk_count=Count('chunks'))
            .order_by('-updated_at')
            .values('id', 'title', 'status', 'chunk_count', 'metadata', 'updated_at')[:200]
        )
        return Response(
            {
                'owner_id': user.pk,
                'chunk_count_total': chunk_total,
                'document_count': Document.objects.filter(owner=user).count(),
                'documents': list(docs),
            }
        )


class UserChunkDebugView(APIView):
    """
    GET /api/v1/debug/chunks/<user_id>/

    Returns ``DocumentChunk`` count for that user (RAG ingestion verification).
    Callers may only query their own ``user_id`` unless ``request.user.is_staff``.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id: int, *args, **kwargs):
        if request.user.pk != user_id and not request.user.is_staff:
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        chunk_count = DocumentChunk.objects.filter(document_owner_id=user_id).count()
        return Response({'user_id': user_id, 'chunk_count': chunk_count})


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

        set_document_ingestion_status(document, INGESTION_STATUS_PENDING)
        try:
            if settings.DEBUG:
                logger.info(
                    '[INGESTION] ADMIN_REPROCESS_SYNC_DEBUG document_id=%s',
                    document.pk,
                )
                sync_result = embed_document_chunks.apply(args=[document.pk])
                task_id = sync_result.id
                sync_result.get()
            else:
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
