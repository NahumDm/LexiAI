from __future__ import annotations

from rest_framework import generics, permissions

from .models import Document
from .serializers import DocumentSerializer


class DocumentQuerysetMixin:
    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)


class DocumentListCreateView(DocumentQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class DocumentDetailView(DocumentQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
