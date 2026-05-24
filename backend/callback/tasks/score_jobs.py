"""
score_jobs — score unseen jobs via LLM and return the top N candidates.

Takes the list of unseen job dicts produced by scan_jobs and runs each
through the LLM scoring function.  Jobs below the configured score threshold
are filtered out.  The remaining jobs are sorted descending by score and
capped at the JobSearch's daily_limit.

This module is intentionally free of Celery task decoration — it is called
directly by the daily_run orchestrator so that the orchestrator controls
retry and error-handling policy.  If you need to run scoring in isolation
for debugging, call score_jobs() directly.
"""

import logging

from callback.config import LLM_SCORE_THRESHOLD
from callback.llm import score_job
from jobs.models import JobSearch

logger = logging.getLogger(__name__)


def _build_profile(job_search: JobSearch) -> dict:
    """
    Build the profile dict passed to the LLM from a JobSearch instance.

    Centralised here so the shape is consistent across scoring calls.
    Extend this function when the profile schema gains new fields (e.g.
    skills list, free-text experience summary from the user model).
    """
    # Cover letter body doubles as an experience summary for now.
    # When a dedicated experience_summary field exists on the user model,
    # pull it in here instead.
    experience_summary = ''
    if job_search.cover_letter_template:
        experience_summary = job_search.cover_letter_template.body[:1000]

    return {
        'target_roles': job_search.role_titles,
        'seniority_levels': job_search.seniority_levels,
        'years_experience': job_search.years_experience,
        'location_types': job_search.location_types,
        'experience_summary': experience_summary,
    }


def score_jobs(job_search_id: int, unseen_jobs: list[dict]) -> list[dict]:
    """
    Score a list of unseen jobs and return the top candidates.

    Parameters
    ----------
    job_search_id:
        PK of the owning JobSearch (used to load config and profile).
    unseen_jobs:
        Normalised job dicts from scan_jobs.

    Returns
    -------
    list[dict]
        Jobs that passed the score threshold, sorted by score descending,
        capped at JobSearch.daily_limit.  Each dict is the original job dict
        with two additional keys added:
            llm_score  (int)
            llm_score_reason (str)

    Notes
    -----
    Scoring failures for individual jobs are caught and logged.  A single
    bad LLM response will not abort the entire run — the job is simply
    skipped and counted in the caller's jobs_failed counter.
    """
    if not unseen_jobs:
        return []

    logger.info('score_jobs: scoring %d jobs for job_search_id=%d', len(unseen_jobs), job_search_id)

    try:
        job_search = JobSearch.objects.select_related('cover_letter_template').get(pk=job_search_id)
    except JobSearch.DoesNotExist:
        logger.error('score_jobs: JobSearch %d not found', job_search_id)
        return []

    threshold = LLM_SCORE_THRESHOLD
    profile = _build_profile(job_search)
    scored: list[dict] = []

    for job in unseen_jobs:
        try:
            result = score_job(job, profile)
            score = result['score']
            reason = result['reason']
        except Exception:
            logger.exception(
                'score_jobs: failed to score job_id=%s (%s at %s)',
                job.get('job_id'), job.get('title'), job.get('company'),
            )
            # Yield control back to caller so it can count this as a failure.
            job['llm_score'] = None
            job['llm_score_reason'] = None
            job['_score_failed'] = True
            scored.append(job)
            continue

        job['llm_score'] = score
        job['llm_score_reason'] = reason
        scored.append(job)

    # Separate hard failures from scoreable jobs.
    failed = [j for j in scored if j.get('_score_failed')]
    scoreable = [j for j in scored if not j.get('_score_failed')]

    # Filter by threshold, sort descending, cap at daily_limit.
    candidates = [j for j in scoreable if (j['llm_score'] or 0) >= threshold]
    candidates.sort(key=lambda j: j['llm_score'], reverse=True)
    candidates = candidates[: job_search.daily_limit]

    logger.info(
        'score_jobs: %d/%d jobs passed threshold %d, returning top %d candidates '
        '(%d scoring failures)',
        len(candidates),
        len(scoreable),
        threshold,
        len(candidates),
        len(failed),
    )

    # Attach failures to return value so orchestrator can count them.
    # Caller checks for _score_failed flag.
    return candidates + failed