"""
scan_jobs — fetch new jobs from JSearch and dedup against jobs_seen.

This task is responsible for:
  1. Loading the JobSearch and validating it is still active.
  2. Fetching jobs via the JSearch client.
  3. Filtering out jobs already in JobSeen for this search.
  4. Bulk-inserting new JobSeen records.
  5. Returning the list of unseen job dicts for the scoring stage.

The task does NOT write Application records — that happens downstream.
It is idempotent: re-running after a partial failure will simply skip
jobs that were already marked as seen.
"""

import logging

from callback.jsearch.client import fetch_jobs
from jobs.models import JobSearch, JobSeen

logger = logging.getLogger(__name__)


def scan_jobs(job_search_id: int, strategy: str = 'combined') -> list[dict]:
    """
    Fetch unseen jobs for a JobSearch.

    Parameters
    ----------
    job_search_id:
        PK of the JobSearch to run.
    strategy:
        JSearch query strategy.  Passed through to ``fetch_jobs()``.
        Defaults to 'combined'.

    Returns
    -------
    list[dict]
        Normalised, unseen job dicts ready for scoring.
        Returns an empty list if the search is inactive, has no role titles,
        or the API returns nothing.
    """
    logger.info('scan_jobs started for job_search_id=%d', job_search_id)

    try:
        job_search = JobSearch.objects.select_related('user').get(pk=job_search_id)
    except JobSearch.DoesNotExist:
        logger.error('scan_jobs: JobSearch %d not found', job_search_id)
        return []

    if not job_search.active:
        logger.info('scan_jobs: JobSearch %d is inactive, skipping', job_search_id)
        return []

    if not job_search.role_titles:
        logger.warning('scan_jobs: JobSearch %d has no role_titles, skipping', job_search_id)
        return []

    # Fetch from JSearch.
    raw_jobs = fetch_jobs(
        role_titles=job_search.role_titles,
        cities=job_search.cities,
        location_types=job_search.location_types,
        strategy=strategy,
    )

    if not raw_jobs:
        logger.info('scan_jobs: no jobs returned from JSearch for job_search_id=%d', job_search_id)
        return []

    logger.info('scan_jobs: fetched %d jobs from JSearch', len(raw_jobs))

    # Dedup: find which job_ids we've already seen for this search.
    incoming_ids = [j['job_id'] for j in raw_jobs if j.get('job_id')]
    already_seen = set(
        JobSeen.objects.filter(
            job_search=job_search,
            job_id__in=incoming_ids,
        ).values_list('job_id', flat=True)
    )

    unseen_jobs = [j for j in raw_jobs if j.get('job_id') and j['job_id'] not in already_seen]

    if not unseen_jobs:
        logger.info('scan_jobs: all %d fetched jobs already seen', len(raw_jobs))
        return []

    # Bulk-insert new seen records.
    # ignore_conflicts=True makes this idempotent if somehow called twice concurrently.
    JobSeen.objects.bulk_create(
        [JobSeen(job_search=job_search, job_id=j['job_id']) for j in unseen_jobs],
        ignore_conflicts=True,
    )

    logger.info(
        'scan_jobs: %d new jobs found (%d already seen) for job_search_id=%d',
        len(unseen_jobs),
        len(already_seen),
        job_search_id,
    )

    return unseen_jobs