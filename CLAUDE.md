# Callback

<!-- Written by /harness-init. Agents read this file before planning, coding or reviewing:
     keep it short, factual and current. -->

## What this is
Writes a tailored resume and cover letter for one job. The user supplies a resume (PDF), a cover letter sample, optional supporting documents and a pasted job description; AI agents write both documents in the user's voice; the user edits them in the app and downloads PDFs. Next.js frontend, Django + Celery backend, WeasyPrint for PDFs.

The older auto-apply pipeline (JSearch scan, scoring, Lambda browser agent, `/dashboard`, `/onboarding`) is **parked**: the code stays, nothing in the new flow uses it, do not extend it unless asked.

## Repos
- `.` (app): Next.js (JavaScript) in frontend, Django (Python)

## Commands
- Backend tests: `cd backend && env/bin/python manage.py test --noinput` (needs Postgres: `docker compose up -d db`). LLM calls are mocked, so also run the real path once after changing `pipeline/llm` (see `AGENTS.md`, Testing).
- Backend dev: `docker compose up` (backend, celery, celery-beat, redis, postgres, frontend). On macOS run a host Celery worker with `--pool=solo`.
- Migrations: `cd backend && env/bin/python manage.py makemigrations --check` before committing model changes. Migrations are tracked in git.
- Frontend: `cd frontend && npm run dev` / `npm run lint` / `npm run build`. Do not run `build` while `dev` is running in the same folder.
- Lambda (parked): Docker image deployed to ECR by `.github/workflows/deploy-lambda.yml` on pushes to `main` that touch `lambda/**`.

## Conventions and rules
Full details in `AGENTS.md` (read it first). Key points:
- Monorepo: `frontend/` (Next.js App Router, plain JS, Tailwind only), `backend/` (Django + DRF; apps `callback` config, `documents` the product, `users`, `pipeline` LLM client/agents + parked tasks, no models; `jobs` parked, `notifications` placeholder), `lambda/` (parked).
- Generation: context scout (light model, searches only the sources the user added) -> writer (strong model, no tools) -> verifier (flags unsupported claims). Stages and models are set in `callback/config.py`. Resume content and layout are stored separately, so tailoring never changes the user's formatting.
- All LLM calls go through `pipeline/llm`; never import the Anthropic SDK elsewhere. Get JSON with `call_structured` (structured outputs). Never force `tool_choice`: current models reject it. `pipeline/llm` must not import Django models.
- Never put model output into CSS or HTML unvalidated: layout values go through `resolve_layout`, markdown is rendered with raw HTML off, and WeasyPrint is not allowed to fetch URLs.
- Constants go in `callback/config.py`, env values in `settings.py`, secrets only in `.env`. `.env` has `USE_S3=True`; override to `False` for local runs.
- Do not define `CELERY_BEAT_SCHEDULE`; scheduling is DB-backed (only the parked pipeline uses it).
- Auth: JWT in httpOnly cookies, never localStorage. Endpoints need `IsAuthenticated` unless explicitly `AllowAny`, and every `documents` queryset is scoped to `request.user`.
- Frontend: all API calls via `src/lib/apiClient.js`; load data with `useApiResource`; user state via `useAuth()`; no TypeScript, no inline styles, no CSS modules. Set state only inside promise callbacks in effects (React compiler lint rule).
- No `console.log`, hardcoded URLs/keys, or TODOs without a linked task.
- Uploads use the two-phase pending -> ready pattern; anything selecting resumes filters `status='ready'`.
- Git: branch from `main` (`feature/`, `fix/`, `chore/`); imperative commit messages. `docs/` is gitignored and holds local test inputs (personal resumes); never commit it.

## Harness
- `/ship <issue or task>`, `/review-pr <PR>`, `/harness-report`. Config: `.claude/harness.toml`.
- Run files live in `.harness/` (kept out of git).
