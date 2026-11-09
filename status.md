# Project Status

Current scope: **V1**, paste a job description and get a tailored resume and cover letter. Version plan and design are in `AGENTS.md` ("Product direction", "Document generation").

The V1 work is merged into `main`; there is no open feature branch.

## Done

- Resume analysis: PDF in, structured content plus layout spec out.
- Supporting documents: upload `.md`/`.txt`, split by heading, Postgres full-text search, strictly user-scoped.
- Three-stage generation, one model per stage: context scout (Haiku, tool-using, step-capped), writer (Sonnet), verifier (Haiku) that flags unsupported claims. Cached voice profile.
- PDF export (WeasyPrint) and HTML preview from one renderer; layout values validated before reaching CSS; page-count warning.
- API under `/api/documents/`; frontend `/profile`, `/jobs`, `/jobs/new`, `/jobs/[id]` (field editor, cover letter editor, live preview, autosave, flagged-claims panel, PDF download, "Generate again").
- Auth hardening, upload and content validation, throttles, in-flight guards and daily caps on parse, generate and auth.
- Verified end to end against the real Anthropic API and in a headless browser, using a fictional resume.
- The cover letter sample can be uploaded as a file (#29).
- "Generate again" defaults to the primary resume (#28).
- Layout extraction hardened on real resumes (#30).
- Explicit Celery result expiry (#38).

## Known gaps

1. **Real resumes still expose gaps.** Extraction was hardened on real resumes (#30), but parse slips remain ([#32](https://github.com/Arbelaezch/callback/issues/32)), icons and decorative header elements are lost ([#33](https://github.com/Arbelaezch/callback/issues/33)), and there are no layout regression fixtures without personal data ([#34](https://github.com/Arbelaezch/callback/issues/34)). The layout spec is single-column only (`columns` is read but ignored) ([#31](https://github.com/Arbelaezch/callback/issues/31)).
2. **Verifier is lenient on small embellishments** (an invented reason or adverb). Tune against real output ([#9](https://github.com/Arbelaezch/callback/issues/9)).
3. **No frontend tests** and no automated browser test.
4. **Not production-ready:** nothing deployed; Sentry installed but not initialised; no per-user storage quota; `NUM_PROXIES` and the proxy setup need finishing ([#23](https://github.com/Arbelaezch/callback/issues/23)). Other open issues: no CSRF protection on cookie-authenticated writes ([#14](https://github.com/Arbelaezch/callback/issues/14)), raw exception text shown to users ([#15](https://github.com/Arbelaezch/callback/issues/15)), the refresh fetch has no timeout and can hold the cross-tab lock ([#20](https://github.com/Arbelaezch/callback/issues/20)).
5. **V2/V3 groundwork bugs**, left as found (see `AGENTS.md`): `apply_job` import path, cover letter personalisation never called, Lambda marks an application `submitted` too early, `send_digest` not written, jobs list status ignores versions ([#16](https://github.com/Arbelaezch/callback/issues/16)), lint errors in `/dashboard` and `/onboarding`.
6. **Generation leaves no state when the task never starts** ([#12](https://github.com/Arbelaezch/callback/issues/12)).
7. **Local venv drift:** recreate `backend/env` from `requirements.txt`.
8. Docker image build with WeasyPrint's system packages has not been verified.

## Next

- Git repository source: clone or pull a public repo and index `.md` files into sections (`ContextSource.kind = 'git'` already exists).
- Obsidian source: Obsidian Publish is public-only, so an uploaded vault zip is the simpler stand-in.
- Tune the verifier and writer against real resumes ([#9](https://github.com/Arbelaezch/callback/issues/9)).
- Verify summary placement and the keep-sections prompt on more real resumes ([#35](https://github.com/Arbelaezch/callback/issues/35)).

## Before shipping

- Build and run the Docker images and confirm WeasyPrint works in the container.
- Deploy on the OptiPlex (Nginx, `.env`, `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`, migrate) and smoke test.
- Initialise Sentry, add uptime monitoring and a `pg_dump` to S3 backup job.
- Create the S3 bucket and IAM user.

## Later

- URL import of job descriptions, browser extension, `.docx` in-place filling, embeddings if full-text retrieval is too weak, two-column layouts ([#31](https://github.com/Arbelaezch/callback/issues/31)).
- **V2:** saved search requirements (the `Search` model), job discovery (rework the JSearch scan and scoring; decide Celery vs Lambda for the crawler), a match inbox where the user approves or dismisses each job, notifications, generation only for approved jobs.
- **V3:** automated applying for approved jobs (rework the Lambda browser agent), with a submission log the user can see.
- Stripe and free-tier limits, social auth, password reset, email verification.
