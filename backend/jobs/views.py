import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Application, JobSearch

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
    """

    def get(self, request):
        logger.debug('[ApplicationListView] user=%s fetching applications', request.user.id)

        applications = (
            Application.objects
            .filter(job_search__user=request.user)
            .select_related('job_search', 'resume')
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
    Returns all job searches for the authenticated user.
    """

    def get(self, request):
        logger.debug('[JobSearchListView] user=%s fetching job searches', request.user.id)

        searches = JobSearch.objects.filter(user=request.user).order_by('-created_at')

        data = [
            {
                'id': s.id,
                'label': s.label or 'Job Search',
                'active': s.active,
                'daily_limit': s.daily_limit,
                'role_titles': s.role_titles,
                'cities': s.cities,
                'location_types': s.location_types,
                'seniority_levels': s.seniority_levels,
                'created_at': s.created_at,
                'updated_at': s.updated_at,
            }
            for s in searches
        ]

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