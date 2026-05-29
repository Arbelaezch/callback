# AGENTS.md
# Instructions for AI coding agents working on this codebase.
# Read this before generating any code.

## Project
Callback — AI-powered job application agent.
Monorepo: Next.js frontend + Django backend + AWS Lambda function.

Runs daily per user — fetches jobs, scores relevance via LLM, submits applications autonomously via ATS APIs or browser automation. Goal is quality over volume: up to 5 targeted applications per day. The LLM does two jobs only: relevance scoring and cover letter personalization. Everything else is plumbing.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js (JS) |
| Backend | Django + DRF |
| Auth | Django auth + simplejwt |
| ORM | Django ORM |
| Database | Postgres (Docker) |
| Job queue | Celery + Redis (Docker) |
| Browser automation | AWS Lambda + Browser Use |
| Lambda deploy | Zip upload (→ SAM later) |
| Job discovery | JSearch API (RapidAPI) |
| LLM | Anthropic API (claude-sonnet-4-6) |
| File storage | AWS S3 |
| Email | Django SMTP (→ AWS SES later) |
| Error tracking | Sentry |
| Uptime | UptimeRobot |
| Reverse proxy | Nginx (host) |
| DNS + SSL | Cloudflare |
| Payments | Stripe (post-MVP) |
| Backups | pg_dump → S3 (cron) |

---

## Infrastructure

Self-hosted on Dell OptiPlex 7040. Browser Use jobs isolated to AWS Lambda — never touch the home server.

```
Host (OptiPlex)
├── Nginx (reverse proxy, host-level)
├── callback/docker-compose.yml
│   ├── django (gunicorn :8002)
│   ├── celery worker
│   ├── celery-beat (django-celery-beat DB scheduler)
│   ├── redis
│   └── postgres
└── portfolio/docker-compose.yml
    ├── django (gunicorn :8001)
    └── postgres

AWS
└── Lambda: callback-submit-application (Browser Use)

S3
├── resumes/
├── cover_letters/
└── backups/
```

---

## Project Structure

```
/frontend
  /src
    /app
      /(auth)
        /login           # login page
        /register        # register page
      /dashboard         # pipeline controls, run logs, applications
      /onboarding        # profile setup, file upload
      layout.js          # root layout — wraps app in AuthProvider
      globals.css        # global styles
      page.js            # redirects to /dashboard
    /components
      /layout
        Navbar.js        # auth-aware nav — reads from AuthContext
      /ui
        TagInput.js      # tag/chip input for arrays
    /contexts
      AuthContext.js     # AuthProvider + useAuth hook — single source of truth for auth state
    /hooks
      /onboarding
        useChoices.js    # fetches + caches job choice fields from API
    /lib
      apiClient.js       # fetch wrapper — all API calls go through here
      auth.js            # auth helpers (login, logout, register, getMe)
    proxy.js             # route protection — redirects unauthenticated users

/backend
  /callback              # Django project config — settings, URLs, Celery, wsgi only
    config.py            # non-secret constants (LLM model, timeouts, thresholds)
    celery.py            # Celery app — autodiscovers tasks from pipeline app
    db_config.py         # database config logic (dev vs prod)
    health.py            # /api/health/ endpoint
    settings.py          # Django settings — reads from .env via python-dotenv; imports constants from config.py
    urls.py              # root URL config
    wsgi.py

  /pipeline              # Django app — all job pipeline business logic, no models
    /tasks
      __init__.py        # imports daily_run so Celery autodiscovery registers it
      daily_run.py       # orchestrator Celery task — scan → score → apply (stub) → log
      scan_jobs.py       # JSearch fetch + dedup against JobSeen (user-scoped)
      score_jobs.py      # LLM scoring, threshold filter, top-N selection
      apply_job.py       # ATS detection + Lambda dispatch (not yet implemented)
      send_digest.py     # daily digest email (not yet implemented)
    /llm
      __init__.py        # exports score_job, personalize_cover_letter
      client.py          # Anthropic SDK wrapper — never imported directly by callers
    /jsearch
      __init__.py
      client.py          # JSearch API wrapper — pluggable query strategies
    /ats
      __init__.py
      greenhouse.py      # Greenhouse API client (not yet implemented)
      lever.py           # Lever API client (not yet implemented)
    storage.py           # S3 helpers (upload, delete) — dev stub, prod S3
    apps.py

  /users                 # Django app — auth, user model, resume, portfolio, cover letter sample
    admin.py
    authentication.py    # CookieJWTAuthentication backend
    models.py            # CustomUser, Resume, Portfolio, CoverLetterSample
    serializers.py       # RegisterSerializer, UserSerializer, ResumeSerializer,
                         #   PortfolioSerializer, CoverLetterSampleSerializer,
                         #   SearchSerializer, OnboardingSerializer
    views.py             # RegisterView, LoginView, LogoutView, MeView, OnboardingView, RefreshView

  /jobs                  # Django app — agent, searches, applications, run logs
    admin.py             # AgentAdmin, SearchAdmin (with trigger_run action), ApplicationAdmin,
                         #   RunLogAdmin, JobSeenAdmin
    models.py            # Agent, Search, JobSeen, Application, RunLog
    serializers.py       # AgentSerializer, SearchSerializer, RunLogSerializer,
                         #   ApplicationSerializer
    views.py             # ChoicesView, AgentView, SearchListView, SearchToggleView,
                         #   SearchTriggerView, SearchRunLogView, SearchScheduleView,
                         #   ApplicationListView
    urls.py              # /api/jobs/*
    management/
      commands/
        sync_schedules.py  # syncs Search.schedule_enabled → django-celery-beat PeriodicTask

  /notifications         # Django app — notification preferences + delivery (placeholder)
    models.py            # placeholder — no models yet

/lambda
  handler.py             # Browser Use submission
  requirements.txt
  deploy.sh              # zip + aws lambda update-function-code
```

---

## Django Apps

| App | Purpose |
|---|---|
| `callback` | Project config only — settings, URLs, Celery, wsgi. No models, no views. |
| `pipeline` | All job pipeline business logic — tasks, LLM, JSearch, ATS, storage. No models. |
| `jobs` | Agent, Search configs, applications, run logs. Models + serializers + views + admin. |
| `users` | Auth, custom user model, Resume, Portfolio, CoverLetterSample. Models + serializers + views. |
| `notifications` | Notification preferences and delivery. Models placeholder — not yet implemented. |

---

## Database

```
users (CustomUser)       -- extends AbstractUser, created_at/updated_at

resumes                  -- user_id, label, s3_key, filename, is_default, status,
                         --   uploaded_at, updated_at
portfolios               -- user_id, label, body, is_default, created_at, updated_at
cover_letter_samples     -- user_id, label, body, is_default, created_at, updated_at

agents                   -- user_id (OneToOne), name, active, created_at, updated_at
searches                 -- agent_id, label, role_titles[], cities[], location_types[],
                         --   seniority_levels[], years_experience, salary_min,
                         --   excluded_companies[], resume_id, portfolio_id,
                         --   cover_letter_sample_id, daily_target, active,
                         --   schedule_enabled, job_cooldown, created_at, updated_at
jobs_seen                -- user_id, job_id, seen_at
applications             -- search_id, resume_id, job_id, job_url, company, role_title,
                         --   location, remote_type, salary_range, job_description, source,
                         --   status, submission_method, cover_letter_used,
                         --   lambda_invocation_id, failure_reason, llm_score,
                         --   llm_score_reason, applied_at, created_at
run_logs                 -- search_id, run_at, jobs_fetched, jobs_scored, jobs_applied,
                         --   jobs_failed, jobs_skipped, status, error
```

**Key design decisions:**

`Agent` — singleton per user. Master on/off switch. All Searches belong to an Agent.

`Search` — one job search configuration. Users can have multiple. Gated by subscription tier.

`JobSeen` — pipeline dedup table scoped to **user** (not search). Prevents re-processing the same job listing across multiple Searches. Separate from `Application` — JobSeen answers "have we processed this job?", Application answers "have we applied?". Re-eligibility controlled by `Search.job_cooldown` (days) — pipeline filters on `seen_at >= now - cooldown`.

`Portfolio` — free-text repository of accomplishments, skills, projects. LLM draws from this when scoring and generating cover letters. Future refactor will add `PortfolioEntry` children and drop `body`.

`CoverLetterSample` — a cover letter written in the user's voice. LLM uses this to match tone. Not submitted directly. Named "sample" to signal it's source material, not the final output.

`status` (resume): `pending` `ready` `failed`
`status` (application): `pending` `submitted` `failed` `deleted` `skipped`
`status` (run_log): `running` `completed` `partial` `failed`
`submission_method`: `greenhouse_api` `lever_api` `browser_lambda`

---

## Celery Beat — DB-Backed Scheduling

Beat schedule is managed via `django-celery-beat` (DB-backed). **Do not define `CELERY_BEAT_SCHEDULE` in `config.py` or `settings.py`** — it would override the database.

`Search.schedule_enabled` is the source of truth. `sync_schedules` management command syncs it to `PeriodicTask` entries. Run on container startup and called automatically by `SearchScheduleView` after any toggle.

```bash
python manage.py sync_schedules
```

Each scheduled Search gets its own `PeriodicTask` named `run-search-<id>`. Disabling removes the task entirely. Beat command must include the scheduler flag:

```
celery -A callback beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

All searches default to `schedule_enabled=False`. Users opt in via the dashboard.

---

## Daily Loop

```
Celery beat cron (per scheduled Search, 08:00 UTC)
  or manual trigger via POST /api/jobs/searches/<id>/trigger/
  → Agent.active check (master kill switch)
  → Search.active check
  → JSearch: fetch jobs by role_titles + cities + location_types
  → Postgres: dedup against jobs_seen (user-scoped, filtered by job_cooldown)
  → LLM: score each new job (1-10) vs Search profile (_build_profile)
  → Select top N (capped at Search.daily_target)
  → Per job:
      → Greenhouse URL → Greenhouse API
      → Lever URL     → Lever API
      → Other         → invoke Lambda (Browser Use)
      → LLM: personalize cover letter
      → Write to applications table
  → Django SMTP: daily digest email
  → Update RunLog with final counts + status
```

---

## LLM Calls

**Scoring — one call per unseen job:**
```
system: You are a job fit evaluator. Return only JSON, no preamble.
user:   Job: {title, company, description, requirements}
        Profile: {target_roles, seniority_levels, years_experience,
                  location_types, experience_summary}
        Return: { "score": 1-10, "reason": "string" }
```

`experience_summary` currently sourced from `CoverLetterSample.body[:1000]`.
Future: prefer `Portfolio.body` — richer, more structured source material.

**Cover letter — one call per application:**
```
system: Modify only: company name, role title, and one opening sentence.
        Return only the full cover letter text.
user:   Template: {cover_letter_text}
        Job: {company, role_title, brief_description}
```

Cost: <$0.01 per application at current Anthropic pricing.

---

## Auth

JWT via `djangorestframework-simplejwt`. Tokens stored in httpOnly cookies — never localStorage.

- `access_token` cookie — 15 min lifetime
- `refresh_token` cookie — 7 day lifetime, rotated on refresh, blacklisted on logout
- `CookieJWTAuthentication` in `users/authentication.py` reads token from cookie, falls back to Authorization header
- All endpoints require `IsAuthenticated` unless explicitly decorated with `@permission_classes([AllowAny])`
- `secure=not DEBUG` on cookies — works over HTTP in dev, HTTPS only in prod
- Token refresh handled silently in `apiClient.js` — on 401, attempts `POST /api/auth/token/refresh/` then retries once
- Auth endpoints (`/api/auth/*`) skip the refresh flow and throw immediately
- `AuthContext.js` is the single source of truth for user state — components read via `useAuth()`, never call `getMe()` directly

---

## File Upload — Two-Phase Pattern

Resume uploads use a two-phase pattern to avoid orphaned files or records:

1. Create `Resume` record with `status='pending'` and empty `s3_key` inside `transaction.atomic()`
2. Upload file to S3 (or dev stub) outside the transaction
3. On success: update `s3_key` and `status='ready'`
4. On failure: update `status='failed'`, return error to user

Daily loop tasks must filter `resume__status='ready'` when selecting resumes for applications.

`pipeline/storage.py` currently stubs S3 — saves to `/tmp/` in dev. Replace with real boto3 calls when S3 is configured.

---

## Onboarding Flow

Single `POST /api/onboarding/` creates all records atomically:
1. `Resume` (pending) + S3 upload outside transaction
2. `Portfolio` (optional — user can fill in more later)
3. `CoverLetterSample`
4. `Agent` (via `get_or_create` — safe to call multiple times)
5. First `Search` linked to all of the above

Free tier: one resume only (checked at onboarding entry). Upgrade prompt scaffolded.

---

## API Endpoints

### Auth — `/api/auth/`
| Method | Path | Description |
|---|---|---|
| POST | `/register/` | Register new user |
| POST | `/login/` | Login |
| POST | `/logout/` | Logout + blacklist refresh token |
| GET | `/me/` | Current user |
| POST | `/token/refresh/` | Refresh access token |

### Jobs — `/api/jobs/`
| Method | Path | Description |
|---|---|---|
| GET | `/choices/` | All choice field options for frontend |
| GET | `/agent/` | Get user's agent (creates on first call) |
| PATCH | `/agent/` | Update agent name or active state |
| GET | `/searches/` | All searches with last run info |
| PATCH | `/searches/<id>/toggle/` | Flip Search.active |
| POST | `/searches/<id>/trigger/` | Manually fire daily_run for a Search |
| GET | `/searches/<id>/runs/` | Last 10 RunLog entries for a Search |
| PATCH | `/searches/<id>/schedule/` | Toggle schedule_enabled + sync to beat |
| GET | `/applications/` | All applications for the user |

### Onboarding — `/api/`
| Method | Path | Description |
|---|---|---|
| POST | `/onboarding/` | Submit all onboarding data in one request |

---

## Lambda

**Function:** `callback-submit-application` — one invocation per application (fan-out). Lambda writes result directly back to Postgres on completion. 15-min timeout.

**Payload:**
```json
{
  "job_url": "...",
  "apply_url": "...",
  "resume_s3_key": "resumes/user_123.pdf",
  "cover_letter": "...",
  "user_id": 123,
  "application_id": 456
}
```

**Deploy:**
```bash
cd lambda
pip install -r requirements.txt -t package/
cp handler.py package/
cd package && zip -r ../function.zip .
aws lambda update-function-code \
  --function-name callback-submit-application \
  --zip-file fileb://../function.zip
```

---

## Settings

Non-secret constants live in `callback/config.py` and are imported into `settings.py`.

Rule of thumb:
- Value comes from the environment → `settings.py` via `os.environ`
- Value is a hardcoded constant → `config.py`
- Value is a secret → `.env` only, never committed

Application code imports constants directly from `callback.config`, not from `django.conf.settings`, unless Django itself requires the value on the settings module.

---

## Backend — Module Interfaces

### `callback/config.py` — application constants
- `LLM_MODEL` — Anthropic model string
- `LLM_SCORE_THRESHOLD` — minimum score (inclusive) to pass to apply stage
- `JSEARCH_HOST`, `JSEARCH_TIMEOUT_SECONDS`, `JSEARCH_PAGE_SIZE`
- `AUTH_COOKIE_MAX_AGE` — must match `SIMPLE_JWT.REFRESH_TOKEN_LIFETIME`
- `CELERY_TIMEZONE`

### `pipeline/storage.py`
- `upload_resume(file, user_id: int) -> str` — returns S3 key
- `delete_resume(s3_key: str) -> None`

### `pipeline/llm/`
Import via `from pipeline.llm import score_job, personalize_cover_letter`.

- `score_job(job: dict, profile: dict) -> dict`
  - `profile` keys: `target_roles`, `seniority_levels`, `years_experience`, `location_types`, `experience_summary`
  - Returns `{ "score": int (1–10), "reason": str }`

- `personalize_cover_letter(template: str, job: dict) -> str`

### `pipeline/jsearch/client.py`
- `fetch_jobs(role_titles, cities, location_types, strategy='combined') -> list[dict]`
  - Never raises — logs and returns `[]` on error
  - Normalised job keys: `job_id`, `title`, `company`, `description`, `job_url`, `location`, `remote_type`, `salary_range`, `apply_link`

### `pipeline/tasks/scan_jobs.py`
- `scan_jobs(search_id: int) -> list[dict]`
  - Fetches jobs, deduplicates against `JobSeen` (user-scoped, filtered by `Search.job_cooldown`)
  - Updates `seen_at` for re-eligible jobs, bulk-inserts new `JobSeen` records
  - Returns unseen job dicts. Idempotent.

### `pipeline/tasks/score_jobs.py`
- `score_jobs(search_id: int, unseen_jobs: list[dict]) -> list[dict]`
  - Builds profile via `_build_profile(search)` — currently uses `CoverLetterSample.body` as experience summary
  - Scores via LLM, filters by `LLM_SCORE_THRESHOLD`, sorts descending, caps at `Search.daily_target`
  - Failures flagged with `_score_failed: True` — appended after candidates

### `pipeline/tasks/daily_run.py`
- `daily_run(search_id: int | None = None)` — Celery task
  - Checks `Agent.active` (master switch) then `Search.active` before running
  - Pass `search_id` to run one search; omit to run all active searches (fallback only)
  - Creates and updates a `RunLog` per search. Per-search failures are isolated.

### `jobs/management/commands/sync_schedules.py`
- `sync_schedules()` — callable directly or via `python manage.py sync_schedules`
  - Reads all `Search.schedule_enabled` values
  - Creates/updates `PeriodicTask` for enabled searches, deletes for disabled
  - Called on container startup and by `SearchScheduleView` after every toggle

---

## Frontend — Next.js

### Version & Router
- Next.js 15, App Router only
- Never use Pages Router
- Never use `getServerSideProps`, `getStaticProps`, `getInitialProps`

### Components
- Server Components by default — add `"use client"` only for state, effects, browser APIs, or event listeners
- Keep `"use client"` components small and at the leaves
- Functional components only — no class components

### Styling
- Tailwind CSS only — design tokens as CSS variables in `globals.css`
- Dark theme, cool blue/slate palette
- No CSS modules, styled-components, emotion, or inline `style` props

### API Communication
- All API calls through `src/lib/apiClient.js` — never call fetch directly in components
- File uploads use `apiClient.multipart()` — omits `Content-Type` so browser sets boundary
- Always pass `credentials: 'include'` — handled by `apiClient.js`

### Module Interfaces

#### `src/lib/apiClient.js`
- `apiClient.get(path)`
- `apiClient.post(path, body)`
- `apiClient.patch(path, body)`
- `apiClient.delete(path)`
- `apiClient.multipart(path, formData)`
- Throws `{ status, ...detail }` on non-2xx; returns `null` on 204

#### `src/lib/auth.js`
- `register({ username, email, password })`
- `login({ username, password })`
- `logout()`
- `getMe()` → current user object

#### `src/hooks/onboarding/useChoices.js`
- `useChoices()` → `{ choices, loading, error }`
- `choices` shape: `location_types`, `seniority_levels`, `application_statuses`, `submission_methods`, `remote_types`

#### `src/contexts/AuthContext.js`
- `useAuth()` → `{ user, loading, refresh, logout }`
- Never call `getMe()` directly in components

---

## General

### Never do this
- No TypeScript — plain JS only in frontend
- No `console.log` in committed code — use proper logging
- No hardcoded URLs, API keys, or credentials
- No `TODO` comments without a linked task

### Git
- Branch from `main`: `feature/`, `fix/`, `chore/`
- Commit messages: imperative present tense (`Add job scoring task`)
- Never commit `.env`, `node_modules/`, `__pycache__/`, or build artifacts