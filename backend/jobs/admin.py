from django.contrib import admin, messages

from pipeline.tasks.daily_run import daily_run
from .models import Agent, Application, JobSeen, RunLog, Search


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'active', 'created_at')
    list_filter = ('active',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    actions = ['activate_agents', 'deactivate_agents']

    @admin.action(description='Activate selected agents')
    def activate_agents(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description='Deactivate selected agents')
    def deactivate_agents(self, request, queryset):
        queryset.update(active=False)


@admin.register(Search)
class SearchAdmin(admin.ModelAdmin):
    list_display = ('label', 'agent', 'active', 'schedule_enabled', 'daily_target', 'created_at')
    list_filter = ('active', 'schedule_enabled')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    actions = ['activate_searches', 'deactivate_searches', 'trigger_run']

    @admin.action(description='Activate selected searches')
    def activate_searches(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description='Deactivate selected searches')
    def deactivate_searches(self, request, queryset):
        queryset.update(active=False)

    @admin.action(description='Trigger run now')
    def trigger_run(self, request, queryset):
        triggered = 0
        for search in queryset:
            if not search.active:
                self.message_user(
                    request,
                    f'Skipped "{search}" — inactive.',
                    level=messages.WARNING,
                )
                continue
            if not search.agent.active:
                self.message_user(
                    request,
                    f'Skipped "{search}" — agent is inactive.',
                    level=messages.WARNING,
                )
                continue
            daily_run.delay(search_id=search.pk)
            triggered += 1

        if triggered:
            self.message_user(
                request,
                f'Triggered run for {triggered} search(es).',
                level=messages.SUCCESS,
            )


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


@admin.register(RunLog)
class RunLogAdmin(admin.ModelAdmin):
    list_display = ('search', 'status', 'jobs_fetched', 'jobs_applied', 'jobs_failed', 'jobs_skipped', 'run_at')
    list_filter = ('status',)
    ordering = ('-run_at',)
    readonly_fields = ('run_at', 'jobs_fetched', 'jobs_scored', 'jobs_applied', 'jobs_failed', 'jobs_skipped')


@admin.register(JobSeen)
class JobSeenAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'user', 'seen_at')
    ordering = ('-seen_at',)
    readonly_fields = ('seen_at',)