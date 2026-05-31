"""
pipeline/views.py — internal API views for the pipeline.

These endpoints are not user-facing. They are called by internal services
(currently Lambda) and are authenticated via a shared secret header rather
than JWT, since Lambda has no user session.
"""

import logging
from datetime import datetime, timezone

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from jobs.models import Application

logger = logging.getLogger(__name__)


class ApplicationCallbackView(APIView):
    """
    POST /api/pipeline/applications/{application_id}/callback/

    Called by the Lambda function (callback-submit-application) after a
    browser-use application attempt completes — successfully or not.

    Authentication
    --------------
    Validated via the X-Callback-Secret header against settings.CALLBACK_SECRET.
    No JWT required — Lambda has no user session.

    Request body
    ------------
    {
        "status":         "submitted" | "failed",
        "failure_reason": str | null
    }

    Response
    --------
    200 — record updated successfully
    400 — missing / invalid body fields
    401 — missing or invalid secret
    404 — application not found
    """

    authentication_classes = []  # no JWT auth for this endpoint
    permission_classes = []      # secret header handles authz below

    def post(self, request: Request, application_id: int) -> Response:
        # ----------------------------------------------------------------
        # Authenticate via shared secret.
        # ----------------------------------------------------------------
        incoming_secret = request.headers.get('X-Callback-Secret', '')
        if not incoming_secret or incoming_secret != settings.CALLBACK_SECRET:
            logger.warning(
                'ApplicationCallbackView: invalid or missing secret for '
                'application_id=%d (ip=%s)',
                application_id,
                request.META.get('REMOTE_ADDR'),
            )
            return Response(
                {'detail': 'Invalid or missing callback secret.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ----------------------------------------------------------------
        # Validate body.
        # ----------------------------------------------------------------
        incoming_status = request.data.get('status')
        failure_reason = request.data.get('failure_reason')

        valid_statuses = {'submitted', 'failed'}
        if incoming_status not in valid_statuses:
            return Response(
                {'detail': f'"status" must be one of: {sorted(valid_statuses)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ----------------------------------------------------------------
        # Load Application.
        # ----------------------------------------------------------------
        try:
            application = Application.objects.get(pk=application_id)
        except Application.DoesNotExist:
            logger.error(
                'ApplicationCallbackView: application_id=%d not found',
                application_id,
            )
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ----------------------------------------------------------------
        # Update record.
        # ----------------------------------------------------------------
        update_fields = ['status']

        application.status = incoming_status

        if incoming_status == 'submitted':
            application.applied_at = datetime.now(tz=timezone.utc)
            update_fields.append('applied_at')

        if failure_reason:
            application.failure_reason = failure_reason[:2000]  # guard against oversized payloads
            update_fields.append('failure_reason')

        application.save(update_fields=update_fields)

        logger.info(
            'ApplicationCallbackView: application_id=%d updated to status=%s',
            application_id,
            incoming_status,
        )

        return Response({'detail': 'ok'}, status=status.HTTP_200_OK)