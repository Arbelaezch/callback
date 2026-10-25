"""
callback/config.py — application constants.

All hardcoded, non-secret configuration lives here.
Environment-driven values (API keys, URLs, credentials) stay in settings.py.

Import directly in application code:
    from callback.config import LLM_MODEL, LLM_SCORE_THRESHOLD

For Celery config, settings.py imports the CELERY_* values from here
so they're picked up via app.config_from_object().
"""


# -----------------------------------------------------------------
# LLM
# -----------------------------------------------------------------

LLM_MODEL = 'claude-sonnet-4-20250514'
LLM_MAX_TOKENS = 1024
LLM_TIMEOUT_SECONDS = 30

# Document generation stages. Each stage has its own model so they can be
# swapped independently: a light model gathers context and verifies claims,
# a stronger model writes.
LLM_MODEL_SCOUT = 'claude-haiku-4-5-20251001'
LLM_MODEL_WRITER = 'claude-sonnet-5-5'
LLM_MODEL_VERIFIER = 'claude-haiku-4-5-20251001'
LLM_MAX_TOKENS_WRITER = 8192
LLM_MAX_TOKENS_SCOUT = 2048
LLM_TIMEOUT_SECONDS_LONG = 120  # PDF analysis and document writing

# Scout agent: tool-use rounds before it is forced to submit its brief.
SCOUT_MAX_STEPS = 8
SCOUT_TOOL_RESULT_MAX_CHARS = 6000
VOICE_SAMPLE_MAX_CHARS = 6000

# Context sources: sections longer than this are split on paragraph breaks.
CONTEXT_SECTION_MAX_CHARS = 2000
CONTEXT_UPLOAD_MAX_BYTES = 1024 * 1024
RESUME_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
CONTEXT_UPLOAD_EXTENSIONS = ('.md', '.txt')

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

# A refresh token blacklisted less than this many seconds ago gets a 401 that
# keeps cookies, so another tab's rotation does not log everyone out.
REFRESH_ROTATION_GRACE_SECONDS = 30

# -----------------------------------------------------------------
# Celery
# -----------------------------------------------------------------

# Beat schedule is managed entirely via django-celery-beat (DB-backed).
# Do not define CELERY_BEAT_SCHEDULE here — it would override the DB.
# Use `python manage.py sync_schedules` to push JobSearch state into beat.

# CELERY_TIMEZONE inherits Django's TIME_ZONE ('UTC').
# Change TIME_ZONE in settings.py to shift all scheduled tasks together.
CELERY_TIMEZONE = 'UTC'


# -----------------------------------------------------------------
# Background task timeouts
# -----------------------------------------------------------------

# Pending rows older than this are treated as lost, because the worker died.
PARSE_STALE_AFTER_MINUTES = 10
GENERATION_STALE_AFTER_MINUTES = 20
# Uploads index synchronously, so a source still pending this long means the
# request died. Must stay below SOURCE_POLL_TIMEOUT_MS in
# frontend/src/app/profile/page.js (3 min).
SOURCE_STALE_AFTER_MINUTES = 2


# -----------------------------------------------------------------
# Rate limits
# -----------------------------------------------------------------

# DRF throttle rates. Parse and generate are per user, login and register per IP.
# Token refresh and logout are intentionally not throttled.
THROTTLE_RATE_PARSE = '10/hour'
THROTTLE_RATE_GENERATE = '10/hour'
THROTTLE_RATE_LOGIN = '10/min'
THROTTLE_RATE_REGISTER = '5/hour'

# Daily caps, counted from DB rows over a rolling 24 hours, per user.
DAILY_PARSE_LIMIT = 30
DAILY_GENERATION_LIMIT = 30

# In-flight guards: a second request within this window gets a 409.
# Both must stay below the *_STALE_AFTER_MINUTES values above.
# Must match GENERATION_POLL_TIMEOUT_MS in frontend/src/app/jobs/[id]/page.js.
GENERATION_INFLIGHT_MINUTES = 5
# Must match PARSE_POLL_TIMEOUT_MS in frontend/src/app/profile/page.js.
PARSE_INFLIGHT_MINUTES = 3
