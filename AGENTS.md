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
      /dashboard         # history, pause/resume, preferences
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
  /callback
    config.py            # non-secret constants (LLM model, timeouts, beat schedule, thresholds)
    celery.py            # Celery app — autodiscovers tasks, reads config from Django settings
    db_config.py         # database config logic (dev vs prod)
    health.py            # /api/health/ endpoint
    settings.py          # Django settings — reads from .env via python-dotenv; imports constants from config.py
    storage.py           # S3 helpers (upload, delete) — dev stub, prod S3
    urls.py              # root URL config
    /tasks
      __init__.py
      daily_run.py       # orchestrator Celery task — scan → score → apply (stub) → log
      scan_jobs.py       # JSearch fetch + dedup against jobs_seen
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
      greenhouse.py      # Greenhouse API client (not yet implemented)
      lever.py           # Lever API client (not yet implemented)
  /users
    admin.py
    authentication.py    # CookieJWTAuthentication backend
    models.py            # CustomUser, Resume, CoverLetterTemplate
    serializers.py       # RegisterSerializer, UserSerializer, OnboardingSerializer
    views.py             # RegisterView, LoginView, LogoutView, MeView, OnboardingView
  /jobs
    admin.py
    models.py            # JobSearch, JobSeen, Application, DailyRunLog
    views.py             # ChoicesView
    urls.py              # /api/jobs/choices/

/lambda
  handler.py             # Browser Use submission
  requirements.txt
  deploy.sh              # zip + aws lambda update-function-code
```

---

## Database

```
users (CustomUser)       -- extends AbstractUser, created_at/updated_at
resumes                  -- s3_key, filename, is_default, status, user_id
cover_letter_templates   -- label, body, is_default, user_id
job_searches             -- role_titles[], cities[], location_types[], seniority_levels[],
                         --   years_experience, salary_min, excluded_companies[],
                         --   resume, cover_letter_template, daily_limit, active
jobs_seen                -- job_search_id, job_id, seen_at
applications             -- job_search_id, resume_id, job_id, job_url, company, role_title,
                         --   status, submission_method, llm_score, llm_score_reason,
                         --   cover_letter_used, lambda_invocation_id, failure_reason,
                         --   applied_at, created_at
daily_run_logs           -- job_search_id, run_at, jobs_fetched, jobs_scored,
                         --   jobs_applied, jobs_failed, jobs_skipped, status, error
```

`status` (resume): `pending` `ready` `failed` — two-phase upload pattern; daily loop only uses `ready` resumes
`status` (application): `pending` `submitted` `failed` `skipped`
`status` (daily_run_log): `running` `completed` `partial` `failed`
`submission_method`: `greenhouse_api` `lever_api` `browser_lambda`

---

## Daily Loop

```
Celery beat cron (daily, per active user)
  → JSearch: fetch jobs by role_titles + cities + location_types
  → Postgres: dedup against jobs_seen
  → LLM: score each new job (1-10) vs user profile
  → Select top N (default 5, up to daily_limit)
  → Per job:
      → Greenhouse URL → Greenhouse API
      → Lever URL     → Lever API
      → Other         → invoke Lambda (Browser Use)
      → LLM: personalize cover letter
      → Write to applications table
  → Django SMTP: daily digest email
```

---

## LLM Calls

**Scoring — one call per unseen job:**
```
system: You are a job fit evaluator. Return only JSON, no preamble.
user:   Job: {title, company, description, requirements}
        Profile: {target_roles, skills, experience_summary, remote_pref}
        Return: { "score": 1-10, "reason": "string" }
```

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
- Open redirect protection on the `next` param in middleware and login page — only relative paths accepted
- Token refresh handled silently in `apiClient.js` — on 401, attempts 
  `POST /api/auth/token/refresh/` then retries the original request once
- Auth endpoints (`/api/auth/*`) skip the refresh flow and throw immediately
- `AuthContext.js` is the single source of truth for user state — 
  components read via `useAuth()`, never call `getMe()` directly

Scaffolded for future social auth at `/api/auth/social/` and password reset/email verification endpoints.

---

## File Upload — Two-Phase Pattern

Resume uploads use a two-phase pattern to avoid orphaned files or records:

1. Create `Resume` record with `status='pending'` and empty `s3_key` inside `transaction.atomic()`
2. Upload file to S3 (or dev stub) outside the transaction
3. On success: update `s3_key` and `status='ready'`
4. On failure: update `status='failed'`, return error to user

Daily loop tasks must filter `resume__status='ready'` when selecting resumes for applications.

`storage.py` currently stubs S3 — saves to `/tmp/` in dev. Replace the stub with real boto3 calls when S3 is configured.

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

## Backups

```bash
# /etc/cron.d/callback-backup — runs 3am daily
0 3 * * * root pg_dump $DATABASE_URL | gzip | \
  aws s3 cp - s3://callback-backups/$(date +%Y-%m-%d).sql.gz
```

---

## Roadmap

**MVP**
- [x] Django + Next.js, Dockerized
- [x] Models + migrations
- [x] Auth (simplejwt + httpOnly cookies)
- [x] Onboarding + file upload (dev stub — S3 wiring pending)
- [ ] Nginx host config
- [ ] Wire up S3 for real file uploads
- [ ] Celery beat cron
- [ ] JSearch client + fetch + dedup
- [ ] LLM scoring
- [ ] Greenhouse + Lever clients
- [ ] Lambda (Browser Use) + deploy script
- [ ] Cover letter personalization
- [ ] Fan-out Lambda dispatch
- [ ] Digest email (Django SMTP)
- [ ] Dashboard
- [ ] Sentry + UptimeRobot
- [ ] pg_dump → S3 cron
- [ ] Deploy

**V2** — approve-before-apply (SMS), expanded boards, retry logic, Stripe

**V3** — modular resume, LLM assembly, PDF generation per application

**V4** — multi-vertical, interview prep, analytics, staging environment

---

## Settings

Non-secret constants (LLM model, timeouts, score threshold, beat schedule) live in `callback/config.py`
and are imported into `settings.py` via `from callback import config`. This keeps `settings.py`
env-only and makes constants safe to commit.

Rule of thumb:

- Value comes from the environment → `settings.py` via `os.environ`
- Value is a hardcoded constant → `config.py`
- Value is a secret → `.env` only, never committed
Application code that needs a constant imports directly from `callback.config`, not from
`django.conf.settings`, unless Django itself requires the value to be on the settings module
(e.g. Celery beat schedule, which is read via `config_from_object`).

---

## Frontend — Next.js

### Version & Router
- Next.js 15, App Router only
- Never use Pages Router (`/pages` directory does not exist)
- Never use `getServerSideProps`, `getStaticProps`, `getInitialProps`

### Components
- Server Components by default — do not add `"use client"` unless the component needs:
  - `useState` / `useReducer`
  - `useEffect`
  - Browser APIs
  - Event listeners
- Keep `"use client"` components small and pushed to the leaves of the tree
- No class components — functional components only

### Data Fetching
- Fetch data in Server Components using async/await directly
- Use `fetch()` with Next.js cache options (`{ cache: 'no-store' }` or `{ next: { revalidate: N } }`)
- Client-side fetching: use SWR or native fetch in a `"use client"` component
- Never use `axios` — use native `fetch`

### Routing & Navigation
- Use `next/navigation` not `next/router`
  - `useRouter` from `next/navigation`
  - `usePathname`, `useSearchParams` from `next/navigation`
- Use `next/link` for all internal links
- File-based routing only — no manual route config

### Imports
- Use `@/` alias for all imports from the src root
- Example: `import Button from '@/components/ui/Button'`
- Never use relative imports that traverse up more than one level

### Styling
- Tailwind CSS only — design tokens defined as CSS variables in `globals.css`
- Dark theme, cool blue/slate palette — see `globals.css` for variable definitions
- `tailwind.config.js` maps all CSS variables to Tailwind color tokens
- No CSS modules, no styled-components, no emotion
- No inline `style` props unless dynamically computed

### Hooks
- Custom hooks live in `src/hooks/` organized by feature (e.g. `hooks/onboarding/useChoices.js`)
- Import via `@/hooks/feature/useHookName`

### Images
- Always use `next/image` — never a raw `<img>` tag

### Fonts
- Use `next/font` — never import fonts via `<link>` in layout

### Metadata
- Use the `export const metadata` API in `layout.js` or `page.js`
- Never use `next/head`

### Environment Variables
- Server-only vars: `VARIABLE_NAME` (never exposed to browser)
- Browser-safe vars: `NEXT_PUBLIC_VARIABLE_NAME`
- Access via `process.env.VARIABLE_NAME` — never hardcode values

### API Communication
- All API calls go through `src/lib/apiClient.js` — never call fetch directly in components
- Exception: multipart file uploads use `apiClient.multipart()` which omits `Content-Type` so the browser sets the boundary
- Django backend at `process.env.NEXT_PUBLIC_API_URL`
- JWT stored in httpOnly cookie — never localStorage
- Always pass `credentials: 'include'` — handled by `apiClient.js`

### API Proxy
- All `/api/*` requests are proxied to `INTERNAL_API_URL` (Django) via rewrites in `next.config.mjs`
- Browser always talks to `localhost:3000` — never directly to Django in dev
- `NEXT_PUBLIC_API_URL` must be `http://localhost:3000` in dev
- `INTERNAL_API_URL=http://backend:8000` is server-side only (not `NEXT_PUBLIC_`)
- In prod, Nginx handles this routing — Next.js rewrites are dev-only

### Module Interfaces

#### `src/lib/apiClient.js` — HTTP client
- `apiClient.get(path)`
- `apiClient.post(path, body)`
- `apiClient.patch(path, body)`
- `apiClient.delete(path)`
- `apiClient.multipart(path, formData)` — file uploads; omits `Content-Type` so the browser sets the multipart boundary
- Always sends `credentials: 'include'` — cookies handled automatically
- Throws `{ status, ...detail }` on non-2xx; returns `null` on 204

#### `src/lib/auth.js` — auth helpers
- `register({ username, email, password })`
- `login({ username, password })`
- `logout()`
- `getMe()` → current user object
- All calls go through `apiClient` — no direct fetch
- Cookie-setting is server-side; callers don't handle tokens

#### `src/hooks/onboarding/useChoices.js`
- `useChoices()` → `{ choices, loading, error }`
- Fetches `/api/jobs/choices/` once and caches in module scope
- `choices` shape: `location_types`, `seniority_levels`, `application_statuses`, `submission_methods`, `remote_types` — each an array of `{ value, label }`

#### `src/contexts/AuthContext.js` — auth state
- `AuthProvider` — wraps the app in `layout.js`; fetches `getMe()` once on mount
- `useAuth()` → `{ user, loading, refresh, logout }`
  - `user` — current user object or `null`
  - `loading` — true until first `getMe()` resolves
  - `refresh()` — re-fetches current user (call after login/register)
  - `logout()` — calls `auth.logout()` and clears user state
- Never call `getMe()` directly in components — use `useAuth()` instead

---

## Backend — Django

### Version & Style
- Django 5.x + Django REST Framework
- Class-based views (`APIView`, `ModelViewSet`) preferred throughout for consistency
- Function-based views (`@api_view`) only for one-off utility endpoints like health checks

### Auth
- `djangorestframework-simplejwt` for JWT tokens
- All endpoints require `IsAuthenticated` unless explicitly public
- Public endpoints must explicitly set `@permission_classes([AllowAny])`

### Models
- Use Django ORM — no raw SQL unless absolutely necessary
- Always define `__str__` on every model
- Use `created_at` / `updated_at` timestamps on all models via a base model or explicit fields
- Always use `settings.AUTH_USER_MODEL` for FK references to the user model — never import `User` directly
- Custom user model is `users.CustomUser` (extends `AbstractUser`) — `AUTH_USER_MODEL = 'users.CustomUser'`

### Settings
- Use `python-dotenv` + `os.environ` for env var access
- `.env` lives at the monorepo root — loaded in `settings.py` via `load_dotenv(BASE_DIR.parent / '.env')`
- Database config is in `callback/db_config.py` — dev uses individual `POSTGRES_*` vars, prod parses `DATABASE_URL`
- Never use `os.environ` directly in application code outside of `settings.py` and `db_config.py`
- Never hardcode secrets

### Celery
- All background tasks in `/callback/tasks/`
- Tasks must be idempotent — safe to retry on failure
- Always use `.delay()` or `.apply_async()` — never call task functions directly
- Log task start, success, and failure explicitly

### URLs
- All API endpoints prefixed with `/api/`
- Version prefix not required at MVP (`/api/jobs/` not `/api/v1/jobs/`)

### Module Interfaces

### `callback/config.py` — application constants

All hardcoded, non-secret configuration. Import directly in application code — do not
read these via `django.conf.settings` unless Django requires it.

Constants:

- `LLM_MODEL` — Anthropic model string
- `LLM_MAX_TOKENS` — max tokens for all LLM calls
- `LLM_TIMEOUT_SECONDS` — Anthropic client timeout
- `LLM_SCORE_THRESHOLD` — minimum score (inclusive) to pass a job to the apply stage
- `JSEARCH_HOST` — RapidAPI host header value
- `JSEARCH_TIMEOUT_SECONDS` — httpx timeout for JSearch calls
- `JSEARCH_PAGE_SIZE` — results per JSearch API call (max 10)
- `AUTH_COOKIE_MAX_AGE` — cookie max-age in seconds; must match `SIMPLE_JWT.REFRESH_TOKEN_LIFETIME`
- `CELERY_TIMEZONE` — timezone for beat schedule; inherits Django `TIME_ZONE`
- `CELERY_BEAT_SCHEDULE` — beat schedule dict; change fire time here

### `callback/storage.py`
- `upload_resume(file, user_id: int) -> str` — returns S3 key
- `delete_resume(s3_key: str) -> None`
- Dev (`DEBUG=True`): writes to `/tmp/`, returns a real key — callers behave identically in dev and prod
- Prod: real S3 calls — scaffold in place, activate by uncommenting boto3 block
- Daily loop tasks must filter `resume__status='ready'` — storage does not enforce this

### `callback/llm/`
Import via `from pipeline.llm import score_job, personalize_cover_letter`.
Never import `anthropic` directly outside this package.

- `score_job(job: dict, profile: dict) -> dict`
  - `job` keys: `job_id`, `title`, `company`, `description`
  - `profile` keys: `target_roles`, `seniority_levels`, `years_experience`, `location_types`, `experience_summary`
  - Returns `{ "score": int (1–10), "reason": str }`
  - Raises `ValueError` if LLM response is not valid JSON
  - Re-raises `anthropic.*` exceptions on API error

- `personalize_cover_letter(template: str, job: dict) -> str`
  - `job` keys: `company`, `title`, `description`
  - Returns full personalised cover letter text
  - Re-raises `anthropic.*` exceptions on API error

### `callback/jsearch/client.py`
Import via `from pipeline.jsearch.client import fetch_jobs`.

- `fetch_jobs(role_titles, cities, location_types, strategy='combined') -> list[dict]`
  - Returns normalised job dicts, de-duplicated by `job_id` across all queries
  - Never raises on API error — logs and returns empty list; caller decides what to do
  - Normalised job dict keys: `job_id`, `title`, `company`, `description`, `job_url`,
    `location`, `remote_type`, `salary_range`, `apply_link`

  Query strategies (pass via `strategy` argument):
  - `'combined'` *(default)* — single API call; joins role titles and cities with OR
  - Add new strategies in `_STRATEGIES` dict; see module docstring for instructions

### `callback/tasks/scan_jobs.py`
- `scan_jobs(job_search_id: int, strategy: str = 'combined') -> list[dict]`
  - Fetches jobs, deduplicates against `JobSeen`, bulk-inserts new seen records
  - Returns unseen normalised job dicts ready for scoring
  - Returns `[]` if search is inactive, has no role titles, or API returns nothing
  - Idempotent — safe to re-run after partial failure

### `callback/tasks/score_jobs.py`
- `score_jobs(job_search_id: int, unseen_jobs: list[dict]) -> list[dict]`
  - Scores each job via LLM, filters below `LLM_SCORE_THRESHOLD`, sorts descending, caps at `daily_limit`
  - Scoring failures per job are caught and logged — flagged with `_score_failed: True` on the dict
  - Candidates (passed threshold) come first in the return list; failures appended after
  - Caller checks `_score_failed` flag to count failures separately

### `callback/tasks/daily_run.py`
- `daily_run(job_search_id: int | None = None)` — Celery task (`@shared_task`)
  - If `job_search_id` is supplied, runs only that search (useful for manual triggers / debugging)
  - If `None`, runs all active `JobSearch` records (normal scheduled invocation)
  - Creates and updates a `DailyRunLog` per search
  - Per-search errors are isolated — one failure never aborts other searches
  - Apply stage is currently a stub; candidates are logged and counted but not submitted

### `callback/ats/greenhouse.py` + `lever.py`
*(Not yet implemented)*
- `submit(application) -> { success: bool, method: str }`
- ATS detection logic lives in `tasks/apply_job.py`, not in these clients

---

## Lambda — Browser Use

### Language
- Python 3.13
- One function: `callback-submit-application`
- One invocation = one job application (fan-out pattern)

### Patterns
- Always write result back to Postgres directly on completion
- Log all steps — browser navigation is hard to debug without logs
- Handle exceptions explicitly — write `status: failed` + `failure_reason` on any unhandled error, never let Lambda silently fail

---

## General

### Never do this
- No TypeScript — plain JS only in frontend
- No `console.log` left in committed code — use proper logging
- No hardcoded URLs, API keys, or credentials anywhere
- No `TODO` comments without a linked task
- No `any` type workarounds (even in JS, avoid duck-typed assumptions)

### Git
- Branch from `main` for all features: `feature/`, `fix/`, `chore/`
- Commit messages: imperative present tense (`Add job scoring task` not `Added` or `Adding`)
- Never commit `.env`, `node_modules/`, `__pycache__/`, or build artifacts