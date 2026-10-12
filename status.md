# Project Status

Checked against the code, not just `tasklist.md`. `tasklist.md` is behind in places and still uses old names (`UserPreferences`, `JobSearch`, `CoverLetterTemplate`).

Verified by reading the code only. The app and tests were not run.

## Done and working in code

**Foundation and models**
- Docker Compose stack: db, redis, backend, celery, celery-beat, frontend, plus a prod override file.
- Migrations exist for `users` and `jobs`.
- Models: `CustomUser`, `Resume`, `Portfolio`, `CoverLetterSample`, `Agent`, `Search`, `JobSeen`, `Application`, `RunLog`.
- All models registered in admin.
- CORS configured.

**Auth**
- simplejwt with httpOnly cookies, refresh and logout.
- Register, login and `me` endpoints.
- Frontend: login and register pages, `AuthContext`, `proxy.js` route protection, silent token refresh in `apiClient.js`.

**Onboarding and uploads**
- Atomic `/api/onboarding/` endpoint and resume upload endpoint (`ResumeUploadView`).
- `storage.py` with upload, delete and presigned `get_resume_url`.
- Onboarding page.

**Pipeline**
- `jsearch/client.py`, `scan_jobs` (with `job_cooldown` dedup) and `score_jobs`.
- `llm/client.py` with `score_job` and `personalize_cover_letter`.
- `daily_run` orchestrates scan -> score -> apply and writes a `RunLog`.
- `apply_job.py` creates `Application` records, detects the ATS, and dispatches to Lambda in prod or runs in-process when `USE_LAMBDA=False`.
- `run_pipeline` management command for local testing.

**Lambda**
- `handler.py` runs the Browser Use agent, downloads the resume, and posts the result to `/api/pipeline/applications/<id>/callback/` with a shared-secret header.
- Ships as a Docker image to ECR, with a GitHub Actions deploy workflow (replaced the zip upload in the spec).

**Scheduling**
- DB-backed beat with `sync_schedules`, and a schedule toggle endpoint.

**Dashboard (more built than the tasklist says)**
- Agent on/off toggle.
- Search list with active toggle, schedule toggle, manual trigger and run logs.
- Create-search form.
- Resume list and upload.
- Applications are fetched.

**Misc**
- `/api/health/` endpoint.
- `sentry-sdk` in requirements.

## Bugs and mismatches found

1. **Local dispatch is probably broken.** `apply_job.py:148` does `from lambda_runner import run_handler`, but the module is at `pipeline/tasks/lambda_runner.py`. Should be `from .lambda_runner import run_handler`. The `ImportError` handler would then mislabel it as a missing browser-use install.
2. **Cover letter personalization is not wired in.** `personalize_cover_letter` exists but nothing calls it. `daily_run.py` has a TODO for it, and `apply_job` reads `job.get('cover_letter', '')`, which is always empty.
3. **Spec drift on submission.** No Greenhouse or Lever direct API clients. The `ats/__init__.py` docstring says they need the employer's API key, so everything goes through the browser agent. The spec and tasklist should say so.
4. **Lambda marks applications `submitted` too early in prod.** `_dispatch_lambda` sets `submitted` plus `applied_at` as soon as the async invoke returns 202. The callback overwrites it later, but failures show as "submitted" in the meantime. Use `pending` until the callback arrives.
5. **Sentry is not initialized.** Installed, but no `sentry_sdk.init` anywhere.
6. **Cosmetic:**
   - `llm/prompts.py` doesn't exist (prompts are in `client.py`).
   - `AGENTS.md` lists `RefreshView` twice and `SearchSerializer` in the wrong app.
   - Dashboard has `console.log`/`console.debug` calls that `AGENTS.md` forbids.
   - The uncommitted `apply_job.py` import fix is correct: `pipeline.storage.get_resume_url` exists.

## Left to do

**Core pipeline**
- [ ] Wire cover letter personalization into `daily_run` / `apply_job`.
- [ ] Fix the `lambda_runner` import.
- [ ] Decide on and set the intermediate application status.
- [ ] Write `send_digest` (not started; no `EMAIL_*` settings in `settings.py` either) and call it at the end of `daily_run`.
- [ ] Test the Lambda end to end against real ATS pages (unclear from the code whether this has been done).

**Dashboard**
- [ ] Application history table (data is fetched; check whether it renders).
- [ ] Edit search preferences (roles, cities, etc.). Only creating a search exists.
- [ ] Upload or edit a cover letter sample or portfolio after onboarding.

**Infra and ops**
- [ ] Create the S3 bucket and IAM user (code is ready, tasklist item unchecked).
- [ ] Initialize Sentry in Django and Celery.
- [ ] Set up UptimeRobot.
- [ ] Set up the `pg_dump` -> S3 cron job.
- [ ] Remove `UserPreferences` / `JobSearch` references from the tasklist.
- [ ] Add Lambda env config `ANTHROPIC_API_KEY` / `DJANGO_CALLBACK_URL` (noted in `workflow.md`).

**Deploy**
- [ ] Docker and Nginx on the OptiPlex.
- [ ] Clone the repo and add `.env`.
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
- [ ] Run migrations, then smoke test the full loop.
- [ ] Check `next.config.mjs` has `output: 'standalone'` (prod compose runs `node server.js`).

**Post-MVP**
- Stripe, free-tier gating, social auth, password reset, email verification (scaffolded only), and the `notifications` app (placeholder).
