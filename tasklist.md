# MVP Task List

**Foundation**
- [x] Init monorepo, Docker Compose stack running
- [x] Run initial migrations
- [x] Create Django superuser (`docker compose exec backend python manage.py createsuperuser`)
- [x] Confirm Django admin accessible at `localhost:8000/admin`
- [x] Add `corsheaders` middleware to `settings.py`
- [x] Configure `CORS_ALLOWED_ORIGINS` for `localhost:3000`

**Models**
- [x] Create `users` app in Django
- [x] `UserPreferences` model — `role_titles`, `cities`, `remote_pref`, `active`, `daily_limit`
- [x] `Resume` model — `s3_key`, `uploaded_at`, `user` FK
- [x] `CoverLetterTemplate` model — `body`, `user` FK
- [x] `JobSeen` model — `job_id`, `user` FK, `seen_at`
- [x] `Application` model — `job_id`, `company`, `role_title`, `status`, `submission_method`, `applied_at`, `cover_letter_used`, `lambda_invocation_id`, `failure_reason`, `user` FK
- [x] Run `makemigrations` + `migrate`
- [x] Register all models in Django admin

**Auth**
- [x] Install + configure `djangorestframework-simplejwt`
- [x] Add token obtain + refresh endpoints to `urls.py`
- [x] Build Next.js login page
- [x] Store JWT in httpOnly cookie on login
- [x] Auth middleware in Next.js — redirect unauthenticated users

**File Upload**
- [ ] Configure AWS S3 bucket + IAM user with minimal permissions
- [x] Write S3 helper (`storage.py`) — `upload_resume`, `delete_resume`
- [x] DRF endpoint — accept resume PDF upload → store in S3 → save key to `Resume` model
- [x] DRF endpoint — accept cover letter text → save to `CoverLetterTemplate`
- [x] Next.js onboarding UI — role titles, cities, remote pref, resume upload, cover letter input

**Job Discovery**
- [ ] Write JSearch client (`jsearch/client.py`) — `fetch_jobs(role_titles, cities, location_types)`
- [ ] Write dedup logic — check `JobSeen` before processing
- [ ] Write Celery task `scan_jobs` — fetch → dedup → store unseen jobs

**LLM Scoring**
- [ ] Write Anthropic client (`llm/client.py`) — `score_job`, `personalize_cover_letter`
- [ ] Write prompt templates (`llm/prompts.py`)
- [ ] Write Celery task `score_jobs` — score each unseen job, return top N

**Application Submission**
- [ ] Write Greenhouse client (`ats/greenhouse.py`) — `submit(application)`
- [ ] Write Lever client (`ats/lever.py`) — `submit(application)`
- [ ] Write ATS detection logic in `tasks/apply_job.py` — inspect apply URL, route accordingly
- [ ] Write cover letter personalization call (`llm/client.py` — `personalize_cover_letter`)
- [ ] Write Lambda invoke helper (`tasks/apply_job.py`) — build payload, call Lambda
- [ ] Write Lambda function (`lambda/handler.py`) — Browser Use submission logic
- [ ] Test Lambda locally with a zip deploy to AWS
- [ ] Write `apply_job` Celery task — orchestrate ATS check → submit → log result

**Daily Loop**
- [ ] Wire full Celery chain: `scan_jobs` → `score_jobs` → `apply_job` (fan-out) → `send_digest`
- [ ] Configure Celery beat schedule in `settings.py`
- [ ] Write `send_digest` task — query today's applications, send email via Django SMTP

**Dashboard**
- [ ] Next.js dashboard — application history table
- [ ] Pause / resume toggle (hits `JobSearch.active`)
- [ ] Update preferences form (role titles, cities, remote pref)
- [ ] Upload new resume / cover letter

**Monitoring + Ops**
- [ ] Add Sentry to Django (`settings.py`) and Celery
- [ ] Add health endpoint (`/api/health/`)
- [ ] Set up UptimeRobot monitors
- [ ] Set up `pg_dump` → S3 cron job

**Deploy**
- [ ] Install Docker on server
- [ ] Configure Nginx on server — route `callback.yourdomain.com` to ports 8002/3000
- [ ] Clone repo on server, add `.env`
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
- [ ] Run migrations on server
- [ ] Smoke test full loop end to end