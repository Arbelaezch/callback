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
| Email | Resend |
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
SECRET_KEY=
DEBUG=
ALLOWED_HOSTS=
DATABASE_URL=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=
AWS_LAMBDA_FUNCTION_NAME=
AWS_REGION=

ANTHROPIC_API_KEY=
JSEARCH_API_KEY=
RESEND_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

SENTRY_DSN=

CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

---

## Project Structure

```
/frontend
  /app
    /dashboard       # history, pause/resume, preferences
    /onboarding      # profile setup, file upload

/backend
  /callback
    /api             # DRF endpoints
    /models          # User, Preferences, Resume, Application, JobSeen
    /tasks
      scan_jobs.py   # JSearch fetch + dedup
      score_jobs.py  # LLM scoring
      apply_job.py   # ATS detection + Lambda dispatch
      send_digest.py # Resend daily email
    /llm             # Prompt templates + Anthropic client
    /ats             # Greenhouse + Lever API clients
    /jsearch         # JSearch client
    /storage         # S3 helpers

/lambda
  handler.py         # Browser Use submission
  requirements.txt
  deploy.sh          # zip + aws lambda update-function-code
```

---

## Daily Loop

```
Celery beat cron (daily, per active user)
  → JSearch: fetch jobs by role_titles + cities + remote_pref
  → Postgres: dedup against jobs_seen
  → LLM: score each new job (1-10) vs user profile
  → Select top N (default 5)
  → Per job:
      → Greenhouse URL → Greenhouse API
      → Lever URL     → Lever API
      → Other         → invoke Lambda (Browser Use)
      → LLM: personalize cover letter
      → Write to applications table
  → Resend: daily digest email
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

```sql
users                    -- Django auth
user_preferences         -- role_titles[], cities[], remote_pref, active, daily_limit
resumes                  -- s3_key, uploaded_at, user_id
cover_letter_templates   -- body, user_id
jobs_seen                -- job_id, user_id, seen_at
applications             -- job_id, user_id, company, role_title, status,
                         --   submission_method, applied_at, cover_letter_used,
                         --   lambda_invocation_id, failure_reason
```

`status`: `pending` `submitted` `failed` `skipped`
`submission_method`: `greenhouse_api` `lever_api` `browser_lambda`

---

## Monitoring

**Sentry** — add to `settings.py`:
```python
import sentry_sdk
sentry_sdk.init(dsn=env("SENTRY_DSN"), traces_sample_rate=0.2)
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

## Backups

```bash
# /etc/cron.d/callback-backup — runs 3am daily
0 3 * * * root pg_dump $DATABASE_URL | gzip | \
  aws s3 cp - s3://callback-backups/$(date +%Y-%m-%d).sql.gz
```

30-day retention. Cost: negligible.

---

## Submission Reliability

| Method | Condition | Reliability |
|---|---|---|
| Greenhouse API | URL contains `boards.greenhouse.io` | ~100% |
| Lever API | URL contains `jobs.lever.co` | ~100% |
| Browser Use (Lambda) | everything else | ~70-80% |

Failures logged + surfaced in digest. User handles manually.

---

## Roadmap

**MVP**
- [ ] Django + Next.js, Dockerized
- [ ] Nginx host config
- [ ] Models + migrations
- [ ] Auth (simplejwt)
- [ ] Onboarding + file upload → S3
- [ ] Celery beat cron
- [ ] JSearch client + fetch + dedup
- [ ] LLM scoring
- [ ] Greenhouse + Lever clients
- [ ] Lambda (Browser Use) + deploy script
- [ ] Cover letter personalization
- [ ] Fan-out Lambda dispatch
- [ ] Digest email (Resend)
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
| Resend | 3k emails/mo | $20/mo |
| Sentry | 5k errors/mo | Free at MVP |
| UptimeRobot | 50 monitors | Free |
| Stripe | No monthly fee | 2.9% + $0.30/txn |

**Estimated MVP cost: ~$0-30 CAD/mo**