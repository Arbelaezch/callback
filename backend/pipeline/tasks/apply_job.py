"""
pipeline/tasks/apply_job.py — application submission stage.

Responsibilities
----------------
1. For each scored candidate job, create an Application record (status=pending).
2. Detect the ATS from the apply URL (greenhouse / lever / other).
3. Dispatch to Lambda (prod) or run the handler in-process (dev).
4. Update the Application record to submitted or failed.
5. Return counts for the RunLog.

Dispatch routing
----------------
Controlled by settings.USE_LAMBDA:

    USE_LAMBDA=True  (prod)
        Invokes the Lambda function asynchronously via boto3.
        Django records the invocation ID and marks the application 'submitted'.
        Lambda writes the final result back via the callback endpoint.

    USE_LAMBDA=False  (dev)
        Calls lambda_runner.run_handler() directly in-process.
        Runs the exact same browser-use agent locally.
        Requires browser-use + Playwright installed in the local venv:
            pip install browser-use playwright
            playwright install chromium

Lambda payload contract
-----------------------
{
    "application_id": int,
    "job_url":        str,
    "apply_url":      str,
    "resume_url":     str,
    "resume_filename": str,
    "cover_letter":   str,
    "user": {
        "first_name": str,
        "last_name":  str,
        "email":      str,
    },
    "ats":            str,
}
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
from storage.s3 import get_resume_url

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
    """Build the payload dict sent to Lambda or the local handler."""
    user = application.search.agent.user
    resume_url = get_resume_url(resume.s3_key, expires_in=3600)

    return {
        'application_id': application.pk,
        'job_url':         application.job_url,
        'apply_url':       application.job_url,
        'resume_url':      resume_url,
        'resume_filename': resume.filename,
        'cover_letter':    cover_letter,
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
    Returns the invocation ID. Raises on failure.
    """
    client = _lambda_client()

    response = client.invoke(
        FunctionName=settings.AWS_LAMBDA_FUNCTION_NAME,
        InvocationType='Event',
        Payload=json.dumps(payload),
    )

    status_code = response.get('StatusCode', 0)
    if status_code != 202:
        raise RuntimeError(
            f'Lambda invoke returned unexpected status {status_code} '
            f'for application_id={payload["application_id"]}'
        )

    return response.get('ResponseMetadata', {}).get('RequestId', '')


def _run_local(payload: dict) -> tuple[bool, str | None]:
    """
    Run the handler in-process for local dev (USE_LAMBDA=False).
    Returns (success, failure_reason).
    """
    from lambda_runner import run_handler

    result = run_handler(payload)
    success = result.get('status') == 'submitted'
    failure_reason = result.get('failure_reason') if not success else None
    return success, failure_reason


# ---------------------------------------------------------------------------
# Per-application entry point
# ---------------------------------------------------------------------------

def _apply_one(search: Search, job: dict, resume: Resume) -> bool:
    """
    Create an Application record and dispatch to Lambda (prod) or run
    the handler in-process (dev).

    Returns True on successful dispatch/completion, False on any failure.
    Never raises.
    """
    cover_letter = job.get('cover_letter', '') or ''
    apply_link = job.get('apply_link') or job.get('job_url', '')
    ats = detect_ats(apply_link)

    if ats in ('greenhouse', 'lever'):
        logger.info(
            'apply_one: detected %s ATS for job_id=%s — routing through browser agent '
            '(direct API submission not yet available)',
            ats, job['job_id'],
        )

    # Create Application record in pending state.
    try:
        application, created = Application.objects.get_or_create(
            search=search,
            job_id=job['job_id'],
            defaults={
                'resume':            resume,
                'job_url':           job.get('job_url', ''),
                'company':           job.get('company', ''),
                'role_title':        job.get('title', ''),
                'location':          job.get('location', ''),
                'remote_type':       job.get('remote_type', 'unknown'),
                'salary_range':      job.get('salary_range'),
                'job_description':   job.get('description', ''),
                'submission_method': 'browser_lambda',
                'status':            'pending',
                'llm_score':         job.get('llm_score'),
                'llm_score_reason':  job.get('llm_score_reason'),
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
        logger.info(
            'apply_one: application already exists for job_id=%s search_id=%d, skipping',
            job['job_id'], search.pk,
        )
        return False

    # Build payload — same shape regardless of dispatch method.
    try:
        payload = _build_lambda_payload(application, resume, cover_letter, ats)
    except Exception as exc:
        reason = f'Failed to build payload: {exc}'
        logger.exception('apply_one: payload build failed for job_id=%s', job['job_id'])
        application.status = 'failed'
        application.failure_reason = reason
        application.save(update_fields=['status', 'failure_reason'])
        return False

    # Dispatch — Lambda in prod, in-process in dev.
    use_lambda = getattr(settings, 'USE_LAMBDA', True)

    if use_lambda:
        return _dispatch_lambda(application, payload, job['job_id'], search.pk)
    else:
        return _dispatch_local(application, payload, job['job_id'], search.pk)


def _dispatch_lambda(
    application: Application,
    payload: dict,
    job_id: str,
    search_id: int,
) -> bool:
    """Invoke Lambda asynchronously and mark application as submitted."""
    try:
        invocation_id = _invoke_lambda(payload)

        application.lambda_invocation_id = invocation_id
        application.status = 'submitted'
        application.applied_at = datetime.now(tz=timezone.utc)
        application.save(update_fields=[
            'lambda_invocation_id', 'status', 'applied_at',
        ])

        logger.info(
            'apply_one: dispatched job_id=%s to Lambda (invocation_id=%s)',
            job_id, invocation_id,
        )
        return True

    except (BotoCoreError, ClientError) as exc:
        reason = f'Lambda invoke failed: {exc}'
    except RuntimeError as exc:
        reason = str(exc)
    except Exception as exc:
        reason = f'Unexpected error: {exc}'
        logger.exception('apply_one: unexpected Lambda error for job_id=%s search_id=%d', job_id, search_id)

    application.status = 'failed'
    application.failure_reason = reason
    application.save(update_fields=['status', 'failure_reason'])
    logger.error('apply_one: Lambda dispatch failed for job_id=%s: %s', job_id, reason)
    return False


def _dispatch_local(
    application: Application,
    payload: dict,
    job_id: str,
    search_id: int,
) -> bool:
    """Run the handler in-process (dev only) and update the application record."""
    logger.info(
        'apply_one: running handler in-process (USE_LAMBDA=False) for job_id=%s',
        job_id,
    )

    try:
        success, failure_reason = _run_local(payload)

        if success:
            application.status = 'submitted'
            application.applied_at = datetime.now(tz=timezone.utc)
            application.save(update_fields=['status', 'applied_at'])
            logger.info('apply_one: local handler succeeded for job_id=%s', job_id)
            return True
        else:
            application.status = 'failed'
            application.failure_reason = failure_reason
            application.save(update_fields=['status', 'failure_reason'])
            logger.warning(
                'apply_one: local handler failed for job_id=%s: %s',
                job_id, failure_reason,
            )
            return False

    except ImportError as exc:
        reason = str(exc)
        logger.error('apply_one: %s', reason)
    except Exception as exc:
        reason = f'Unexpected local handler error: {exc}'
        logger.exception('apply_one: unexpected error for job_id=%s search_id=%d', job_id, search_id)

    application.status = 'failed'
    application.failure_reason = reason
    application.save(update_fields=['status', 'failure_reason'])
    return False


# ---------------------------------------------------------------------------
# Public interface — called by daily_run
# ---------------------------------------------------------------------------

def apply_jobs(search_id: int, candidates: list[dict], log: RunLog) -> None:
    """
    Dispatch applications for each scored candidate job.

    Parameters
    ----------
    search_id:
        PK of the Search being processed.
    candidates:
        Scored job dicts from score_jobs. Jobs with _score_failed=True must
        already be filtered out by the caller (daily_run).
    log:
        The RunLog for this run. Updated in place with jobs_applied / jobs_failed.
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

    use_lambda = getattr(settings, 'USE_LAMBDA', True)
    logger.info(
        'apply_jobs: search_id=%d — %d candidates — USE_LAMBDA=%s',
        search_id, len(candidates), use_lambda,
    )

    applied = 0
    failed = 0

    for job in candidates:
        success = _apply_one(search, job, resume)
        if success:
            applied += 1
        else:
            failed += 1

    log.jobs_applied = applied
    log.jobs_failed = log.jobs_failed + failed
    log.save(update_fields=['jobs_applied', 'jobs_failed'])

    logger.info(
        'apply_jobs: search_id=%d — applied=%d failed=%d',
        search_id, applied, failed,
    )