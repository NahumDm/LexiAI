from __future__ import annotations

from django.core.management.base import CommandError
from rest_framework import serializers

from .models import Document, DocumentIngestionJob
from .services import resolve_ingestion_owner, resolve_ingestion_source


class DocumentSerializer(serializers.ModelSerializer):
    source_file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            'id',
            'title',
            'description',
            'source_file',
            'source_file_url',
            'extracted_text',
            'analysis_summary',
            'status',
            'metadata',
            'page_count',
            'file_size',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'source_file_url', 'created_at', 'updated_at')

    def get_source_file_url(self, instance):
        request = self.context.get('request')
        if not instance.source_file:
            return None
        url = instance.source_file.url
        return request.build_absolute_uri(url) if request else url

    def create(self, validated_data):
        request = self.context['request']
        return Document.objects.create(owner=request.user, **validated_data)


class DocumentIngestionJobSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(write_only=True, required=False, allow_blank=False)
    requested_by_email = serializers.EmailField(source='requested_by.email', read_only=True)
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = DocumentIngestionJob
        fields = (
            'id',
            'source_dir',
            'owner_email',
            'requested_by_email',
            'status',
            'total_files',
            'processed_files',
            'created_documents',
            'updated_documents',
            'current_file_name',
            'error_message',
            'progress_percent',
            'started_at',
            'finished_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'requested_by_email',
            'status',
            'total_files',
            'processed_files',
            'created_documents',
            'updated_documents',
            'current_file_name',
            'error_message',
            'progress_percent',
            'started_at',
            'finished_at',
            'created_at',
            'updated_at',
        )

    def get_progress_percent(self, instance):
        if not instance.total_files:
            return 0
        return round((instance.processed_files / instance.total_files) * 100, 2)

    def validate_source_dir(self, value):
        try:
            resolve_ingestion_source(value)
        except CommandError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def create(self, validated_data):
        owner_email = validated_data.pop('owner_email', None)
        try:
            owner = resolve_ingestion_owner(owner_email)
        except CommandError as exc:
            raise serializers.ValidationError({'owner_email': str(exc)}) from exc
        request = self.context['request']
        return DocumentIngestionJob.objects.create(
            source_dir=validated_data.get('source_dir', 'tax_doc'),
            owner=owner,
            requested_by=request.user,
        )