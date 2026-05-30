import logging

from django.db.models import OuterRef, Prefetch, Subquery
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from pipeline.tasks.daily_run import daily_run
from jobs.management.commands.sync_schedules import sync_schedules
from .models import Agent, Application, RunLog, Search
from .serializers import (
    AgentSerializer,
    ApplicationSerializer,
    RunLogSerializer,
    SearchSerializer,
)

logger = logging.getLogger(__name__)


class ChoicesView(APIView):
    """
    GET /api/jobs/choices/
    Returns all choice field options for the frontend.
    Add any new choice fields here as they're added to models.
    """

    def get(self, request):
        return Response({
            'location_types': [
                {'value': v, 'label': l} for v, l in Search.LOCATION_TYPE_CHOICES
            ],
            'seniority_levels': [
                {'value': v, 'label': l} for v, l in Search.SENIORITY_CHOICES
            ],
            'application_statuses': [
                {'value': v, 'label': l} for v, l in Application.STATUS_CHOICES
            ],
            'submission_methods': [
                {'value': v, 'label': l} for v, l in Application.SUBMISSION_METHOD_CHOICES
            ],
            'remote_types': [
                {'value': v, 'label': l} for v, l in Application.REMOTE_TYPE_CHOICES
            ],
        })


class ApplicationListView(APIView):
    """
    GET /api/jobs/applications/
    Returns all applications for the authenticated user, newest first.

    TODO: add pagination before shipping to real users.
    """

    def get(self, request):
        logger.debug('[ApplicationListView] user=%s fetching applications', request.user.id)

        applications = (
            Application.objects
            .filter(search__agent__user=request.user)
            .select_related('search')
            .order_by('-created_at')
        )

        serializer = ApplicationSerializer(applications, many=True)
        logger.debug('[ApplicationListView] user=%s returned %d applications', request.user.id, len(serializer.data))
        return Response(serializer.data)


class AgentView(APIView):
    """
    GET  /api/jobs/agent/  — return the user's agent (creates one on first visit)
    PATCH /api/jobs/agent/ — update active, name
    """

    def _get_or_create_agent(self, user):
        agent, _ = Agent.objects.get_or_create(user=user)
        return agent

    def get(self, request):
        agent = self._get_or_create_agent(request.user)
        return Response(AgentSerializer(agent).data)

    def patch(self, request):
        agent = self._get_or_create_agent(request.user)
        serializer = AgentSerializer(agent, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        logger.info('[AgentView] user=%s agent updated: %s', request.user.id, serializer.data)
        return Response(serializer.data)


class SearchListView(APIView):
    """
    GET /api/jobs/searches/
    Returns all searches for the authenticated user's agent, with last run info.

    Uses a Prefetch subquery to load the most recent RunLog per search
    in a single extra query — avoids N+1.
    """

    def get(self, request):
        logger.debug('[SearchListView] user=%s fetching searches', request.user.id)

        # Subquery: latest run ID per Search
        latest_run_ids = (
            RunLog.objects
            .filter(search=OuterRef('pk'))
            .order_by('-run_at')
            .values('id')[:1]
        )

        searches = (
            Search.objects
            .filter(agent__user=request.user)
            .prefetch_related(
                Prefetch(
                    'run_logs',
                    queryset=RunLog.objects.filter(id__in=Subquery(latest_run_ids)),
                    to_attr='_latest_run_list',
                )
            )
            .order_by('-created_at')
        )

        serializer = SearchSerializer(searches, many=True)
        logger.debug('[SearchListView] user=%s returned %d searches', request.user.id, len(serializer.data))
        return Response(serializer.data)

    def post(self, request):
        logger.debug('[SearchListView] user=%s creating search', request.user.id)

        agent, _ = Agent.objects.get_or_create(user=request.user)

        serializer = SearchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Auto-assign default documents if not provided
        from users.models import Resume, Portfolio, CoverLetterSample
        resume = Resume.objects.filter(user=request.user, is_default=True).first()
        portfolio = Portfolio.objects.filter(user=request.user, is_default=True).first()
        cover_letter_sample = CoverLetterSample.objects.filter(user=request.user, is_default=True).first()

        search = serializer.save(
            agent=agent,
            resume=resume,
            portfolio=portfolio,
            cover_letter_sample=cover_letter_sample,
        )

        logger.info('[SearchListView] user=%s created search id=%s', request.user.id, search.id)
        return Response(SearchSerializer(search).data, status=status.HTTP_201_CREATED)


class SearchToggleView(APIView):
    """
    PATCH /api/jobs/searches/<id>/toggle/
    Flips the active boolean on a Search.
    """

    def patch(self, request, pk):
        logger.debug('[SearchToggleView] user=%s toggling search id=%s', request.user.id, pk)

        try:
            search = Search.objects.get(pk=pk, agent__user=request.user)
        except Search.DoesNotExist:
            logger.warning('[SearchToggleView] user=%s search id=%s not found', request.user.id, pk)
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        search.active = not search.active
        search.save(update_fields=['active', 'updated_at'])

        logger.info('[SearchToggleView] user=%s search id=%s active=%s', request.user.id, pk, search.active)
        return Response({'id': search.id, 'active': search.active})


class SearchTriggerView(APIView):
    """
    POST /api/jobs/searches/<id>/trigger/
    Manually fires daily_run for a specific Search.
    Returns immediately; task runs asynchronously in Celery.
    """

    def post(self, request, pk):
        logger.debug('[SearchTriggerView] user=%s triggering search id=%s', request.user.id, pk)

        try:
            search = Search.objects.select_related('agent').get(pk=pk, agent__user=request.user)
        except Search.DoesNotExist:
            logger.warning('[SearchTriggerView] user=%s search id=%s not found', request.user.id, pk)
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not search.agent.active:
            return Response(
                {'detail': 'Agent is inactive. Activate your agent before triggering a run.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not search.active:
            logger.warning('[SearchTriggerView] user=%s search id=%s is inactive', request.user.id, pk)
            return Response(
                {'detail': 'Search is paused. Activate it before triggering a run.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = daily_run.delay(search_id=search.pk)

        logger.info('[SearchTriggerView] user=%s search id=%s task_id=%s', request.user.id, pk, task.id)
        return Response({'task_id': task.id, 'search_id': search.id}, status=status.HTTP_202_ACCEPTED)


class SearchRunLogView(APIView):
    """
    GET /api/jobs/searches/<id>/runs/
    Returns the 10 most recent RunLog entries for a Search.
    """

    def get(self, request, pk):
        logger.debug('[SearchRunLogView] user=%s fetching runs for search id=%s', request.user.id, pk)

        # Verify ownership and fetch runs in one query
        runs = (
            RunLog.objects
            .filter(search_id=pk, search__agent__user=request.user)
            .order_by('-run_at')[:10]
        )

        # Empty result is ambiguous — could be no runs yet, or wrong user/id.
        # Only do the existence check when needed to avoid an extra query on
        # the happy path.
        if not runs:
            if not Search.objects.filter(pk=pk, agent__user=request.user).exists():
                return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = RunLogSerializer(runs, many=True)
        logger.debug('[SearchRunLogView] user=%s search id=%s returned %d runs', request.user.id, pk, len(serializer.data))
        return Response(serializer.data)


class SearchScheduleView(APIView):
    """
    PATCH /api/jobs/searches/<id>/schedule/
    Toggles schedule_enabled and syncs to django-celery-beat.
    """

    def patch(self, request, pk):
        logger.debug('[SearchScheduleView] user=%s toggling schedule for search id=%s', request.user.id, pk)

        try:
            search = Search.objects.get(pk=pk, agent__user=request.user)
        except Search.DoesNotExist:
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
                '[SearchScheduleView] sync_schedules failed after toggling search id=%s — '
                'DB state is correct, beat will catch up on next restart',
                pk,
            )

        logger.info(
            '[SearchScheduleView] user=%s search id=%s schedule_enabled=%s',
            request.user.id, pk, search.schedule_enabled,
        )
        return Response({'id': search.id, 'schedule_enabled': search.schedule_enabled})