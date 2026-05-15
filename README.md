# callback# Callback

AI-powered job application agent. Runs daily per user, fetches jobs, scores relevance via LLM, submits applications autonomously.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend / API routes | Next.js (App Router) |
| Hosting | Vercel (serverless) |
| Database + Storage | Supabase (Postgres + S3-compatible storage) |
| Auth | Supabase Auth |
| Background jobs | Inngest |
| Job discovery | JSearch API (RapidAPI) |
| LLM | Anthropic API (claude-sonnet-4-6) |
| Browser automation | Browserbase + Browser Use |
| Email | Resend |

---

## Env Vars

```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
ANTHROPIC_API_KEY=
JSEARCH_API_KEY=
BROWSERBASE_API_KEY=
BROWSERBASE_PROJECT_ID=
RESEND_API_KEY=
INNGEST_EVENT_KEY=
INNGEST_SIGNING_KEY=
```

---

## Project Structure

```
/app
  /api
    /inngest         # Inngest function handler
    /webhooks        # Resend webhooks (optional)
  /dashboard         # User-facing UI
  /onboarding        # Profile + upload flow
/inngest
  /functions
    scan-jobs.ts     # Main daily loop per user
    score-jobs.ts    # LLM relevance scoring
    apply-job.ts     # Submission orchestration
    send-digest.ts   # Email digest
/lib
  /llm               # Prompt templates + API wrappers
  /browser           # Browserbase + Browser Use helpers
  /jsearch           # JSearch API client
  /ats               # Greenhouse + Lever direct API clients
  /supabase          # DB client + typed queries
```

---

## Daily Job Loop

```
Inngest cron (per user, daily)
  → JSearch: fetch jobs matching user prefs
  → Supabase: dedup check (jobs_seen table)
  → LLM: score each new job (1–10) against user profile
  → Select top 1–5 by score
  → For each job:
      → Check if Greenhouse/Lever apply URL exists → use API
      → Else → Browserbase + Browser Use to fill + submit form
      → LLM: generate tailored cover letter from template
      → Write result to applications table (submitted | failed)
  → Resend: send digest email with day's activity
```

---

## Database Tables

```sql
users                   -- auth, managed by Supabase Auth
user_preferences        -- role_titles[], cities[], remote_pref, active bool
resumes                 -- storage_path, uploaded_at, user_id
cover_letter_templates  -- body text, user_id
jobs_seen               -- job_id, user_id, seen_at (dedup)
applications            -- job_id, user_id, company, role_title, status,
                        --   submission_method, applied_at, cover_letter_used
```

---

## LLM Calls

**Scoring** — one call per unseen job:
```
system: You are a job fit evaluator...
user:   Job: {title, description, requirements}
        Profile: {target_roles, skills, experience_summary}
        Return JSON: { score: 1-10, reason: string }
```

**Cover letter** — one call per application:
```
system: You are a cover letter writer. Modify only: company name, role title,
        and one sentence in the opening paragraph. Keep everything else verbatim.
user:   Template: {cover_letter_text}
        Job: {company, role_title, one_line_description}
```

---

## Submission Methods

| Method | When | Reliability |
|---|---|---|
| Greenhouse API | `job_apply_link` matches `boards.greenhouse.io` | ~100% |
| Lever API | `job_apply_link` matches `jobs.lever.co` | ~100% |
| Browserbase + Browser Use | Everything else | ~70–80% |

Failed submissions → logged as `status: failed` → surfaced in digest email.

---

## Cost (MVP scale)

| Service | Free tier | Paid |
|---|---|---|
| JSearch | ~200–500 req/mo | $10–50/mo |
| Anthropic API | — | <$0.01/application |
| Browserbase | 1 hr, 1 concurrent | $20/mo (Developer) |
| Inngest | 50k runs/mo | $75/mo (Pro) |
| Resend | 3k emails/mo | $20/mo (Pro) |
| Supabase | Generous | $25/mo (Pro) |
| Vercel | Generous | $20/mo (Pro) |

---

## Roadmap

- **MVP** — profile setup, upload, daily scan, LLM scoring, submission, digest, dedup
- **V2** — approve-before-apply (SMS/in-app), better failure visibility
- **V3** — modular resume: discrete blurbs → LLM assembly → PDF generation per application
- **V4** — multi-vertical config, interview prep loop, analytics dashboard