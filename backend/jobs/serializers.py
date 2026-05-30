from rest_framework import serializers

from .models import Agent, Application, RunLog, Search


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = ('id', 'name', 'active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class RunLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RunLog
        fields = (
            'id',
            'run_at',
            'status',
            'jobs_fetched',
            'jobs_scored',
            'jobs_applied',
            'jobs_failed',
            'jobs_skipped',
            'error',
        )
        read_only_fields = fields


class SearchSerializer(serializers.ModelSerializer):
    """
    Full Search representation including last run info.
    last_run is populated from the _latest_run_list prefetch annotation
    in SearchListView — not a real model field.
    """
    last_run = serializers.SerializerMethodField()

    class Meta:
        model = Search
        fields = (
            'id',
            'label',
            'active',
            'schedule_enabled',
            'daily_target',
            'job_cooldown',
            'role_titles',
            'cities',
            'location_types',
            'seniority_levels',
            'years_experience',
            'salary_min',
            'excluded_companies',
            'resume',
            'portfolio',
            'cover_letter_sample',
            'created_at',
            'updated_at',
            'last_run',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'last_run')

    def get_last_run(self, obj):
        runs = getattr(obj, '_latest_run_list', None)
        if not runs:
            return None
        return RunLogSerializer(runs[0]).data


class ApplicationSerializer(serializers.ModelSerializer):
    search_label = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = (
            'id',
            'search_id',
            'search_label',
            'job_id',
            'job_url',
            'company',
            'role_title',
            'location',
            'remote_type',
            'salary_range',
            'status',
            'submission_method',
            'llm_score',
            'llm_score_reason',
            'failure_reason',
            'applied_at',
            'created_at',
        )
        read_only_fields = fields

    def get_search_label(self, obj):
        return obj.search.label or 'Search'


class ChoiceSerializer(serializers.Serializer):
    """Represents a single value/label choice pair."""
    value = serializers.CharField()
    label = serializers.CharField()