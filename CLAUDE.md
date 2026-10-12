# Callback

<!-- Written by /harness-init. Agents read this file before planning, coding or reviewing:
     keep it short, factual and current. -->

## What this is
AI-powered job application agent: Next.js frontend, Django backend, Celery pipeline, AWS Lambda browser automation.

## Repos
- `.` (app): Next.js (JavaScript) in frontend, Django (Python)

## Commands
- Backend tests: `cd backend && env/bin/python manage.py test --noinput`
- Backend dev: `docker compose up` (django, celery, celery-beat, redis, postgres); `python manage.py sync_schedules` syncs beat schedules.
- Frontend: `cd frontend && npm run dev` / `npm run lint` / `npm run build`
- Lambda deploy: `lambda/deploy.sh` (zip upload).

## Conventions and rules
Full details in `AGENTS.md` (read it first). Key points:
- Monorepo: `frontend/` (Next.js App Router, plain JS, Tailwind only), `backend/` (Django + DRF; apps `callback` config, `pipeline` logic/no models, `jobs`, `users`, `notifications`), `lambda/` (Browser Use).
- Pipeline: scan (JSearch + JobSeen dedup, user-scoped) -> LLM score -> apply (Greenhouse/Lever API or Lambda) -> RunLog. The LLM only scores and personalizes cover letters.
- Constants go in `callback/config.py`, env values in `settings.py`, secrets only in `.env`.
- Do not define `CELERY_BEAT_SCHEDULE`; scheduling is DB-backed via `Search.schedule_enabled` + `sync_schedules`.
- Auth: JWT in httpOnly cookies, never localStorage. Endpoints need `IsAuthenticated` unless explicitly `AllowAny`.
- Frontend: all API calls via `src/lib/apiClient.js`; user state via `useAuth()`; no TypeScript, no inline styles, no CSS modules.
- No `console.log`, hardcoded URLs/keys, or TODOs without a linked task.
- Resume uploads use the two-phase pending -> ready pattern; pipeline filters `resume__status='ready'`.
- Git: branch from `main` (`feature/`, `fix/`, `chore/`); imperative commit messages.

## Harness
- `/ship <issue or task>`, `/review-pr <PR>`, `/harness-report`. Config: `.claude/harness.toml`.
- Run files live in `.harness/` (kept out of git).
