"""
pipeline/ats — applicant tracking system integrations.

Current state
-------------
Direct API submission to Greenhouse and Lever requires the *employer's*
API key, which is not obtainable by a third-party applicant.  As a result,
all submissions currently route through Lambda (Browser Use) regardless of
ATS.

What lives here now
-------------------
``utils.detect_ats(url)``
    Detects which ATS a job URL belongs to.  Used by apply_job for logging
    and future routing.

What belongs here later
-----------------------
If direct-submission APIs become available (e.g. a future Greenhouse
applicant-facing OAuth flow, or a partner programme), add clients here:

    greenhouse.py  — GreenhouseClient
    lever.py       — LeverClient

Each client should expose a ``submit(application: Application, resume_url: str,
cover_letter: str) -> str`` interface that returns a confirmation ID and raises
on failure, so apply_job can swap it in with minimal changes.
"""

from .utils import detect_ats

__all__ = ['detect_ats']