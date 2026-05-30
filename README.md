# Callback

AI-powered job application agent. Runs daily per user — fetches jobs, scores relevance via LLM, submits applications autonomously via ATS APIs or browser automation.

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

## Env Vars

```bash
# Django
SECRET_KEY=
DEBUG=
ALLOWED_HOSTS=

# Database
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
DATABASE_URL=                        # prod only

# Redis / Celery
REDIS_PASSWORD=
CELERY_BROKER_URL=redis://:password@redis:6379/0
CELERY_RESULT_BACKEND=redis://:password@redis:6379/0

# AWS
USE_S3=True
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=
AWS_LAMBDA_FUNCTION_NAME=
AWS_REGION=

# APIs
ANTHROPIC_API_KEY=
JSEARCH_API_KEY=

# Email
EMAIL_HOST=
EMAIL_PORT=
EMAIL_USE_TLS=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Monitoring
SENTRY_DSN=

# Stripe (post-MVP)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Next.js
NEXT_PUBLIC_API_URL=http://localhost:3000   # browser-facing — always points to Next.js
INTERNAL_API_URL=http://backend:8000        # server-side only — Next.js → Django inside Docker
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
      AuthContext.js     # AuthProvider + useAuth hook
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
    celery.py            # Celery app setup — autodiscovers tasks from pipeline
    db_config.py         # database config logic (dev vs prod)
    health.py            # /api/health/ endpoint
    settings.py          # Django settings — env vars + imports from config.py
    urls.py              # root URL config
    wsgi.py

  /pipeline              # Django app — all job pipeline business logic, no models
    /tasks
      __init__.py        # imports daily_run for Celery registration
      daily_run.py       # orchestrator Celery task
      scan_jobs.py       # JSearch fetch + dedup (user-scoped JobSeen)
      score_jobs.py      # LLM scoring + ranking
      apply_job.py       # ATS detection + Lambda dispatch (not yet implemented)
      send_digest.py     # daily digest email (not yet implemented)
    /llm
      __init__.py        # exports score_job, personalize_cover_letter
      client.py          # Anthropic SDK wrapper
    /jsearch
      client.py          # JSearch API wrapper — pluggable query strategies
    /ats
      greenhouse.py      # Greenhouse API client (not yet implemented)
      lever.py           # Lever API client (not yet implemented)
    storage.py           # S3 helpers — dev stub, prod S3

  /users                 # Django app — auth, user model, documents
    admin.py
    authentication.py    # CookieJWTAuthentication backend
    models.py            # CustomUser, Resume, Portfolio, CoverLetterSample
    serializers.py       # RegisterSerializer, UserSerializer, ResumeSerializer,
                         #   PortfolioSerializer, CoverLetterSampleSerializer,
                         #   SearchSerializer, OnboardingSerializer
    views.py             # RegisterView, LoginView, LogoutView, MeView,
                         #   OnboardingView, RefreshView

  /jobs                  # Django app — agent, searches, applications, run logs
    admin.py             # AgentAdmin, SearchAdmin, ApplicationAdmin,
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
        sync_schedules.py  # syncs Search.schedule_enabled → PeriodicTask

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
| `notifications` | Notification preferences and delivery. Placeholder — not yet implemented. |

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

`status` (resume): `pending` `ready` `failed`
`status` (application): `pending` `submitted` `failed` `deleted` `skipped`
`status` (run_log): `running` `completed` `partial` `failed`
`submission_method`: `greenhouse_api` `lever_api` `browser_lambda`

---

## Key Model Design Decisions

**`Agent`** — singleton per user. Master on/off switch (`Agent.active`). When inactive, no Searches run regardless of their own state. Holds the user's agent name.

**`Search`** — one job search configuration per agent. Multiple allowed (gated by plan). Owns `daily_target` (aspiration, enforced against plan ceiling in business logic) and `job_cooldown` (days before a seen job is eligible for re-processing — exposed to user, premium feature).

**`JobSeen`** — pipeline dedup scoped to **user**, not Search. Prevents re-processing the same job listing across multiple Searches. Separate concern from `Application`: JobSeen = "have we processed this?", Application = "have we applied?". Rows never deleted — re-eligibility filtered by `seen_at >= now - job_cooldown`.

**`Portfolio`** — free-text accomplishments/skills repository. LLM draws from this for scoring and cover letter generation. `body` field is MVP — future `PortfolioEntry` children will replace it for structured per-item input.

**`CoverLetterSample`** — user's cover letter in their own voice. LLM uses for tone matching. Not submitted directly. "Sample" naming intentional — signals it's source material.

---

## Daily Loop

```
Celery beat (per scheduled Search, 08:00 UTC)
  or manual via POST /api/jobs/searches/<id>/trigger/
  → Agent.active check (master kill switch)
  → Search.active check
  → JSearch fetch by role_titles + cities + location_types
  → Dedup against JobSeen (user-scoped, filtered by Search.job_cooldown)
  → LLM score each new job vs Search profile
  → Select top N (capped at Search.daily_target)
  → Per job:
      → Greenhouse URL → Greenhouse API
      → Lever URL     → Lever API
      → Other         → invoke Lambda (Browser Use)
      → LLM: personalize cover letter
      → Write Application record
  → Digest email
  → Update RunLog
```

---

## LLM Calls

**Scoring:**
```
system: You are a job fit evaluator. Return only JSON.
user:   Job: {title, company, description, requirements}
        Profile: {target_roles, seniority_levels, years_experience,
                  location_types, experience_summary}
        Return: { "score": 1-10, "reason": "string" }
```

**Cover letter:**
```
system: Modify only: company name, role title, and one opening sentence.
        Return only the full cover letter text.
user:   Template: {cover_letter_text}
        Job: {company, role_title, brief_description}
```

Cost: <$0.01 per application.

---

## Lambda

**Function:** `callback-submit-application`

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

One invocation per application (fan-out). Writes result back to `applications` table. 15 min timeout.

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

## Monitoring

**Sentry:**
```python
import sentry_sdk
sentry_sdk.init(dsn=os.environ['SENTRY_DSN'], traces_sample_rate=0.2)
```

**UptimeRobot** — monitor:
- `https://yourcallbackdomain.com/api/health/`
- `https://yourcallbackdomain.com`

---

## Submission Reliability

| Method | Condition | Reliability |
|---|---|---|
| Greenhouse API | URL contains `boards.greenhouse.io` | ~100% |
| Lever API | URL contains `jobs.lever.co` | ~100% |
| Browser Use (Lambda) | everything else | ~70–80% |

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
- [x] Models + migrations (Agent, Search, JobSeen, Application, RunLog, Resume, Portfolio, CoverLetterSample)
- [x] Auth (simplejwt + httpOnly cookies)
- [x] Onboarding + file upload (dev stub — S3 wiring pending)
- [x] JSearch client + fetch + dedup (user-scoped JobSeen + job_cooldown)
- [x] LLM scoring
- [x] Celery beat cron (DB-backed via django-celery-beat)
- [x] Dashboard pipeline controls (Agent toggle, Search toggle, Run Now, schedule toggle, run logs)
- [x] Wire up S3 for real file uploads
- [ ] Greenhouse + Lever clients
- [ ] Lambda (Browser Use) + deploy script
- [ ] Cover letter personalization
- [ ] Fan-out Lambda dispatch
- [ ] Digest email (Django SMTP)
- [ ] Nginx host config
- [ ] Sentry + UptimeRobot
- [ ] pg_dump → S3 cron
- [ ] Deploy

**V2** — approve-before-apply (SMS), expanded boards, retry logic, Stripe

**V3** — modular resume, LLM assembly, PDF generation per application, PortfolioEntry structured input

**V4** — multi-vertical, interview prep, analytics, staging environment

---

## Cost (MVP, minimal users)

| Service | Free tier | Paid |
|---|---|---|
| JSearch | ~200–500 req/mo | $10–50/mo |
| Anthropic | — | <$0.01/application |
| AWS Lambda | 1M invocations/mo | Negligible |
| AWS S3 | 5GB free | Pennies |
| Sentry | 5k errors/mo | Free at MVP |
| UptimeRobot | 50 monitors | Free |
| Stripe | No monthly fee | 2.9% + $0.30/txn |

**Estimated MVP cost: ~$0–30 CAD/mo**