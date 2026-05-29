"""
score_jobs — score unseen jobs via LLM and return the top N candidates.

Takes the list of unseen job dicts produced by scan_jobs and runs each
through the LLM scoring function. Jobs below the configured score threshold
are filtered out. The remaining jobs are sorted descending by score and
capped at the Search's daily_target.

This module is intentionally free of Celery task decoration — it is called
directly by the daily_run orchestrator so that the orchestrator controls
retry and error-handling policy. If you need to run scoring in isolation
for debugging, call score_jobs() directly.
"""

import logging

from django.conf import settings

from pipeline.llm import score_job
from jobs.models import Search

logger = logging.getLogger(__name__)


def _build_profile(search: Search) -> dict:
    """
    Build the profile dict passed to the LLM from a Search instance.

    Centralised here so the shape is consistent across all scoring calls.
    Extend this function when the profile schema gains new fields (e.g.
    pulling from Portfolio.body once that's wired up).

    Currently uses CoverLetterSample.body as an experience summary —
    it's written in the user's voice and gives the LLM useful context.
    When Portfolio is populated, prefer that instead as it's more
    structured and fact-oriented.
    """
    experience_summary = ''
    if search.cover_letter_sample:
        experience_summary = search.cover_letter_sample.body[:1000]

    # TODO: once Portfolio is reliably populated during onboarding,
    # prefer portfolio.body here as the primary experience context.
    # if search.portfolio:
    #     experience_summary = search.portfolio.body[:2000]

    return {
        'target_roles': search.role_titles,
        'seniority_levels': search.seniority_levels,
        'years_experience': search.years_experience,
        'location_types': search.location_types,
        'experience_summary': experience_summary,
    }


def score_jobs(search_id: int, unseen_jobs: list[dict]) -> list[dict]:
    """
    Score a list of unseen jobs and return the top candidates.

    Parameters
    ----------
    search_id:
        PK of the owning Search (used to load config and build profile).
    unseen_jobs:
        Normalised job dicts from scan_jobs.

    Returns
    -------
    list[dict]
        Jobs that passed the score threshold, sorted by score descending,
        capped at Search.daily_target. Each dict is the original job dict
        with two additional keys added:
            llm_score        (int)
            llm_score_reason (str)

    Notes
    -----
    Scoring failures for individual jobs are caught and logged. A single
    bad LLM response will not abort the entire run — the job is marked with
    _score_failed=True and returned so the orchestrator can count it.
    """
    if not unseen_jobs:
        return []

    logger.info('score_jobs: scoring %d jobs for search_id=%d', len(unseen_jobs), search_id)

    try:
        search = Search.objects.select_related(
            'cover_letter_sample',
            'portfolio',
        ).get(pk=search_id)
    except Search.DoesNotExist:
        logger.error('score_jobs: Search %d not found', search_id)
        return []

    threshold = settings.LLM_SCORE_THRESHOLD
    profile = _build_profile(search)
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
    candidates = candidates[:search.daily_target]

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