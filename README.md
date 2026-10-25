# Callback

Writes a tailored resume and cover letter for a job, in the user's own voice, from their resume, a cover letter sample and optional supporting documents (projects, notes). The user edits both in the app and downloads PDFs.

## Versions

1. **V1 (MVP, current):** paste a job description, get a tailored resume and cover letter, edit them, download PDFs.
2. **V2:** scan for jobs matching the user's search requirements and push them to the user, who signs off on which jobs the AI generates documents for.
3. **V3:** the AI applies for the user, using a browser agent or whatever means is possible by then.

## Stack

Next.js (JavaScript, Tailwind) frontend; Django + DRF backend with Celery and Redis; Postgres; Anthropic API for generation; WeasyPrint for PDF export; S3 for file storage.

## Running locally

```bash
cp .env.example .env     # fill in values; set USE_S3=False for local runs
docker compose up --build
```

On macOS, run the Celery worker on the host with `--pool=solo`. See `CLAUDE.md` for test and lint commands.

## Docs

- `CLAUDE.md`: short project rules and commands for AI sessions.
- `AGENTS.md`: architecture, data model, API, conventions.
- `status.md`: current progress, known gaps and what is next.
