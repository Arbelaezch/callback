import logging
from datetime import timedelta

from django.utils import timezone

from callback.config import PARSE_STALE_AFTER_MINUTES
from users.models import Resume

logger = logging.getLogger(__name__)

STALE_PARSE_ERROR = 'Analysis stopped unexpectedly. Please try again.'


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
