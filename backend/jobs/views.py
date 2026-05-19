from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import JobSearch, Application


class ChoicesView(APIView):
    permission_classes = [IsAuthenticated]

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