"""
pipeline/tasks/apply_job.py — application submission stage.

Responsibilities
----------------
1. For each scored candidate job, create an Application record (status=pending).
2. Detect the ATS from the apply URL (greenhouse / lever / other).
3. Dispatch to Lambda (Browser Use) for submission.
   - Greenhouse and Lever are detected and logged but also route through
     Lambda for now — direct API submission requires the employer's API key,
     which is not available to third-party applicants.
     TODO: replace Lambda dispatch with GreenhouseClient / LeverClient once
     a direct-submission path becomes available.
4. Update the Application record to submitted or failed.
5. Return counts for the RunLog.

Lambda payload contract
-----------------------
The Lambda function (callback-submit-application) receives:

    {
        "application_id": int,       -- Application PK, written back to DB on completion
        "job_url":        str,       -- canonical job page URL (for context / fallback nav)
        "apply_url":      str,       -- direct apply link (Browser Use starts here)
        "resume_url":     str,       -- presigned S3 GET URL, valid for 1 hour
        "resume_filename": str,      -- original filename for the file input
        "cover_letter":   str,       -- personalised cover letter text
        "user": {
            "first_name": str,
            "last_name":  str,
            "email":      str,
        },
        "ats":            str,       -- 'greenhouse' | 'lever' | 'other' (informational)
    }

Lambda writes the result back to the Application row directly via Django ORM
(it has DB access through the same DATABASE_URL env var).  The invocation is
fire-and-forget from Django's side; we record the invocation ID and treat the
application as 'submitted' once the invoke call succeeds.

Error handling
--------------
- Lambda invoke failure  → Application status='failed', failure_reason set.
- Resume missing / S3 error → Application status='failed', failure_reason set.
- apply_jobs() never raises — per-application errors are caught and logged so
  one bad job never aborts the rest of the batch.
"""

import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from jobs.models import Application, RunLog, Search
from users.models import Resume
from pipeline.ats import detect_ats
from pipeline.storage import get_resume_url  # presigned GET URL helper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lambda client
# ---------------------------------------------------------------------------

def _lambda_client():
    return boto3.client(
        'lambda',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


# ---------------------------------------------------------------------------
# Per-application helpers
# ---------------------------------------------------------------------------

def _get_resume(search: Search) -> Resume | None:
    """
    Return the resume to use for this search.
    Prefers the search-specific resume; falls back to the user's default.
    Returns None if the user has no usable resume.
    """
    if search.resume and search.resume.status == 'ready':
        return search.resume

    return (
        search.agent.user.resumes
        .filter(is_default=True, status='ready')
        .first()
    )


def _build_lambda_payload(
    application: Application,
    resume: Resume,
    cover_letter: str,
    ats: str,
) -> dict:
    """Build the payload dict sent to the Lambda function."""
    user = application.search.agent.user

    resume_url = get_resume_url(resume.s3_key, expires_in=3600)

    return {
        'application_id': application.pk,
        'job_url':        application.job_url,
        'apply_url':      application.job_url,   # same until we split apply_url into Application
        'resume_url':     resume_url,
        'resume_filename': resume.filename,
        'cover_letter':   cover_letter,
        'user': {
            'first_name': user.first_name,
            'last_name':  user.last_name,
            'email':      user.email,
        },
        'ats': ats,
    }


def _invoke_lambda(payload: dict) -> str:
    """
    Invoke the Lambda function asynchronously (Event invocation type).
    Returns the invocation ID from the response metadata.
    Raises BotoCoreError / ClientError on failure.
    """
    client = _lambda_client()

    response = client.invoke(
        FunctionName=settings.AWS_LAMBDA_FUNCTION_NAME,
        InvocationType='Event',          # async — Lambda queues and returns 202
        Payload=json.dumps(payload),
    )

    # 'Event' invocations return 202 on success.
    status_code = response.get('StatusCode', 0)
    if status_code != 202:
        raise RuntimeError(
            f'Lambda invoke returned unexpected status {status_code} '
            f'for application_id={payload["application_id"]}'
        )

    invocation_id = response.get('ResponseMetadata', {}).get('RequestId', '')
    return invocation_id


# ---------------------------------------------------------------------------
# Per-application entry point
# ---------------------------------------------------------------------------

def _apply_one(search: Search, job: dict, resume: Resume) -> bool:
    """
    Create an Application record and dispatch to Lambda.

    Returns True on successful dispatch, False on any failure.
    Never raises — all errors are caught, logged, and written to the DB.
    """
    # Resolve cover letter.  Empty string is acceptable — Lambda will submit
    # without one if the form doesn't require it.
    cover_letter = job.get('cover_letter', '') or ''

    # Detect ATS for logging and future routing.
    apply_link = job.get('apply_link') or job.get('job_url', '')
    ats = detect_ats(apply_link)

    if ats in ('greenhouse', 'lever'):
        logger.info(
            'apply_one: detected %s ATS for job_id=%s — routing through Lambda '
            '(direct API submission not yet available)',
            ats, job['job_id'],
        )

    # Create Application record in pending state.
    try:
        application, created = Application.objects.get_or_create(
            search=search,
            job_id=job['job_id'],
            defaults={
                'resume':           resume,
                'job_url':          job.get('job_url', ''),
                'company':          job.get('company', ''),
                'role_title':       job.get('title', ''),
                'location':         job.get('location', ''),
                'remote_type':      job.get('remote_type', 'unknown'),
                'salary_range':     job.get('salary_range'),
                'job_description':  job.get('description', ''),
                'submission_method': 'browser_lambda',
                'status':           'pending',
                'llm_score':        job.get('llm_score'),
                'llm_score_reason': job.get('llm_score_reason'),
                'cover_letter_used': cover_letter,
            },
        )
    except Exception as exc:
        logger.exception(
            'apply_one: failed to create Application for job_id=%s search_id=%d: %s',
            job['job_id'], search.pk, exc,
        )
        return False

    if not created:
        # Already applied via a previous run — skip silently.
        logger.info(
            'apply_one: application already exists for job_id=%s search_id=%d, skipping',
            job['job_id'], search.pk,
        )
        return False

    # Build Lambda payload and invoke.
    try:
        payload = _build_lambda_payload(application, resume, cover_letter, ats)
        invocation_id = _invoke_lambda(payload)

        application.lambda_invocation_id = invocation_id
        application.status = 'submitted'
        application.applied_at = datetime.now(tz=timezone.utc)
        application.save(update_fields=[
            'lambda_invocation_id', 'status', 'applied_at',
        ])

        logger.info(
            'apply_one: dispatched job_id=%s to Lambda (invocation_id=%s, ats=%s)',
            job['job_id'], invocation_id, ats,
        )
        return True

    except (BotoCoreError, ClientError) as exc:
        reason = f'Lambda invoke failed: {exc}'
        logger.error(
            'apply_one: Lambda error for job_id=%s search_id=%d: %s',
            job['job_id'], search.pk, reason,
        )
    except RuntimeError as exc:
        reason = str(exc)
        logger.error(
            'apply_one: Lambda returned bad status for job_id=%s search_id=%d: %s',
            job['job_id'], search.pk, reason,
        )
    except Exception as exc:
        reason = f'Unexpected error: {exc}'
        logger.exception(
            'apply_one: unexpected error for job_id=%s search_id=%d',
            job['job_id'], search.pk,
        )

    # Mark failed.
    application.status = 'failed'
    application.failure_reason = reason
    application.save(update_fields=['status', 'failure_reason'])
    return False


# ---------------------------------------------------------------------------
# Public interface — called by daily_run
# ---------------------------------------------------------------------------

def apply_jobs(search_id: int, candidates: list[dict], log: RunLog) -> None:
    """
    Dispatch Lambda invocations for each scored candidate job.

    Parameters
    ----------
    search_id:
        PK of the Search being processed.
    candidates:
        Scored job dicts from score_jobs — each has llm_score, llm_score_reason,
        and all normalised JSearch fields.  Jobs with _score_failed=True must
        already be filtered out by the caller (daily_run).
    log:
        The RunLog for this run.  Updated in place with jobs_applied /
        jobs_failed counts.

    Notes
    -----
    - Skips the entire batch if no usable resume is found.
    - Individual job failures never abort the rest of the batch.
    - cover_letter personalisation is not yet implemented; the cover_letter
      field on each job dict will be empty until that stage is added between
      score_jobs and apply_jobs in daily_run.
      TODO: call personalise_cover_letter() per job before this stage.
    """
    try:
        search = Search.objects.select_related(
            'agent__user', 'resume',
        ).get(pk=search_id)
    except Search.DoesNotExist:
        logger.error('apply_jobs: search_id=%d not found', search_id)
        return

    resume = _get_resume(search)
    if resume is None:
        logger.warning(
            'apply_jobs: no ready resume for search_id=%d — skipping apply stage',
            search_id,
        )
        log.status = 'partial'
        log.error = 'No ready resume found — apply stage skipped.'
        log.save(update_fields=['status', 'error'])
        return

    applied = 0
    failed = 0

    for job in candidates:
        success = _apply_one(search, job, resume)
        if success:
            applied += 1
        else:
            failed += 1

    log.jobs_applied = applied
    log.jobs_failed = log.jobs_failed + failed   # score failures already counted
    log.save(update_fields=['jobs_applied', 'jobs_failed'])

    logger.info(
        'apply_jobs: search_id=%d — applied=%d failed=%d',
        search_id, applied, failed,
    )