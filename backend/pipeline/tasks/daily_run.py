"""
daily_run — top-level Celery task that orchestrates one full pipeline run per Search.

Sequence
--------
1. Load all active Searches whose Agent is also active (or a specific one
   if search_id is supplied).
2. For each search, create a RunLog with status='running'.
3. scan_jobs  — fetch + dedup new jobs.
4. score_jobs — LLM score + rank.
5. apply_jobs — create Application records + dispatch to Lambda.
6. Update RunLog with counts and final status.

Error policy
------------
Per-search errors are caught, logged, and recorded on the run log.
A failure on one search never aborts others.
"""

import logging

from celery import shared_task

from jobs.models import RunLog, Search
from .scan_jobs import scan_jobs
from .score_jobs import score_jobs
from .apply_job import apply_jobs

logger = logging.getLogger(__name__)


def _run_one_search(search: Search) -> None:
    log = RunLog.objects.create(search=search, status='running')

    logger.info('daily_run: starting search_id=%d (log_id=%d)', search.pk, log.pk)

    try:
        # Stage 1: fetch + dedup
        unseen_jobs = scan_jobs(search.pk)
        log.jobs_fetched = len(unseen_jobs)
        log.save(update_fields=['jobs_fetched'])

        if not unseen_jobs:
            log.status = 'completed'
            log.save(update_fields=['status'])
            logger.info('daily_run: no new jobs for search_id=%d', search.pk)
            return

        # Stage 2: score + rank
        scored_jobs = score_jobs(search.pk, unseen_jobs)

        score_failures = [j for j in scored_jobs if j.get('_score_failed')]
        candidates = [j for j in scored_jobs if not j.get('_score_failed')]

        log.jobs_scored = len(candidates)
        log.jobs_failed = len(score_failures)
        log.save(update_fields=['jobs_scored', 'jobs_failed'])

        if not candidates:
            logger.info(
                'daily_run: no candidates above threshold for search_id=%d',
                search.pk,
            )
            log.status = 'completed' if not score_failures else 'partial'
            log.save(update_fields=['status'])
            return

        # Stage 3: apply
        # TODO: insert cover letter personalisation here before apply_jobs:
        #   candidates = personalise_cover_letters(search.pk, candidates)
        apply_jobs(search.pk, candidates, log)

        # Finalise status.
        # apply_jobs updates log.jobs_applied / jobs_failed in place.
        # Re-fetch to get the latest counts before deciding final status.
        log.refresh_from_db()

        total_failures = log.jobs_failed
        total_jobs = log.jobs_fetched

        if total_failures == total_jobs:
            final_status = 'failed'
        elif total_failures > 0:
            final_status = 'partial'
        else:
            final_status = 'completed'

        if log.status not in ('failed', 'partial'):
            # Don't downgrade a status already set by apply_jobs (e.g. 'partial'
            # set because no resume was found).
            log.status = final_status

        log.save(update_fields=['status'])

        logger.info(
            'daily_run: finished search_id=%d — fetched=%d scored=%d applied=%d failed=%d status=%s',
            search.pk, log.jobs_fetched, log.jobs_scored,
            log.jobs_applied, log.jobs_failed, log.status,
        )

    except Exception as exc:
        log.status = 'failed'
        log.error = str(exc)
        log.save(update_fields=['status', 'error'])
        logger.exception('daily_run: unexpected error for search_id=%d', search.pk)


@shared_task(bind=True, name='pipeline.tasks.daily_run.daily_run')
def daily_run(self, search_id: int | None = None) -> None:
    """
    Celery entry point.

    Called by celery-beat (via PeriodicTask kwargs) and manually
    via SearchTriggerView.
    Always receives search_id — beat passes it via the PeriodicTask kwargs field,
    trigger view passes it directly.
    """
    if search_id is not None:
        try:
            search = Search.objects.select_related('agent').get(pk=search_id)
        except Search.DoesNotExist:
            logger.error('daily_run: search_id=%d not found', search_id)
            return

        if not search.agent.active:
            logger.info('daily_run: skipping search_id=%d — agent inactive', search_id)
            return

        if not search.active:
            logger.info('daily_run: skipping search_id=%d — search inactive', search_id)
            return

        _run_one_search(search)
        return

    # Fallback: run all active searches for all active agents.
    # Only hit if called without search_id (e.g. manual shell invocation).
    searches = (
        Search.objects
        .filter(active=True, agent__active=True)
        .select_related('agent')
    )
    logger.info('daily_run: no search_id supplied, running %d active searches', searches.count())
    for search in searches:
        _run_one_search(search)