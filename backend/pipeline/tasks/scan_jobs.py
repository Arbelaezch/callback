"""
scan_jobs — fetch new jobs from JSearch and dedup against jobs_seen.

This task is responsible for:
  1. Loading the Search and validating it is still active.
  2. Fetching jobs via the JSearch client.
  3. Filtering out jobs already in JobSeen for this search.
  4. Bulk-inserting new JobSeen records.
  5. Returning the list of unseen job dicts for the scoring stage.

The task does NOT write Application records — that happens downstream.
It is idempotent: re-running after a partial failure will simply skip
jobs that were already marked as seen.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from jobs.models import JobSeen, Search
from pipeline.jsearch.client import fetch_jobs

logger = logging.getLogger(__name__)


def scan_jobs(search_id: int) -> list[dict]:
    """
    Fetch jobs for a Search, filter out ones the user has seen recently
    (within search.job_cooldown days), record new ones, and return unseen jobs.

    JobSeen is scoped to the user — not the search — so a job seen via any
    of the user's searches won't be returned again until the cooldown expires.
    """
    search = Search.objects.select_related('agent__user').get(pk=search_id)
    user = search.agent.user

    jobs = fetch_jobs(search)
    logger.info('scan_jobs: fetched %d jobs from JSearch', len(jobs))

    if not jobs:
        return []

    job_ids = [j['job_id'] for j in jobs]

    # Dedup: find which job_ids this user has seen within the cooldown window
    cutoff = timezone.now() - timedelta(days=search.job_cooldown)
    recently_seen_ids = set(
        JobSeen.objects
        .filter(user=user, job_id__in=job_ids, seen_at__gte=cutoff)
        .values_list('job_id', flat=True)
    )

    unseen_jobs = [j for j in jobs if j['job_id'] not in recently_seen_ids]
    logger.info(
        'scan_jobs: %d new jobs found (%d within cooldown window) for search_id=%d',
        len(unseen_jobs), len(recently_seen_ids), search_id,
    )

    # Record all unseen jobs — ignore conflicts for jobs seen outside the window
    # that are now re-eligible (update seen_at to now).
    if unseen_jobs:
        new_ids = [j['job_id'] for j in unseen_jobs]
        # Update existing rows that are outside the window (re-eligible)
        JobSeen.objects.filter(user=user, job_id__in=new_ids).update(seen_at=timezone.now())
        # Insert genuinely new rows
        existing_ids = set(
            JobSeen.objects
            .filter(user=user, job_id__in=new_ids)
            .values_list('job_id', flat=True)
        )
        truly_new = [
            JobSeen(user=user, job_id=jid)
            for jid in new_ids if jid not in existing_ids
        ]
        if truly_new:
            JobSeen.objects.bulk_create(truly_new, ignore_conflicts=True)

    return unseen_jobs