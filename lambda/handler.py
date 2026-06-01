"""
handler.py — Lambda entry point for callback-submit-application.

Responsibilities
----------------
1. Parse the event payload from Django's apply_job task.
2. Download the resume PDF from the presigned S3 URL to /tmp/.
3. Run a browser-use Agent (backed by Claude) to navigate to the apply URL,
   fill the application form, upload the resume, and submit.
4. POST the result back to the Django callback endpoint with retry logic.

Payload contract (from apply_job.py)
--------------------------------------
{
    "application_id": int,
    "job_url":        str,   -- canonical job page (context/fallback)
    "apply_url":      str,   -- direct apply link — agent starts here
    "resume_url":     str,   -- presigned S3 GET URL (1hr expiry)
    "resume_filename": str,
    "cover_letter":   str,
    "user": {
        "first_name": str,
        "last_name":  str,
        "email":      str,
    },
    "ats":            str,   -- 'greenhouse' | 'lever' | 'other' (informational)
}

Callback contract (to Django)
------------------------------
POST /api/pipeline/applications/{application_id}/callback/
Headers: X-Callback-Secret: <CALLBACK_SECRET>
Body: {
    "status":         "submitted" | "failed",
    "failure_reason": str | null,
}

Environment variables
---------------------
ANTHROPIC_API_KEY   — Claude API key for browser-use Agent
DJANGO_CALLBACK_URL — Base URL of Django server, e.g. https://yourcallbackdomain.com
CALLBACK_SECRET     — Shared secret validated by Django on the callback endpoint

Reconciliation hook (V2)
-------------------------
Applications that never receive a callback (Lambda crash, network failure after
all retries) will remain in status='pending'. A future reconciliation task can
scan for Application rows where status='pending' and applied_at is older than
a configurable threshold, then re-queue them via a new Lambda invocation.
See jobs/tasks/reconcile_applications.py (not yet implemented).
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import httpx
from browser_use import Agent
from langchain_anthropic import ChatAnthropic

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DJANGO_CALLBACK_URL = os.environ['DJANGO_CALLBACK_URL'].rstrip('/')
CALLBACK_SECRET = os.environ['CALLBACK_SECRET']
ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']

# Retry config for the Django callback POST.
CALLBACK_MAX_ATTEMPTS = 3
CALLBACK_RETRY_DELAYS = [5, 15, 30]  # seconds between attempts

# browser-use agent
LLM_MODEL = 'claude-sonnet-4-20250514'
AGENT_MAX_STEPS = 50


# ---------------------------------------------------------------------------
# Resume download
# ---------------------------------------------------------------------------

def _download_resume(resume_url: str, filename: str) -> str:
    """
    Download the resume PDF from the presigned S3 URL to /tmp/.
    Returns the local file path.
    /tmp/ is the only writable directory in Lambda — max 512MB, cleared between
    cold starts but persists across warm invocations of the same container.
    """
    # Sanitise filename to avoid path traversal.
    safe_filename = Path(filename).name or 'resume.pdf'
    local_path = f'/tmp/{safe_filename}'

    logger.info('Downloading resume from S3 presigned URL → %s', local_path)

    with httpx.Client(timeout=30) as client:
        response = client.get(resume_url)
        response.raise_for_status()

    with open(local_path, 'wb') as f:
        f.write(response.content)

    logger.info('Resume downloaded: %d bytes', len(response.content))
    return local_path


# ---------------------------------------------------------------------------
# Browser-use agent task prompt
# ---------------------------------------------------------------------------

def _build_task_prompt(event: dict, resume_path: str) -> str:
    user = event['user']
    full_name = f"{user['first_name']} {user['last_name']}"
    cover_letter = event.get('cover_letter', '')
    ats = event.get('ats', 'other')

    cover_letter_instruction = (
        f'Cover letter to paste if there is a cover letter text field:\n\n{cover_letter}'
        if cover_letter
        else 'No cover letter is available. Skip any optional cover letter text fields.'
    )

    return f"""
You are applying for a job on behalf of {full_name}.

Navigate to the following URL and complete the job application form:
{event['apply_url']}

Applicant details:
- Full name: {full_name}
- First name: {user['first_name']}
- Last name: {user['last_name']}
- Email: {user['email']}

Resume file (already downloaded locally): {resume_path}
Upload this file to any resume upload field you find.

{cover_letter_instruction}

Instructions:
1. Fill in all required fields using the applicant details above.
2. Upload the resume file to the resume upload field.
3. If a cover letter FILE upload is present (not a text field), skip it — we only have text.
4. Answer any screening questions as best you can based on the applicant's name and email.
   If a question requires specific information you don't have, leave it blank if optional,
   or enter a reasonable placeholder if required.
5. Do NOT accept or decline any cookie banners — dismiss them if possible.
6. Submit the application form once all required fields are filled.
7. Confirm the submission was successful (look for a confirmation message or redirect).

ATS hint: {ats} (informational — use if helpful for navigation decisions)

If at any point the form cannot be completed or submitted, stop and report exactly
what went wrong so it can be logged.
""".strip()


# ---------------------------------------------------------------------------
# Application submission
# ---------------------------------------------------------------------------

async def _submit_application(event: dict, resume_path: str) -> tuple[bool, str | None]:
    """
    Run the browser-use agent to fill and submit the job application.

    Returns
    -------
    (success: bool, failure_reason: str | None)
    """
    task = _build_task_prompt(event, resume_path)

    llm = ChatAnthropic(
        model=LLM_MODEL,
        api_key=ANTHROPIC_API_KEY,
        timeout=120,
    )

    agent = Agent(
        task=task,
        llm=llm,
        max_failures=3,
    )

    logger.info(
        'Starting browser-use agent for application_id=%s apply_url=%s',
        event['application_id'],
        event['apply_url'],
    )

    try:
        result = await agent.run(max_steps=AGENT_MAX_STEPS)

        # browser-use returns an AgentHistoryList. Check the final result.
        if result.is_done() and not result.has_errors():
            logger.info(
                'Agent completed successfully for application_id=%s',
                event['application_id'],
            )
            return True, None
        else:
            final_result = result.final_result() or 'Agent finished without confirming submission.'
            logger.warning(
                'Agent finished with errors/incomplete for application_id=%s: %s',
                event['application_id'],
                final_result,
            )
            return False, str(final_result)[:2000]

    except Exception as exc:
        logger.exception(
            'Agent raised exception for application_id=%s',
            event['application_id'],
        )
        return False, f'Agent exception: {str(exc)[:1000]}'


# ---------------------------------------------------------------------------
# Django callback with retry
# ---------------------------------------------------------------------------

def _post_callback(application_id: int, status: str, failure_reason: str | None) -> None:
    """
    POST the application result back to Django.
    Retries up to CALLBACK_MAX_ATTEMPTS times with fixed delays.

    If all attempts fail, logs an error but does NOT raise — the Lambda
    function still exits cleanly so AWS doesn't retry the entire invocation
    (which would re-run the browser agent and duplicate the submission).

    A pending application that never received a callback will be caught by
    the future reconciliation task (V2).
    """
    url = f'{DJANGO_CALLBACK_URL}/api/pipeline/applications/{application_id}/callback/'
    payload = {
        'status': status,
        'failure_reason': failure_reason,
    }
    headers = {
        'Content-Type': 'application/json',
        'X-Callback-Secret': CALLBACK_SECRET,
    }

    for attempt in range(1, CALLBACK_MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()

            logger.info(
                'Callback succeeded for application_id=%d (attempt %d/%d)',
                application_id, attempt, CALLBACK_MAX_ATTEMPTS,
            )
            return

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(
                'Callback attempt %d/%d failed for application_id=%d: %s',
                attempt, CALLBACK_MAX_ATTEMPTS, application_id, exc,
            )

            if attempt < CALLBACK_MAX_ATTEMPTS:
                delay = CALLBACK_RETRY_DELAYS[attempt - 1]
                logger.info('Retrying callback in %ds...', delay)
                time.sleep(delay)

    # All attempts exhausted.
    logger.error(
        'All %d callback attempts failed for application_id=%d. '
        'Application will remain pending — reconciliation task will retry (V2).',
        CALLBACK_MAX_ATTEMPTS,
        application_id,
    )


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:
    """
    Lambda handler. Invoked asynchronously (InvocationType='Event') by Django.
    Return value is discarded by AWS for async invocations.
    """
    application_id = event.get('application_id')
    logger.info('Lambda invoked for application_id=%s', application_id)

    resume_path = None
    status = 'failed'
    failure_reason = 'Unknown error — Lambda did not complete normally.'

    try:
        # Step 1: Download resume.
        resume_path = _download_resume(
            event['resume_url'],
            event['resume_filename'],
        )

        # Step 2: Run browser-use agent.
        success, failure_reason = asyncio.run(
            _submit_application(event, resume_path)
        )
        status = 'submitted' if success else 'failed'

    except Exception as exc:
        failure_reason = f'Lambda error before agent start: {str(exc)[:1000]}'
        logger.exception('Unhandled error in Lambda handler for application_id=%s', application_id)

    finally:
        # Step 3: Always post callback, even on failure, so the Application
        # record doesn't stay stuck in 'pending' indefinitely.
        if application_id is not None:
            _post_callback(application_id, status, failure_reason)

        # Clean up resume from /tmp/ to avoid polluting warm container state.
        if resume_path and Path(resume_path).exists():
            Path(resume_path).unlink(missing_ok=True)
            logger.info('Cleaned up resume from /tmp/')

    return {'status': status, 'failure_reason': failure_reason}