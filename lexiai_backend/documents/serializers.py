from __future__ import annotations

from rest_framework import serializers

from .models import Document


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