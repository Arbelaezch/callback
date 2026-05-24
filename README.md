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
      /dashboard         # history, pause/resume, preferences
      /onboarding        # profile setup, file upload
      layout.js          # root layout
      page.js            # redirects to /dashboard
    /components
      /ui
        TagInput.js      # tag/chip input for arrays
    /hooks
      /onboarding
        useChoices.js    # fetches + caches job choice fields from API
    /lib
      apiClient.js       # fetch wrapper — all API calls go through here
      auth.js            # auth helpers (login, logout, register, getMe)
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
    db_config.py         # database config logic (dev vs prod)
    health.py            # /api/health/ endpoint
    settings.py          # Django settings — reads from .env via python-dotenv
    storage.py           # S3 helpers (upload, delete) — dev stub, prod S3
    urls.py              # root URL config
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

## Module Interfaces

### Frontend

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

### Backend

#### `callback/storage.py`
- `upload_resume(file, user_id: int) -> str` — returns S3 key
- `delete_resume(s3_key: str) -> None`
- In dev (`DEBUG=True`): writes to `/tmp/`, returns a real key — callers behave identically in dev and prod
- In prod: real S3 calls — scaffold in place, activate by uncommenting boto3 block
- Daily loop tasks must filter `resume__status='ready'` — storage does not enforce this

#### `callback/llm/` — Anthropic client
- `score_job(job, profile) -> { score: int, reason: str }`
- `personalize_cover_letter(template, job) -> str`
- Wraps Anthropic SDK — callers never import the SDK directly
- Returns parsed dicts/strings, not raw API responses

#### `callback/jsearch/client.py` — JSearch client
- `fetch_jobs(role_titles, cities, location_types) -> list[dict]`
- Wraps RapidAPI JSearch — callers never call RapidAPI directly

#### `callback/ats/greenhouse.py` + `lever.py` — ATS clients
- `submit(application) -> { success: bool, method: str }`
- ATS detection logic lives in `tasks/apply_job.py`, not in these clients

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

**Scoring:**
```
system: You are a job fit evaluator. Return only JSON.
user:   Job: {title, company, description, requirements}
        Profile: {target_roles, skills, experience_summary, remote_pref}
        Return: { "score": 1-10, "reason": "string" }
```

**Cover letter:**
```
system: Modify only: company name, role title, and one opening sentence.
        Return only the full cover letter text.
user:   Template: {cover_letter_text}
        Job: {company, role_title, brief_description}
```

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

One invocation per application (fan-out). Lambda writes result back to `applications` table directly. 15 min timeout — single application fits comfortably.

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

`status` (resume): `pending` `ready` `failed`
`status` (application): `pending` `submitted` `failed` `skipped`
`status` (daily_run_log): `running` `completed` `partial` `failed`
`submission_method`: `greenhouse_api` `lever_api` `browser_lambda`

---

## Monitoring

**Sentry** — add to `settings.py`:
```python
import sentry_sdk
sentry_sdk.init(dsn=os.environ['SENTRY_DSN'], traces_sample_rate=0.2)
```

**UptimeRobot** — monitor:
- `https://yourcallbackdomain.com/api/health/` (Django)
- `https://yourcallbackdomain.com` (Next.js)

**Health endpoint:**
```python
@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})
```

---

## Submission Reliability

| Method | Condition | Reliability |
|---|---|---|
| Greenhouse API | URL contains `boards.greenhouse.io` | ~100% |
| Lever API | URL contains `jobs.lever.co` | ~100% |
| Browser Use (Lambda) | everything else | ~70-80% |

Failures logged + surfaced in digest. User handles manually.

---

## Backups

```bash
# /etc/cron.d/callback-backup — runs 3am daily
0 3 * * * root pg_dump $DATABASE_URL | gzip | \
  aws s3 cp - s3://callback-backups/$(date +%Y-%m-%d).sql.gz
```

30-day retention. Cost: negligible.

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

## Cost (MVP, minimal users)

| Service | Free tier | Paid |
|---|---|---|
| JSearch | ~200-500 req/mo | $10-50/mo |
| Anthropic | — | <$0.01/application |
| AWS Lambda | 1M invocations/mo | Negligible |
| AWS S3 | 5GB free | Pennies |
| Sentry | 5k errors/mo | Free at MVP |
| UptimeRobot | 50 monitors | Free |
| Stripe | No monthly fee | 2.9% + $0.30/txn |

**Estimated MVP cost: ~$0-30 CAD/mo**