import logging

from django.db.models import OuterRef, Prefetch, Subquery
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from pipeline.tasks.daily_run import daily_run
from jobs.management.commands.sync_schedules import sync_schedules
from .models import Application, DailyRunLog, JobSearch

logger = logging.getLogger(__name__)


class ChoicesView(APIView):

    def get(self, request):
        """
        Returns all choice field options for the frontend.
        Add any new choice fields here as they're added to models.
        """
        return Response({
            'location_types': [
                {'value': value, 'label': label}
                for value, label in JobSearch.LOCATION_TYPE_CHOICES
            ],
            'seniority_levels': [
                {'value': value, 'label': label}
                for value, label in JobSearch.SENIORITY_CHOICES
            ],
            'application_statuses': [
                {'value': value, 'label': label}
                for value, label in Application.STATUS_CHOICES
            ],
            'submission_methods': [
                {'value': value, 'label': label}
                for value, label in Application.SUBMISSION_METHOD_CHOICES
            ],
            'remote_types': [
                {'value': value, 'label': label}
                for value, label in Application.REMOTE_TYPE_CHOICES
            ],
        })


class ApplicationListView(APIView):
    """
    GET /api/jobs/applications/
    Returns all applications for the authenticated user, newest first.
    Scoped to the user via job_search__user — users never see each other's data.

    TODO: Pagination
    """

    def get(self, request):
        logger.debug('[ApplicationListView] user=%s fetching applications', request.user.id)

        applications = (
            Application.objects
            .filter(job_search__user=request.user)
            .select_related('job_search')
            .order_by('-created_at')
        )

        data = [
            {
                'id': app.id,
                'job_search_id': app.job_search_id,
                'job_search_label': app.job_search.label or 'Job Search',
                'job_id': app.job_id,
                'job_url': app.job_url,
                'company': app.company,
                'role_title': app.role_title,
                'location': app.location,
                'remote_type': app.remote_type,
                'salary_range': app.salary_range,
                'status': app.status,
                'submission_method': app.submission_method,
                'llm_score': app.llm_score,
                'llm_score_reason': app.llm_score_reason,
                'failure_reason': app.failure_reason,
                'applied_at': app.applied_at,
                'created_at': app.created_at,
            }
            for app in applications
        ]

        logger.debug('[ApplicationListView] user=%s returned %d applications', request.user.id, len(data))
        return Response(data)


class JobSearchListView(APIView):
    """
    GET /api/jobs/searches/
    Returns all job searches for the authenticated user, with last run info.
    """

    def get(self, request):
        logger.debug('[JobSearchListView] user=%s fetching job searches', request.user.id)

        # Subquery: latest run ID per job_search
        latest_run_ids = (
            DailyRunLog.objects
            .filter(job_search=OuterRef('pk'))
            .order_by('-run_at')
            .values('id')[:1]
        )

        searches = (
            JobSearch.objects
            .filter(user=request.user)
            .prefetch_related(
                Prefetch(
                    'daily_run_logs',
                    queryset=DailyRunLog.objects.filter(
                        id__in=Subquery(latest_run_ids)
                    ),
                    to_attr='_latest_run_list',
                )
            )
            .order_by('-created_at')
        )

        data = []
        for s in searches:
            last_run = s._latest_run_list[0] if s._latest_run_list else None
            data.append({
                'id': s.id,
                'label': s.label or 'Job Search',
                'active': s.active,
                'schedule_enabled': s.schedule_enabled,
                'daily_limit': s.daily_limit,
                'role_titles': s.role_titles,
                'cities': s.cities,
                'location_types': s.location_types,
                'seniority_levels': s.seniority_levels,
                'created_at': s.created_at,
                'updated_at': s.updated_at,
                'last_run': {
                    'run_at': last_run.run_at,
                    'status': last_run.status,
                    'jobs_fetched': last_run.jobs_fetched,
                    'jobs_scored': last_run.jobs_scored,
                    'jobs_applied': last_run.jobs_applied,
                    'jobs_failed': last_run.jobs_failed,
                } if last_run else None,
            })

        logger.debug('[JobSearchListView] user=%s returned %d searches', request.user.id, len(data))
        return Response(data)


class JobSearchToggleView(APIView):
    """
    PATCH /api/jobs/searches/<id>/toggle/
    Flips the active boolean on a job search.
    Scoped to the authenticated user — 404 if not theirs.
    """

    def patch(self, request, pk):
        logger.debug('[JobSearchToggleView] user=%s toggling search id=%s', request.user.id, pk)

        try:
            search = JobSearch.objects.get(pk=pk, user=request.user)
        except JobSearch.DoesNotExist:
            logger.warning('[JobSearchToggleView] user=%s search id=%s not found', request.user.id, pk)
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        search.active = not search.active
        search.save(update_fields=['active', 'updated_at'])

        logger.info('[JobSearchToggleView] user=%s search id=%s active=%s', request.user.id, pk, search.active)
        return Response({'id': search.id, 'active': search.active})


class JobSearchTriggerView(APIView):
    """
    POST /api/jobs/searches/<id>/trigger/
    Manually fires daily_run for a specific job search.
    Scoped to the authenticated user — 404 if not theirs.
    Returns immediately; task runs asynchronously in Celery.
    """

    def post(self, request, pk):
        logger.debug('[JobSearchTriggerView] user=%s triggering search id=%s', request.user.id, pk)

        try:
            search = JobSearch.objects.get(pk=pk, user=request.user)
        except JobSearch.DoesNotExist:
            logger.warning('[JobSearchTriggerView] user=%s search id=%s not found', request.user.id, pk)
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not search.active:
            logger.warning('[JobSearchTriggerView] user=%s search id=%s is inactive', request.user.id, pk)
            return Response(
                {'detail': 'Job search is paused. Activate it before triggering a run.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = daily_run.delay(job_search_id=search.pk)

        logger.info('[JobSearchTriggerView] user=%s search id=%s task_id=%s', request.user.id, pk, task.id)
        return Response({'task_id': task.id, 'job_search_id': search.id}, status=status.HTTP_202_ACCEPTED)


class JobSearchRunLogView(APIView):
    """
    GET /api/jobs/searches/<id>/runs/
    Returns the 10 most recent DailyRunLog entries for a job search.
    Ownership enforced via job_search__user — no separate JobSearch fetch needed.
    """

    def get(self, request, pk):
        logger.debug('[JobSearchRunLogView] user=%s fetching runs for search id=%s', request.user.id, pk)

        # Verify ownership and fetch runs in one query
        runs = (
            DailyRunLog.objects
            .filter(job_search_id=pk, job_search__user=request.user)
            .order_by('-run_at')[:10]
        )

        # If no runs, verify the search actually exists and belongs to the user
        # so we return 404 rather than an empty list for a non-existent search.
        if not runs:
            if not JobSearch.objects.filter(pk=pk, user=request.user).exists():
                return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = [
            {
                'id': run.id,
                'run_at': run.run_at,
                'status': run.status,
                'jobs_fetched': run.jobs_fetched,
                'jobs_scored': run.jobs_scored,
                'jobs_applied': run.jobs_applied,
                'jobs_failed': run.jobs_failed,
                'jobs_skipped': run.jobs_skipped,
                'error': run.error,
            }
            for run in runs
        ]

        logger.debug('[JobSearchRunLogView] user=%s search id=%s returned %d runs', request.user.id, pk, len(data))
        return Response(data)


class JobSearchScheduleView(APIView):
    """
    PATCH /api/jobs/searches/<id>/schedule/
    Toggles schedule_enabled on a JobSearch, then syncs to django-celery-beat.
    Scoped to the authenticated user — 404 if not theirs.
    """

    def patch(self, request, pk):
        logger.debug('[JobSearchScheduleView] user=%s toggling schedule for search id=%s', request.user.id, pk)

        try:
            search = JobSearch.objects.get(pk=pk, user=request.user)
        except JobSearch.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        search.schedule_enabled = not search.schedule_enabled
        search.save(update_fields=['schedule_enabled', 'updated_at'])

        # Sync to celery-beat. If this fails, the DB toggle already happened —
        # log the error but still return success. Beat will re-sync on next
        # container restart via the startup sync_schedules call.
        try:
            sync_schedules()
        except Exception:
            logger.exception(
                '[JobSearchScheduleView] sync_schedules failed after toggling search id=%s — '
                'DB state is correct, beat will catch up on next restart',
                pk,
            )

        logger.info(
            '[JobSearchScheduleView] user=%s search id=%s schedule_enabled=%s',
            request.user.id, pk, search.schedule_enabled,
        )
        return Response({'id': search.id, 'schedule_enabled': search.schedule_enabled})