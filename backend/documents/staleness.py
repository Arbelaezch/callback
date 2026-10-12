import logging
from datetime import timedelta

from django.utils import timezone

from callback.config import GENERATION_STALE_AFTER_MINUTES, PARSE_STALE_AFTER_MINUTES
from users.models import Resume

from .models import GeneratedDocument

logger = logging.getLogger(__name__)

STALE_PARSE_ERROR = 'Analysis stopped unexpectedly. Please try again.'
STALE_GENERATION_ERROR = 'Generation stopped unexpectedly. Please generate again.'


def fail_stale_parses(user) -> int:
    """
    Mark the user's resume parses still pending past the timeout as failed
    (the worker died before writing a final status). Returns the count.
    """
    cutoff = timezone.now() - timedelta(minutes=PARSE_STALE_AFTER_MINUTES)
    count = Resume.objects.filter(
        user=user, parse_status='pending', parse_requested_at__lt=cutoff,
    ).update(parse_status='failed', parse_error=STALE_PARSE_ERROR)
    if count:
        logger.warning('Failed %d stale resume parse(s) for user %s', count, user.pk)
    return count


def fail_stale_documents(user) -> int:
    """
    Mark the user's generated documents still pending past the timeout as
    failed (the worker died before writing a final status). Returns the count.
    """
    now = timezone.now()
    cutoff = now - timedelta(minutes=GENERATION_STALE_AFTER_MINUTES)
    # .update() skips auto_now, so updated_at is set explicitly.
    count = GeneratedDocument.objects.filter(
        job_posting__user=user, status='pending', created_at__lt=cutoff,
    ).update(status='failed', error=STALE_GENERATION_ERROR, updated_at=now)
    if count:
        logger.warning('Failed %d stale generated document(s) for user %s', count, user.pk)
    return count
