"""
lambda_runner.py — local dev shim for the Lambda handler.

In production, apply_job.py invokes the Lambda function asynchronously via
boto3. Locally (USE_LAMBDA=False), apply_job.py calls run_handler() here
instead, which executes the exact same handler logic in-process.

This means:
- Same payload shape
- Same browser-use agent
- Same Playwright + Chromium
- Same callback to Django
- No AWS, no deployment, no cold start

Prerequisites (local dev only — not needed in prod Django):
    pip install browser-use playwright langchain-anthropic
    playwright install chromium

The handler module is imported lazily so that the rest of the Django app
doesn't depend on browser-use / Playwright being installed in prod.
"""

import logging

logger = logging.getLogger(__name__)


def run_handler(payload: dict) -> dict:
    """
    Run the Lambda handler in-process with the given payload.

    Parameters
    ----------
    payload:
        The same dict that apply_job._build_lambda_payload() produces —
        application_id, job_url, apply_url, resume_url, resume_filename,
        cover_letter, user, ats.

    Returns
    -------
    dict
        The handler's return value: {'status': 'submitted' | 'failed'}

    Raises
    ------
    ImportError
        If browser-use or Playwright aren't installed locally.
        Install with: pip install browser-use playwright && playwright install chromium
    """
    try:
        # Import lazily — handler.py depends on browser-use + Playwright
        # which are not installed in the prod Django environment.
        import sys
        import os

        # Add the lambda/ directory to sys.path so handler.py is importable.
        lambda_dir = os.path.join(
            os.path.dirname(__file__),   # backend/
            '..',                         # repo root
            'lambda',
        )
        lambda_dir = os.path.abspath(lambda_dir)

        if lambda_dir not in sys.path:
            sys.path.insert(0, lambda_dir)

        from handler import handler as lambda_handler

    except ImportError as exc:
        raise ImportError(
            'browser-use and Playwright must be installed locally to run the '
            'Lambda handler in-process.\n'
            'Run: pip install browser-use playwright && playwright install chromium\n'
            f'Original error: {exc}'
        ) from exc

    logger.info(
        'lambda_runner: running handler in-process for application_id=%s',
        payload.get('application_id'),
    )

    result = lambda_handler(payload, context=None)

    logger.info(
        'lambda_runner: handler completed for application_id=%s — status=%s',
        payload.get('application_id'),
        result.get('status'),
    )

    return result