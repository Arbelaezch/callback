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
      layout.js          # root layout
      page.js            # redirects to /dashboard
    /components
      /ui                # shared UI components
    /lib
      api.js             # fetch wrapper — all API calls go through here
      auth.js            # auth helpers (login, logout, register, getMe)
    /hooks
      onboarding         # useChoices hook
    middleware.js        # route protection — redirects unauthenticated users

/backend
  /callback
    /tasks
      scan_jobs.py       # JSearch fetch + dedup
      score_jobs.py      # LLM scoring
      apply_job.py       # ATS detection + Lambda dispatch
      send_digest.py     # daily digest email
    /llm                 # prompt templates + Anthropic client
    /ats                 # Greenhouse + Lever API clients
    /jsearch             # JSearch client
    /storage             # S3 helpers
    db_config.py         # database config logic (dev vs prod)
    health.py            # /api/health/ endpoint
    settings.py          # Django settings — reads from .env via python-dotenv
    urls.py              # root URL config
  /users
    admin.py
    authentication.py    # CookieJWTAuthentication backend
    models.py            # CustomUser, Resume, CoverLetterTemplate
    serializers.py       # RegisterSerializer, UserSerializer
    views.py             # RegisterView, LoginView, LogoutView, MeView
  /jobs
    admin.py
    models.py            # JobSearch, JobSeen, Application, DailyRunLog

/lambda
  handler.py             # Browser Use submission
  requirements.txt
  deploy.sh              # zip + aws lambda update-function-code
```

---

## Database

```
users (CustomUser)       -- extends AbstractUser, created_at/updated_at
resumes                  -- s3_key, filename, is_default, user_id
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

Scaffolded for future social auth at `/api/auth/social/` and password reset/email verification endpoints.

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
- [ ] Nginx host config
- [ ] Onboarding + file upload → S3
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

### Hooks
- Custom hooks live in `src/hooks/` organized by feature (e.g. `hooks/onboarding/useChoices.js`)
- Import via `@/hooks/feature/useHookName`

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
- Tailwind CSS only
- No CSS modules, no styled-components, no emotion
- No inline `style` props unless dynamically computed

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
- All API calls go through `src/lib/api.js` — never call fetch directly in components
- Django backend at `process.env.NEXT_PUBLIC_API_URL`
- JWT stored in httpOnly cookie — never localStorage
- Always pass `credentials: 'include'` — handled by `api.js`

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