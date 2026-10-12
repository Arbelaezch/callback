from rest_framework import serializers

from .models import ContextSource, GeneratedDocument, JobPosting, ParsedResume


class ParsedResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParsedResume
        fields = ['id', 'resume', 'content', 'layout', 'updated_at']
        read_only_fields = fields


class ParsedResumeSummarySerializer(serializers.ModelSerializer):
    """Which resumes have been parsed, without the bulky content."""

    class Meta:
        model = ParsedResume
        fields = ['id', 'resume', 'updated_at']
        read_only_fields = fields


class ContextSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContextSource
        fields = ['id', 'kind', 'label', 'url', 'status', 'error', 'last_synced_at', 'created_at']
        read_only_fields = ['id', 'status', 'error', 'last_synced_at', 'created_at']


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedDocument
        fields = [
            'id', 'job_posting', 'kind', 'status', 'content', 'layout', 'markdown',
            'unsupported_claims', 'version', 'edited', 'error', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'job_posting', 'kind', 'status', 'layout', 'unsupported_claims',
            'version', 'edited', 'error', 'created_at', 'updated_at',
        ]


class JobPostingSerializer(serializers.ModelSerializer):
    documents = GeneratedDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = JobPosting
        fields = ['id', 'title', 'company', 'description', 'created_at', 'documents']
        read_only_fields = ['id', 'created_at', 'documents']
