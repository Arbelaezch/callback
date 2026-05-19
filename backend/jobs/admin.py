from django.contrib import admin
from django.utils import timezone

from .models import JobSearch, JobSeen, Application, DailyRunLog


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'active', 'daily_limit', 'created_at')
    list_filter = ('active',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    actions = ['activate_searches', 'deactivate_searches']

    @admin.action(description='Activate selected searches')
    def activate_searches(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description='Deactivate selected searches')
    def deactivate_searches(self, request, queryset):
        queryset.update(active=False)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('company', 'role_title', 'status', 'submission_method', 'llm_score', 'applied_at')
    list_filter = ('status', 'submission_method', 'remote_type', 'source')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'applied_at', 'lambda_invocation_id')
    actions = ['mark_failed', 'mark_skipped']

    @admin.action(description='Mark selected applications as failed')
    def mark_failed(self, request, queryset):
        queryset.update(status='failed')

    @admin.action(description='Mark selected applications as skipped')
    def mark_skipped(self, request, queryset):
        queryset.update(status='skipped')


@admin.register(DailyRunLog)
class DailyRunLogAdmin(admin.ModelAdmin):
    list_display = ('job_search', 'status', 'jobs_fetched', 'jobs_applied', 'jobs_failed', 'jobs_skipped', 'run_at')
    list_filter = ('status',)
    ordering = ('-run_at',)
    readonly_fields = ('run_at', 'jobs_fetched', 'jobs_scored', 'jobs_applied', 'jobs_failed', 'jobs_skipped')


@admin.register(JobSeen)
class JobSeenAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'job_search', 'seen_at')
    ordering = ('-seen_at',)
    readonly_fields = ('seen_at',)