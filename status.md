# Project Status

Last updated 2026-10-12, on branch `feature/tailored-documents` (15 commits ahead of `main`, not merged or pushed).

## Direction

Callback pivoted from "auto-apply to jobs for you" to **"write a tailored resume and cover letter for one job"**: the user supplies a resume, a cover letter sample, optional supporting documents and a pasted job description; the AI writes both documents in the user's voice; the user edits them in the app and downloads PDFs. Browser automation is parked and comes back later as an apply step.

Design rationale and decisions are in `AGENTS.md` ("Document generation").

## How this was verified

- Backend: 63 tests pass (`cd backend && env/bin/python manage.py test --noinput`). The LLM is mocked in them.
- **Live API:** a throwaway resume PDF, notes file and job description were run through parse, scout, writer and verifier against the real Anthropic API, on SDK 1.13.0. Parse took about 12 s, generation about 32 s. Output was checked for invented facts.
- **Browser:** the whole flow (register, upload, analyze, notes, cover letter, new job, generate, edit with autosave, both PDF downloads, jobs list) was driven in headless Chromium against the real backend and a Celery worker, and the screenshots were reviewed.
- Not verified: Docker image build with the new system packages (WeasyPrint needs Pango and fonts), production deploy, anything with a real user's resume (only a fictional one was used), the git and Obsidian sources (not built).

## Done

**Document generation (new)**
- `documents` app: `ParsedResume`, `ContextSource`, `SourceDocumentSection`, `VoiceProfile`, `JobPosting`, `GeneratedDocument`, with admin and tracked migrations.
- Resume analysis: PDF in, structured content plus layout spec out.
- Supporting documents: upload `.md`/`.txt`, split by heading, Postgres full-text search, strictly user-scoped.
- Three-stage generation with a separate model per stage: context scout (Haiku, tool-using, step-capped), writer (Sonnet), verifier (Haiku) that flags claims the sources do not support. Cached voice profile.
- Structured output through `call_structured` (`output_config` JSON schema; no forced tool choice).
- PDF export (WeasyPrint) and HTML preview from the same renderer; layout values validated before reaching CSS; markdown escaped; no external fetches; page-count warning.
- API under `/api/documents/` (see `AGENTS.md`), including cover letter sample and parsed-resume list endpoints.
- Frontend: `/profile`, `/jobs`, `/jobs/new`, `/jobs/[id]` with field editor, cover letter editor, live preview, autosave, flagged-claims panel, PDF download, "Generate again" (new version).

**Platform (kept from before)**
- Docker Compose stack, JWT httpOnly cookie auth, S3 storage helper, Celery.
- `anthropic` SDK upgraded to 1.13.0.
- Housekeeping done on this branch: `output: 'standalone'` and the invalid `experimental.turbo` key fixed in `next.config.mjs`; migrations now tracked in git (the blanket `migrations/` ignore was removed); `docs/` ignored; console calls removed from `proxy.js` and `Navbar.js`; register now refreshes the session.

## Known gaps and bugs

1. **Failed or killed background tasks leave the UI spinning.** A failed parse shows "Analyzing…" forever with no retry; a worker that dies mid-generation leaves documents `pending` forever. Issue text is drafted but not filed (the harness blocks `gh issue create`); see "Needs your action".
2. **Only fictional data has been tested.** Real resumes (two columns, tables, icons, unusual fonts) will stress the layout extraction. The layout spec is single-column only (`columns` is read but ignored).
3. **Verifier is lenient on small embellishments** (for example an invented reason or adverb). It caught nothing on the last live run where a human reader would flag a couple of soft phrases. Worth tuning against real output.
4. **No tests for the frontend**, and no automated browser test (the Playwright script used for verification lives only in a scratchpad).
5. **Not production-ready:** nothing has been deployed; Sentry is installed but not initialised; no rate limiting or cost cap on generation endpoints (each generation spends real money); upload sizes are limited but there is no per-user quota.
6. **Existing lint errors** remain in `/dashboard` (setState in effect) and `/onboarding` (unescaped `'`). Both pages are parked.
7. **Parked pipeline bugs**, left as found: `apply_job` local import path wrong, cover letter personalisation never called, Lambda marks an application `submitted` before the callback, `send_digest` not written.
8. **CLAUDE.md** still describes the old pipeline as the product ("Pipeline: scan -> LLM score -> apply").
9. **Local venv drift:** `backend/env` had packages out of sync with `requirements.txt` (an old `anthropic`, missing Django and third-party migration files), and now contains Lambda packages (`browser-use`, `langchain-anthropic`) that pin `anthropic<1`. The backend image is unaffected. Recreate the venv from `requirements.txt` when convenient; running the parked in-process browser agent from it will not work on SDK 1.x.

## Left to do

**Next (milestone 3)**
- Git repository source: clone or pull a public repo (access token for private ones needs an encryption dependency), index `.md` files into sections. The model already has `ContextSource.kind = 'git'`.
- Obsidian: Obsidian Publish is public-only, so likely a later add-on; an uploaded vault zip is a simpler stand-in.
- Failure handling for parse and generation (item 1 above).
- Tune the verifier and writer against real resumes.

**Before shipping**
- Build and run the Docker images (`docker compose up --build`) and confirm WeasyPrint works in the container.
- Deploy on the OptiPlex (Nginx, `.env`, `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`, migrate) and smoke test the loop.
- Initialise Sentry, add uptime monitoring and the `pg_dump` to S3 backup job.
- Create the S3 bucket and IAM user (the code is ready; the bucket was never created).
- Cost and abuse controls on `/generate/` and `/parse/`.
- Update `CLAUDE.md`; remove or hide the parked `/dashboard` and `/onboarding` pages.

**Later**
- URL import of job descriptions (best effort with a paste fallback), browser extension, `.docx` in-place filling for Word resumes, embeddings if full-text retrieval proves too weak, two-column layouts.
- Bring back automated applying through the Lambda browser agent.
- Stripe and free-tier limits, social auth, password reset, email verification, notifications.

## Needs your action

- **File the failure-handling issue.** The text is in `docs/issue-parse-failure.md` (gitignored). Create it with `gh issue create`, label `bug`, title "Resume parsing and document generation hang forever when the Celery task fails", and `--body-file docs/issue-parse-failure.md`.
- **Dev resume file:** a cleanup step may have deleted the local dev copy of your own resume at `/tmp/resumes/user_1/...`; restore it from `docs/` if parsing that resume fails locally.
- Decide whether to push the branch and open a PR to `main`.
