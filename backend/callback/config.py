"""
callback/config.py — application constants.

All hardcoded, non-secret configuration lives here.
Environment-driven values (API keys, URLs, credentials) stay in settings.py.

Import directly in application code:
    from callback.config import LLM_MODEL, LLM_SCORE_THRESHOLD

For Celery config, settings.py imports the CELERY_* values from here
so they're picked up via app.config_from_object().
"""

from celery.schedules import crontab

# -----------------------------------------------------------------
# LLM
# -----------------------------------------------------------------

LLM_MODEL = 'claude-sonnet-4-20250514'
LLM_MAX_TOKENS = 1024
LLM_TIMEOUT_SECONDS = 30

# Jobs below this score are filtered out before the apply stage.
LLM_SCORE_THRESHOLD = 7

# -----------------------------------------------------------------
# JSearch
# -----------------------------------------------------------------

JSEARCH_HOST = 'jsearch.p.rapidapi.com'
JSEARCH_TIMEOUT_SECONDS = 15
JSEARCH_PAGE_SIZE = 10  # results per API call; JSearch max is 10

# -----------------------------------------------------------------
# Auth
# -----------------------------------------------------------------

# Matches SIMPLE_JWT REFRESH_TOKEN_LIFETIME — kept here so cookie
# max-age and token lifetime are changed in one place.
AUTH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

# -----------------------------------------------------------------
# Celery beat schedule
# -----------------------------------------------------------------

# CELERY_TIMEZONE inherits Django's TIME_ZONE ('UTC').
# Change TIME_ZONE in settings.py to shift all scheduled tasks together.
CELERY_TIMEZONE = 'UTC'

CELERY_BEAT_SCHEDULE = {
    'daily-job-run': {
        'task': 'callback.tasks.daily_run',
        # Fires at 08:00 every day in CELERY_TIMEZONE.
        'schedule': crontab(hour=8, minute=0),
    },
}