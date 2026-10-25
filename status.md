# Project Status

Current scope: **V1**, paste a job description and get a tailored resume and cover letter. Version plan and design are in `AGENTS.md` ("Product direction", "Document generation").

## Done

- Resume analysis: PDF in, structured content plus layout spec out.
- Supporting documents: upload `.md`/`.txt`, split by heading, Postgres full-text search, strictly user-scoped.
- Three-stage generation, one model per stage: context scout (Haiku, tool-using, step-capped), writer (Sonnet), verifier (Haiku) that flags unsupported claims. Cached voice profile.
- PDF export (WeasyPrint) and HTML preview from one renderer; layout values validated before reaching CSS; page-count warning.
- API under `/api/documents/`; frontend `/profile`, `/jobs`, `/jobs/new`, `/jobs/[id]` (field editor, cover letter editor, live preview, autosave, flagged-claims panel, PDF download, "Generate again").
- Auth hardening, upload and content validation, throttles, in-flight guards and daily caps on parse, generate and auth.
- Verified end to end against the real Anthropic API and in a headless browser, using a fictional resume.

## Known gaps

1. **Only fictional data has been tested.** Real resumes (two columns, tables, icons, unusual fonts) will stress layout extraction. The layout spec is single-column only (`columns` is read but ignored).
2. **Verifier is lenient on small embellishments** (an invented reason or adverb). Tune against real output.
3. **No frontend tests** and no automated browser test.
4. **Not production-ready:** nothing deployed; Sentry installed but not initialised; no per-user storage quota; `NUM_PROXIES` and the proxy setup need finishing (issue #23).
5. **V2/V3 groundwork bugs**, left as found (see `AGENTS.md`): `apply_job` import path, cover letter personalisation never called, Lambda marks an application `submitted` too early, `send_digest` not written, lint errors in `/dashboard` and `/onboarding`.
6. **Local venv drift:** recreate `backend/env` from `requirements.txt`.
7. Docker image build with WeasyPrint's system packages has not been verified.

## Next

- Git repository source: clone or pull a public repo and index `.md` files into sections (`ContextSource.kind = 'git'` already exists).
- Obsidian source: Obsidian Publish is public-only, so an uploaded vault zip is the simpler stand-in.
- Tune the verifier and writer against real resumes.

## Before shipping

- Build and run the Docker images and confirm WeasyPrint works in the container.
- Deploy on the OptiPlex (Nginx, `.env`, `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`, migrate) and smoke test.
- Initialise Sentry, add uptime monitoring and a `pg_dump` to S3 backup job.
- Create the S3 bucket and IAM user.

## Later

- URL import of job descriptions, browser extension, `.docx` in-place filling, embeddings if full-text retrieval is too weak, two-column layouts.
- **V2:** saved search requirements (the `Search` model), job discovery (rework the JSearch scan and scoring; decide Celery vs Lambda for the crawler), a match inbox where the user approves or dismisses each job, notifications, generation only for approved jobs.
- **V3:** automated applying for approved jobs (rework the Lambda browser agent), with a submission log the user can see.
- Stripe and free-tier limits, social auth, password reset, email verification.
