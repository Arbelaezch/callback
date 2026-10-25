# Callback

<!-- Written by /harness-init. Agents read this file before planning, coding or reviewing:
     keep it short, factual and current. -->

## What this is
Writes a tailored resume and cover letter for one job. The user supplies a resume (PDF), a cover letter sample, optional supporting documents and a pasted job description; AI agents write both documents in the user's voice; the user edits them in the app and downloads PDFs. Next.js frontend, Django + Celery backend, WeasyPrint for PDFs.

## Roadmap
Three versions, built in order. Work only on the current version unless asked.
1. **V1 (MVP, current):** paste a job description, generate a tailored resume and cover letter from the user's context documents, edit, download PDFs. No job discovery, no applying.
2. **V2:** scan for jobs matching the user's saved search requirements and push matches to the user. The user signs off on each job (approval gate) before the AI generates the resume and cover letter for it. Generation never runs on unapproved jobs (cost control).
3. **V3:** the AI applies on the user's behalf using a browser agent or whatever means is possible by then, for jobs the user has approved.

Code from an earlier scan-and-apply design is kept as **V2/V3 groundwork**: the `jobs` app, `pipeline/tasks`, `jsearch`, `ats`, `lambda/` (Browser Use), `/dashboard`, `/onboarding`. V1 does not use it; keep it, do not extend it unless the task is about V2 or V3. Details in `AGENTS.md`.

## Repos
- `.` (app): Next.js (JavaScript) in frontend, Django (Python)

## Commands
- Backend tests: `cd backend && env/bin/python manage.py test --noinput` (needs Postgres: `docker compose up -d db`). LLM calls are mocked, so also run the real path once after changing `pipeline/llm` (see `AGENTS.md`, Testing).
- Backend dev: `docker compose up` (backend, celery, celery-beat, redis, postgres, frontend). On macOS run a host Celery worker with `--pool=solo`.
- Migrations: `cd backend && env/bin/python manage.py makemigrations --check` before committing model changes. Migrations are tracked in git.
- Frontend: `cd frontend && npm run dev` / `npm run lint` / `npm run build`. Do not run `build` while `dev` is running in the same folder.
- Lambda (V3 groundwork): Docker image deployed to ECR by `.github/workflows/deploy-lambda.yml` on pushes to `main` that touch `lambda/**`.

## Conventions and rules
Full details in `AGENTS.md` (read it first). Key points:
- Monorepo: `frontend/` (Next.js App Router, plain JS, Tailwind only), `backend/` (Django + DRF; apps `callback` config, `documents` the product, `users`, `pipeline` LLM client/agents plus V2/V3 groundwork tasks, no models; `jobs` V2 groundwork, `notifications` placeholder), `lambda/` (V3 groundwork)..
- Generation: context scout (light model, searches only the sources the user added) -> writer (strong model, no tools) -> verifier (flags unsupported claims). Stages and models are set in `callback/config.py`. Resume content and layout are stored separately, so tailoring never changes the user's formatting.
- All LLM calls go through `pipeline/llm`; never import the Anthropic SDK elsewhere. Get JSON with `call_structured` (structured outputs). Never force `tool_choice`: current models reject it. `pipeline/llm` must not import Django models.
- Never put model output into CSS or HTML unvalidated: layout values go through `resolve_layout`, markdown is rendered with raw HTML off, and WeasyPrint is not allowed to fetch URLs.
- Do not define `CELERY_BEAT_SCHEDULE`; scheduling is DB-backed (used by the V2 groundwork).
- Constants go in `callback/config.py`, env values in `settings.py`, secrets only in `.env`. `.env` has `USE_S3=True`; override to `False` for local runs.
- Auth: JWT in httpOnly cookies, never localStorage. Endpoints need `IsAuthenticated` unless explicitly `AllowAny`, and every `documents` queryset is scoped to `request.user`.
- Frontend: all API calls via `src/lib/apiClient.js`; load data with `useApiResource`; user state via `useAuth()`; no TypeScript, no inline styles, no CSS modules. Set state only inside promise callbacks in effects (React compiler lint rule).
- No `console.log`, hardcoded URLs/keys, or TODOs without a linked task.
- Uploads use the two-phase pending -> ready pattern; anything selecting resumes filters `status='ready'`.
- Git: branch from `main` (`feature/`, `fix/`, `chore/`); imperative commit messages. `docs/` is gitignored and holds local test inputs (personal resumes); never commit it.

## Harness
- `/ship <issue or task>`, `/review-pr <PR>`, `/harness-report`. Config: `.claude/harness.toml`.
- Run files live in `.harness/` (kept out of git).
