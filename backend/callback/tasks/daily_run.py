"""
daily_run — top-level Celery task that orchestrates one full run per JobSearch.

Sequence
--------
1. Load all active JobSearches (or a specific one if job_search_id is supplied).
2. For each search, create a DailyRunLog with status='running'.
3. scan_jobs  — fetch + dedup new jobs.
4. score_jobs — LLM score + rank.
5. apply_jobs — (stub) not yet implemented.
6. Update DailyRunLog with counts and final status.

Error policy
------------
- Per-search errors are caught, logged, and recorded on the run log.
  A failure on one search never aborts other searches.
- The Celery task itself only raises on truly unexpected errors so that
  Celery's retry / dead-letter machinery can fire correctly.
"""

import logging

from celery import shared_task
from django.utils import timezone

from jobs.models import DailyRunLog, JobSearch
from .scan_jobs import scan_jobs
from .score_jobs import score_jobs

logger = logging.getLogger(__name__)


def _run_one_search(job_search: JobSearch) -> None:
    """Run the full discovery pipeline for a single JobSearch."""
    log = DailyRunLog.objects.create(
        job_search=job_search,
        status='running',
    )

    logger.info(
        'daily_run: starting job_search_id=%d (log_id=%d)',
        job_search.pk,
        log.pk,
    )

    try:
        # ----------------------------------------------------------------
        # Stage 1: fetch + dedup
        # ----------------------------------------------------------------
        unseen_jobs = scan_jobs(job_search.pk)
        log.jobs_fetched = len(unseen_jobs)
        log.save(update_fields=['jobs_fetched'])

        if not unseen_jobs:
            log.status = 'completed'
            log.save(update_fields=['status'])
            logger.info('daily_run: no new jobs for job_search_id=%d', job_search.pk)
            return

        # ----------------------------------------------------------------
        # Stage 2: score + rank
        # ----------------------------------------------------------------
        scored_jobs = score_jobs(job_search.pk, unseen_jobs)

        # Count scoring failures (flagged by score_jobs).
        score_failures = [j for j in scored_jobs if j.get('_score_failed')]
        candidates = [j for j in scored_jobs if not j.get('_score_failed')]

        log.jobs_scored = len(candidates)
        log.jobs_failed = len(score_failures)
        log.save(update_fields=['jobs_scored', 'jobs_failed'])

        # ----------------------------------------------------------------
        # Stage 3: apply (stub — implemented in a future task)
        # ----------------------------------------------------------------
        logger.info(
            'daily_run: apply stage not yet implemented — '
            '%d candidates ready for job_search_id=%d',
            len(candidates),
            job_search.pk,
        )
        # apply_jobs will be called here and will populate log.jobs_applied.

        # ----------------------------------------------------------------
        # Finalise log
        # ----------------------------------------------------------------
        final_status = 'completed'
        if score_failures and not candidates:
            final_status = 'failed'
        elif score_failures:
            final_status = 'partial'

        log.status = final_status
        log.save(update_fields=['status'])

        logger.info(
            'daily_run: finished job_search_id=%d — '
            'fetched=%d scored=%d failed=%d status=%s',
            job_search.pk,
            log.jobs_fetched,
            log.jobs_scored,
            log.jobs_failed,
            log.status,
        )

    except Exception as exc:
        logger.exception('daily_run: unhandled error for job_search_id=%d', job_search.pk)
        log.status = 'failed'
        log.error = str(exc)
        log.save(update_fields=['status', 'error'])


@shared_task(bind=True, name='callback.tasks.daily_run')
def daily_run(self, job_search_id: int | None = None) -> None:
    """
    Celery entry point.

    Parameters
    ----------
    job_search_id:
        If supplied, run only this JobSearch.
        If None, run all active JobSearches (normal scheduled invocation).
    """
    if job_search_id is not None:
        try:
            searches = [JobSearch.objects.get(pk=job_search_id, active=True)]
        except JobSearch.DoesNotExist:
            logger.error('daily_run: JobSearch %d not found or inactive', job_search_id)
            return
    else:
        searches = list(
            JobSearch.objects.filter(active=True).select_related(
                'user', 'resume', 'cover_letter_template'
            )
        )

    logger.info('daily_run: processing %d active job search(es)', len(searches))

    for job_search in searches:
        _run_one_search(job_search)