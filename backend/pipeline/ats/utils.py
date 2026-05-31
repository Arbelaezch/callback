"""
pipeline/ats/utils.py — ATS detection from job URLs.

Determines which applicant tracking system a job posting belongs to,
based on URL pattern matching.  Used by apply_job to route applications
and produce accurate logging.

Extend ``detect_ats`` when new direct-submission ATS integrations are added.
"""

from urllib.parse import urlparse


# Ordered list of (ats_name, hostname_fragment) pairs.
# First match wins.  'other' is the fallback and is never in this list.
_ATS_PATTERNS: list[tuple[str, str]] = [
    ('greenhouse', 'greenhouse.io'),
    ('lever',      'lever.co'),
]


def detect_ats(url: str) -> str:
    """
    Detect which ATS a job URL belongs to.

    Parameters
    ----------
    url:
        The apply URL or job URL from the normalised job dict.

    Returns
    -------
    str
        One of ``'greenhouse'``, ``'lever'``, or ``'other'``.
        Returns ``'other'`` for blank / unparseable URLs.
    """
    if not url:
        return 'other'

    try:
        hostname = urlparse(url).hostname or ''
    except ValueError:
        return 'other'

    hostname = hostname.lower()

    for ats_name, fragment in _ATS_PATTERNS:
        if fragment in hostname:
            return ats_name

    return 'other'