# AGENTS.md
# Instructions for AI coding agents working on this codebase.
# Read this before generating any code.

## Project
Callback: given a user's resume, a cover letter sample, optional supporting documents (projects, notes) and a pasted job description, the AI writes a resume and cover letter tailored to that job, in the user's own voice. The user edits both in the app and exports PDFs.

Monorepo: Next.js frontend + Django backend (Celery workers) + an AWS Lambda browser-automation function.

**Product direction.** The original product (daily scan, score, auto-apply via browser agent) is **parked, not deleted**. Its code still exists (`pipeline/tasks/*`, `jobs` app, `lambda/`, `/dashboard`, `/onboarding`) but nothing in the new flow uses it. Do not extend it unless asked. The Lambda browser agent returns later as an "apply for me" step once document generation is solid.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, plain JS, Tailwind 4 |
| Backend | Django 6 + DRF |
| Auth | Django auth + simplejwt (httpOnly cookies) |
| Database | Postgres 17 (Docker) |
| Job queue | Celery + Redis (Docker) |
| LLM | Anthropic API, `anthropic` Python SDK 1.x. Models per stage in `callback/config.py` |
| PDF export | WeasyPrint 70 (needs Pango and fonts: installed in `backend/Dockerfile`) |
| Retrieval | Postgres full-text search (no embeddings) |
| File storage | AWS S3 (dev stub: `/tmp`) |
| Browser automation (parked) | AWS Lambda + Browser Use, Docker image in ECR |
| Job discovery (parked) | JSearch API (RapidAPI) |
| Email | Django SMTP (not implemented) |
| Error tracking | Sentry (installed, not initialised) |
| Reverse proxy | Nginx (host) |
| DNS + SSL | Cloudflare |
| Payments | Stripe (post-MVP) |

---

## Infrastructure

Self-hosted on a Dell OptiPlex 7040. Browser Use jobs are isolated to AWS Lambda and never touch the home server.

```
Host (OptiPlex)
├── Nginx (reverse proxy, host-level)
├── callback/docker-compose.yml
│   ├── backend (gunicorn in prod, runserver in dev)
│   ├── celery worker
│   ├── celery-beat (django-celery-beat DB scheduler; only used by the parked pipeline)
│   ├── frontend (next dev; prod runs `node server.js` from the standalone build)
│   ├── redis
│   └── postgres
└── portfolio/docker-compose.yml (separate project)

AWS
├── S3: resumes/, context/ (supporting documents)
└── Lambda: callback-submit-application (parked)
```

---

## Project Structure

```
/frontend
  next.config.mjs        # standalone output, /api/* rewrites to Django
  /src
    proxy.js             # route protection (Next 16 replacement for middleware)
    /app
      /(auth)/login, /register
      /profile           # resume upload + analysis, supporting documents, cover letter sample
      /jobs              # list of job postings
      /jobs/new          # paste a job description, start generation
      /jobs/[id]         # tabs: Resume | Cover letter; editor + live preview + PDF download
      /dashboard         # PARKED: old pipeline controls (has lint errors and console calls)
      /onboarding        # PARKED: old onboarding (requires job-search preferences)
      layout.js, globals.css, page.js (redirects to /jobs)
    /components
      /layout/Navbar.js
      /ui/TagInput.js, Field.js, styles.js     # styles.js: shared Tailwind class strings
      /documents/DocumentWorkspace.js          # draft state, autosave, preview refresh, PDF export
      /documents/ResumeEditor.js               # field-by-field editor for resume content JSON
      /documents/DocumentPreview.js            # sandboxed iframe showing server-rendered HTML
    /contexts/AuthContext.js
    /hooks
      useApiResource.js                        # load + reload a JSON resource via apiClient
      /onboarding/useChoices.js
    /lib
      apiClient.js       # all API calls go through here
      auth.js
      resumeContent.js   # cleanResume(), moveItem(), patchItem()

/backend
  /callback              # project config only: settings, urls, celery, config.py, health
  /users                 # CustomUser, Resume, Portfolio, CoverLetterSample, auth + onboarding views
  /documents             # NEW: the product (see "Document generation")
    models.py, serializers.py, views.py, urls.py, admin.py
    services.py          # parse_resume(), index_upload_source()
    generation.py        # generate_documents(): scout -> writer -> verifier
    search.py            # index_sections(), search_sections() (Postgres FTS)
    sectioning.py        # split_sections(): markdown/plain text -> heading-level sections
    rendering.py         # resume/cover letter HTML + PDF (WeasyPrint), layout sanitising
    tasks.py             # parse_resume_task, generate_documents_task
    templates/documents/ # resume.html, cover_letter.html, styles.css
    tests/
  /pipeline              # no models
    /llm                 # client.py (call_structured), resume_analysis.py, scout.py, writer.py,
                         #   prompts.py, schemas.py, __init__.py
    storage.py           # S3 helpers (dev stub in /tmp)
    /tasks               # PARKED: daily_run, scan_jobs, score_jobs, apply_job, lambda_runner
    /jsearch, /ats       # PARKED (ats has only detect_ats; no Greenhouse/Lever clients)
  /jobs                  # PARKED: Agent, Search, JobSeen, Application, RunLog
  /notifications         # placeholder

/lambda                  # PARKED: Browser Use handler, Dockerfile, deploy via GitHub Actions
/.github/workflows/deploy-lambda.yml
```

---

## Django Apps

| App | Purpose |
|---|---|
| `callback` | Project config only. No models, no views. |
| `documents` | The product: parsed resumes, context sources, generation, rendering. Models + serializers + views. |
| `users` | Auth, custom user, Resume (uploaded file), Portfolio, CoverLetterSample. |
| `pipeline` | LLM client and agents (`pipeline/llm`), S3 storage. Also the parked scan/score/apply tasks. No models. |
| `jobs` | PARKED: Agent, Search, JobSeen, Application, RunLog. |
| `notifications` | Placeholder. |

Dependency direction: `documents` imports `pipeline.llm` and `pipeline.storage`; `pipeline.llm` must **not** import Django models. The scout agent receives tool handlers from its caller for this reason.

---

## Database

```
users (CustomUser)
resumes                  -- user, label, s3_key, filename, is_default, status (pending|ready|failed|deleted)
cover_letter_samples     -- user, label, body, is_default
portfolios               -- user, label, body, is_default           (legacy; not used by generation)

documents_parsedresume          -- user, resume (OneToOne), content JSON, layout JSON
documents_contextsource         -- user, kind (git|obsidian|upload), label, url, s3_key,
                                --   status (pending|ready|failed), error, last_synced_at
documents_sourcedocumentsection -- source, path, heading, text, search_vector (GIN index)
documents_voiceprofile          -- user (OneToOne), notes, excerpts JSON, built_from_hash
documents_jobposting            -- user, title, company, description
documents_generateddocument     -- job_posting, kind (resume|cover_letter), status (pending|ready|failed),
                                --   content JSON, layout JSON, markdown, unsupported_claims JSON,
                                --   version, edited, pdf_s3_key (unused), error

agents, searches, jobs_seen, applications, run_logs   -- PARKED (jobs app)
```

**Key design decisions**

- **Content and layout are separate.** `ParsedResume.content` holds facts; `.layout` holds the user's formatting (fonts, margins, spacing, section order, bullet style). Tailoring changes `content` only, so the user's design survives every generated version.
- **Layout is snapshotted** onto each `GeneratedDocument` so re-parsing a resume never changes an old export. A cover letter keeps its letterhead in `content['header']`.
- **Versions.** Each generation creates a new resume + cover letter pair with `version = previous + 1`. Old versions and the user's edits are kept. The UI shows the newest of each kind.
- **Only added sources are searched.** The scout gets search tools only for `ContextSource` rows with `status='ready'` that belong to the user. No sources means no scout call.
- **`SourceDocumentSection`** is one heading-level slice of a source document: the unit the scout searches, reads and cites.
- **`VoiceProfile`** depends only on the cover letter sample and the user's sources, so it is cached per user and rebuilt only when `built_from_hash` changes.
- **Migrations are tracked in git** for every app. (An old blanket `migrations/` ignore rule was removed.) Run `makemigrations --check` before committing model changes.

---

## Document generation

Two Celery tasks in `documents/tasks.py`; the API queues them and the frontend polls.

**1. Resume analysis** (`parse_resume_task` -> `services.parse_resume`)
Sends the stored PDF to Claude (native PDF input) and stores `{content, layout}` in `ParsedResume`. Uses the writer-tier model because measuring layout is a vision task.

**2. Source indexing** (`services.index_upload_source`, synchronous on upload)
Reads an uploaded `.md`/`.txt` (max 1 MB), splits it by heading into `SourceDocumentSection` rows, fills `search_vector`, and marks the source ready. Git and Obsidian sources are not implemented yet (the API returns 400).

**3. Generation** (`generate_documents_task` -> `generation.generate_documents`), three stages, each with its own model in `callback/config.py`:

| Stage | Model constant | Job |
|---|---|---|
| Context scout | `LLM_MODEL_SCOUT` (Haiku) | Tool-using agent (max `SCOUT_MAX_STEPS` rounds, then forced to submit). Tools: `search_sections`, `read_section`. Returns a **context brief** of verbatim, source-cited facts relevant to the job. |
| Writer | `LLM_MODEL_WRITER` (Sonnet) | Sees only the job, resume content JSON, brief and voice profile. No searching. Returns tailored resume content JSON and cover letter markdown. Must not invent employers, titles, dates, metrics or accomplishments, and must not copy sentences from sources. |
| Verifier | `LLM_MODEL_VERIFIER` (Haiku) | Checks every claim against the original resume, brief and job posting. Unsupported claims are stored in `unsupported_claims` and shown to the user. |

The voice profile is built by `build_voice_profile` from the cover letter sample plus the longest source sections.

If a stage raises, both documents are marked `failed` with the error and the exception is re-raised. If the worker process itself dies the rows stay `pending` until `fail_stale_documents` marks them failed.

**Rendering** (`documents/rendering.py`). HTML is rendered with Django templates and converted to PDF with WeasyPrint. The preview endpoint serves the same HTML.
- The layout comes from the model, so every value is validated before it reaches CSS (`resolve_layout`): numbers clamped, enums checked, colours matched against `#rrggbb`, fonts mapped to a fixed stack (Liberation fonts in Docker). Never emit raw model text into CSS.
- Cover letter markdown is rendered with raw HTML disabled and hard line breaks on.
- WeasyPrint uses a `URLFetcher` that allows no protocol, so crafted `<img src>` cannot read local files or call the network.
- Empty values mean "absent": sections with no content are skipped, and every known section is kept even if the layout's `section_order` omits it.
- `html_to_pdf` returns the page count; the export endpoint sends it in `X-Page-Count` so the UI can warn when a resume runs past one page.

---

## LLM Calls

All calls go through `pipeline/llm`. Callers never import the Anthropic SDK directly. Models, token limits and timeouts live in `callback/config.py`.

- **`call_structured(model, system, content, schema, max_tokens, timeout)`** is the way to get JSON. It uses `output_config={'format': {'type': 'json_schema', ...}}`. Do **not** use forced `tool_choice`: newer models (Sonnet 5.5, Opus 5.5, Fable 5.1) reject it with a 400.
- `_strict_schema` closes every object (`additionalProperties: false`) and marks **all properties required**, because the API caps optional fields per schema (24). Absent values are therefore sent as empty strings or arrays. Schemas in `schemas.py` are written normally; do not add `required`/`additionalProperties` by hand.
- Truncated output (`stop_reason == 'max_tokens'`) and refusals raise `ValueError`.
- `run_scout` (`scout.py`) is the only agent loop. It uses `tool_choice: auto` and forces `submit_brief` only on its last step (Haiku supports that).
- `analyze_resume`, `build_voice_profile`, `write_documents`, `verify_documents` are the other public functions. Prompts are in `prompts.py`.
- `score_job` and `personalize_cover_letter` belong to the parked pipeline.

When adding or changing a prompt, run the live smoke path at least once (see "Testing"): mocked tests cannot catch prompt or schema problems.

---

## Auth

JWT via `djangorestframework-simplejwt`. Tokens in httpOnly cookies, never localStorage.

- `access_token` cookie: 15 min. `refresh_token` cookie: 7 days, blacklisted on logout (not rotated on refresh yet). A failed refresh and logout both clear the auth cookies.
- `CookieJWTAuthentication` in `users/authentication.py` reads the cookie, falls back to the Authorization header.
- All endpoints require `IsAuthenticated` unless explicitly `AllowAny`. Every `documents` view scopes its querysets to `request.user`.
- `secure=not DEBUG` on cookies.
- Token refresh is handled silently in `apiClient.js` (on 401, `POST /api/auth/token/refresh/`, retry once).
- `AuthContext.js` is the single source of truth for user state. Call `refresh()` after login or register so the navbar updates.

---

## File Upload

**Resumes** use a two-phase pattern: create the `Resume` as `pending` inside `transaction.atomic()`, upload outside the transaction, then set `ready` (or `failed`). Anything selecting resumes must filter `status='ready'`.

**Supporting documents** (`ContextSource` kind `upload`) follow the same idea: create `pending`, store the file, index it, then mark `ready`, or `failed` with the error.

`pipeline/storage.py`: `upload_resume`, `upload_context_document`, `read_file`, `delete_resume` (also used to delete context files), `get_resume_url`. With `USE_S3=False` files go to `/tmp/<key>`.

---

## API Endpoints

### Auth: `/api/auth/`
| Method | Path | Description |
|---|---|---|
| POST | `/register/`, `/login/`, `/logout/`, `/token/refresh/` | Auth. Login (10/min per IP) and register (5/hour per IP) are throttled: 429 `{detail}` plus `Retry-After`. Refresh and logout are not |
| GET | `/me/` | Current user |

### Users: `/api/users/`
| Method | Path | Description |
|---|---|---|
| GET, POST | `/resumes/` | List resumes; upload a PDF (field `resume`, max 5 MB) |

### Documents: `/api/documents/` (all require auth, all scoped to the user)
| Method | Path | Description |
|---|---|---|
| POST | `/resumes/<id>/parse/` | Queue analysis of a ready resume (202). 409 if a parse of this resume was requested under 3 minutes ago and is still pending; 429 after 30 accepted analyses per user in a rolling 24 hours (`ParseRequest` rows). POST throttled at 10/hour per user (429 `{detail}` + `Retry-After`); GET is not |
| GET | `/resumes/<id>/parse/` | Parsed content and layout (404 if not parsed) |
| GET | `/resumes/parsed/` | Which resumes are parsed (no content) |
| GET, PUT | `/cover-letter-sample/` | The default cover letter sample (`{body}`) |
| GET, POST | `/sources/` | List sources; upload a `.md`/`.txt` (field `file`, optional `label`) |
| DELETE | `/sources/<id>/` | Remove a source and its file |
| GET, POST | `/jobs/` | List job postings (with documents); create one |
| GET | `/jobs/<id>/` | One posting with its documents |
| POST | `/jobs/<id>/generate/` | `{resume_id}`: create the pending rows, queue generation (202). Resume must be parsed; 503 if queueing fails (rows marked failed). 409 if this job has pending documents under 5 minutes old; 429 after 30 generations per user in a rolling 24 hours. Throttled at 10/hour per user (429 `{detail}` + `Retry-After`) |
| GET, PATCH | `/documents/<id>/` | Read a document (includes read-only `resume`); save the user's edits (sets `edited`). PATCH: 409 unless `ready`, 400 `{content: [...]}` on malformed content |
| GET | `/documents/<id>/preview/` | The document as HTML |
| GET | `/documents/<id>/export/` | PDF download; `X-Page-Count` header |

`preview` and `export` return 409 until the document is `ready`.

### Parked
`/api/jobs/*` (agent, searches, applications), `/api/onboarding/`, `/api/pipeline/applications/<id>/callback/` (Lambda callback, `X-Callback-Secret` header).

---

## Settings

Non-secret constants live in `callback/config.py` and are imported into `settings.py`.

- Value comes from the environment: `settings.py` via `os.environ`.
- Hardcoded constant: `config.py`.
- Secret: `.env` only, never committed.

Application code imports constants from `callback.config`, not `django.conf.settings`, unless Django itself requires the value there. Throttle rates, daily caps and in-flight windows are in `config.py`. `PARSE_INFLIGHT_MINUTES` and `GENERATION_INFLIGHT_MINUTES` must match `PARSE_POLL_TIMEOUT_MS` (profile page) and `GENERATION_POLL_TIMEOUT_MS` (job page) and stay below the `*_STALE_AFTER_MINUTES` values. `NUM_PROXIES` (env, default 0) is the number of reverse proxies in front of Django; with 0 the client IP is `REMOTE_ADDR` and `X-Forwarded-For` is ignored. The browser reaches Django only through the Next.js rewrite, so 0 means one site-wide login/register bucket; do not ship 0. Do not simply set it to the proxy count (1) either: Next keeps a client-supplied `X-Forwarded-For`, so an edge proxy must overwrite it and Django's port must not be public (tracked in issue #23). `CACHE_URL` (env, optional redis URL) shares throttle counters across workers; unset means per-process LocMem.

Do not define `CELERY_BEAT_SCHEDULE` (scheduling is DB-backed via `django-celery-beat`; only the parked pipeline uses it).

---

## Frontend: Next.js

- Next 16, App Router only. No Pages Router, no `getServerSideProps`/`getStaticProps`/`getInitialProps`.
- Server Components by default; `"use client"` only for state, effects, browser APIs or event listeners, kept at the leaves. Functional components only.
- Tailwind only, design tokens as CSS variables in `globals.css`. Dark theme. No CSS modules, styled-components, emotion or inline `style` props. Shared control classes are in `components/ui/styles.js`.
- All API calls go through `src/lib/apiClient.js`; never call `fetch` in components.
- Load data with `useApiResource(path)` (returns `{data, error, loading, reload}`). The React compiler lint rule `react-hooks/set-state-in-effect` rejects calling a state-setting function directly inside an effect, so set state only inside promise callbacks (that is what the hook does).
- Poll by calling `reload` on an interval while something is pending (see `/profile` and `/jobs/[id]`).
- The preview iframe uses `sandbox=""` and `srcDoc`; keep it script-free.
- `next.config.mjs` rewrites `/api/*` to Django (`INTERNAL_API_URL`) and adds the trailing slash Django expects.

### `src/lib/apiClient.js`
- `get`, `post`, `put`, `patch`, `delete`, `multipart(path, formData)`: JSON in, JSON out. `null` on 204.
- `getText(path)`: response body as text (HTML preview).
- `getBlob(path)`: returns `{ blob, pageCount }` (PDF download; page count from `X-Page-Count`).
- Throws `{ status, ...detail }` on non-2xx.

### `src/lib/auth.js`: `register`, `login`, `logout`, `getMe`
### `src/contexts/AuthContext.js`: `useAuth()` returns `{ user, loading, refresh, logout }`. Never call `getMe()` directly in components.

---

## Backend module interfaces

### `callback/config.py`
LLM models and limits (`LLM_MODEL_SCOUT/WRITER/VERIFIER`, `LLM_MAX_TOKENS_*`, `LLM_TIMEOUT_SECONDS(_LONG)`), `SCOUT_MAX_STEPS`, `SCOUT_TOOL_RESULT_MAX_CHARS`, `VOICE_SAMPLE_MAX_CHARS`, `CONTEXT_SECTION_MAX_CHARS`, `CONTEXT_UPLOAD_MAX_BYTES`, `CONTEXT_UPLOAD_EXTENSIONS`, plus parked JSearch and scoring constants.

### `documents/services.py`
- `parse_resume(resume) -> ParsedResume`: requires `resume.status == 'ready'`; re-running replaces the parse.
- `index_upload_source(source) -> int`: replaces sections, marks ready or failed, returns section count.

### `documents/search.py`
- `search_sections(user, query, source_id=None, limit=8)`: OR-ed words, ranked, user-scoped, only `ready` sources. **The only retrieval entry point**: swap its internals to move to embeddings without touching agents.
- `index_sections(source_id)`.

### `documents/generation.py`
- `create_pending_documents(job_posting, resume) -> (resume_doc, cover_letter_doc)`: new pending rows for the next version.
- `generate_documents(resume_doc, letter_doc, parsed_resume, cover_letter_sample='') -> (resume_doc, letter_doc)`: fills the given rows; the task skips rows that are no longer `pending`.
- `get_voice_profile(user, sources, sample)`: cached by hash.

### `documents/rendering.py`
- `resolve_layout(layout)`, `render_resume_html(content, layout)`, `render_cover_letter_html(markdown, header, layout)`, `html_to_pdf(html) -> (bytes, page_count)`.

### `pipeline/storage.py`
`upload_resume(file, user_id)`, `upload_context_document(file, user_id, extension)`, `read_file(key)`, `delete_resume(key)`, `get_resume_url(key)`.

---

## Parked pipeline (reference only)

Daily loop: Celery beat (per scheduled `Search`) or manual trigger -> `Agent.active` and `Search.active` checks -> JSearch fetch -> dedup against `JobSeen` (user-scoped, `Search.job_cooldown`) -> LLM score (threshold `LLM_SCORE_THRESHOLD`, cap `Search.daily_target`) -> `apply_job` -> `RunLog`.

- There are **no Greenhouse or Lever API clients**; they need employer keys. `ats/utils.detect_ats` only classifies URLs, and every application goes through the browser agent.
- `apply_job` dispatches to Lambda in prod (`USE_LAMBDA=True`) or runs `lambda_runner` in-process locally. Known issues: the local import path is wrong, cover letter personalisation is never called, and an application is marked `submitted` as soon as the async invoke returns.
- Lambda `callback-submit-application` runs Browser Use against the apply URL and POSTs `{status, failure_reason}` to `/api/pipeline/applications/<id>/callback/` with `X-Callback-Secret`. It does not write to Postgres directly. The payload carries a presigned `resume_url`. It deploys as a Docker image to ECR through `.github/workflows/deploy-lambda.yml` on pushes to `main` that touch `lambda/**`. Function memory, timeout and env vars are set by hand in AWS.

---

## Testing

```bash
cd backend && env/bin/python manage.py test --noinput
```

Needs Postgres running (`docker compose up -d db`). LLM calls are mocked in the suite, so a green run does not prove prompts or schemas work. After changing anything in `pipeline/llm`, run the real path once with a throwaway resume PDF, a notes file and a pasted job description (`USE_S3=False`, never against S3), and delete the test user afterwards.

Frontend: `cd frontend && npm run lint && npm run build`. For the browser flow, use Playwright against `npm run dev`; do not run `npm run build` while a dev server is running in the same folder (the shared `.next` directory makes the dev page reload forever).

---

## Local development notes

- `docker compose up` runs everything. To run pieces on the host instead, point `CELERY_BROKER_URL` at `localhost`.
- **macOS:** Celery's default prefork pool segfaults after forking; run the worker with `--pool=solo`.
- A Redis already running on the host shadows Docker's published `6379` for `localhost` (and has no password).
- `.env` ships with `USE_S3=True`. Override to `False` for local runs so nothing is written to S3.
- `USE_LAMBDA=False` runs the browser agent in-process (parked path).

---

## General

### Never do this
- No TypeScript. Plain JS in the frontend.
- No `console.log` in committed code. Use proper logging.
- No hardcoded URLs, API keys or credentials.
- No `TODO` comments without a linked task.
- No raw model output in CSS or HTML without validation or escaping.
- No forced `tool_choice` for structured output; use `call_structured`.

### Git
- Branch from `main`: `feature/`, `fix/`, `chore/`.
- Commit messages: imperative present tense (`Add job scoring task`).
- Never commit `.env`, `node_modules/`, `__pycache__/`, build artifacts, or personal files. `docs/` is gitignored and holds local test inputs.
