"""
In-flight guards and daily caps for resume analysis and document generation.

Checks are read-only; the views call them inside transaction.atomic() after
lock_user(), so one user's concurrent requests cannot both pass a check.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from callback.config import (
    DAILY_GENERATION_LIMIT,
    DAILY_PARSE_LIMIT,
    GENERATION_INFLIGHT_MINUTES,
    PARSE_INFLIGHT_MINUTES,
)

from .models import GeneratedDocument, ParseRequest

GENERATION_IN_FLIGHT_ERROR = (
    'Documents for this job are already being generated. '
    'Please wait a few minutes before generating again.'
)
PARSE_IN_FLIGHT_ERROR = (
    'This resume is already being analyzed. Please wait a few minutes before trying again.'
)
DAILY_GENERATION_LIMIT_ERROR = (
    f'You have reached your limit of {DAILY_GENERATION_LIMIT} generations in 24 hours. '
    'Please try again later.'
)
DAILY_PARSE_LIMIT_ERROR = (
    f'You have reached your limit of {DAILY_PARSE_LIMIT} resume analyses in 24 hours. '
    'Please try again later.'
)


def generation_in_flight(job_posting) -> bool:
    """True if the job has pending documents younger than GENERATION_INFLIGHT_MINUTES."""
    cutoff = timezone.now() - timedelta(minutes=GENERATION_INFLIGHT_MINUTES)
    return GeneratedDocument.objects.filter(
        job_posting=job_posting, status='pending', created_at__gte=cutoff,
    ).exists()


def parse_in_flight(resume) -> bool:
    """True if the resume's parse was requested less than PARSE_INFLIGHT_MINUTES ago and is still pending."""
    if resume.parse_status != 'pending' or resume.parse_requested_at is None:
        return False
    cutoff = timezone.now() - timedelta(minutes=PARSE_INFLIGHT_MINUTES)
    return resume.parse_requested_at >= cutoff


def generations_last_day(user) -> int:
    """Generations started by the user in the last 24 hours (one resume row per generation)."""
    cutoff = timezone.now() - timedelta(days=1)
    return GeneratedDocument.objects.filter(
        job_posting__user=user, kind='resume', created_at__gte=cutoff,
    ).count()


def parses_last_day(user) -> int:
    """Resume analyses accepted for the user in the last 24 hours."""
    cutoff = timezone.now() - timedelta(days=1)
    return ParseRequest.objects.filter(user=user, created_at__gte=cutoff).count()


def lock_user(user):
    """
    Lock the user's row until the transaction ends. The caller must be inside
    transaction.atomic(). Serializes one user's parse and generate requests so
    the in-flight and cap checks cannot race.
    """
    return get_user_model().objects.select_for_update().get(pk=user.pk)
