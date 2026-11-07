from rest_framework import serializers

from .notices import layout_notices
from .models import ContextSource, GeneratedDocument, JobPosting, ParsedResume


class ParsedResumeSerializer(serializers.ModelSerializer):
    layout_notices = serializers.SerializerMethodField()

    class Meta:
        model = ParsedResume
        fields = ['id', 'resume', 'content', 'layout', 'layout_notices', 'updated_at']
        read_only_fields = fields

    def get_layout_notices(self, obj):
        return layout_notices(obj.content, obj.layout)


class ParsedResumeSummarySerializer(serializers.ModelSerializer):
    """Which resumes have been parsed, without the bulky content."""

    layout_notices = serializers.SerializerMethodField()

    class Meta:
        model = ParsedResume
        fields = ['id', 'resume', 'layout_notices', 'updated_at']
        read_only_fields = fields

    def get_layout_notices(self, obj):
        return layout_notices(obj.content, obj.layout)


class ContextSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContextSource
        fields = ['id', 'kind', 'label', 'url', 'status', 'error', 'last_synced_at', 'created_at']
        read_only_fields = ['id', 'status', 'error', 'last_synced_at', 'created_at']


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    layout_notices = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedDocument
        fields = [
            'id', 'job_posting', 'resume', 'kind', 'status', 'content', 'layout', 'markdown',
            'layout_notices', 'unsupported_claims', 'version', 'edited', 'error', 'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'job_posting', 'resume', 'kind', 'status', 'layout', 'layout_notices',
            'unsupported_claims', 'version', 'edited', 'error', 'created_at', 'updated_at',
        ]

    def get_layout_notices(self, obj):
        if obj.kind != 'resume':
            return []
        return layout_notices(obj.content, obj.layout)


class JobPostingSerializer(serializers.ModelSerializer):
    documents = GeneratedDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = JobPosting
        fields = ['id', 'title', 'company', 'description', 'created_at', 'documents']
        read_only_fields = ['id', 'created_at', 'documents']
