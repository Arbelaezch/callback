<!-- BEGIN:nextjs-agent-rules -->
# AGENTS.md
# Instructions for AI coding agents working on this codebase.
# Read this before generating any code.

## Project
Callback — AI-powered job application agent.
Monorepo: Next.js frontend + Django backend + AWS Lambda function.

---

## Frontend — Next.js

### Version & Router
- Next.js 15, App Router only
- Never use Pages Router (`/pages` directory does not exist)
- Never use `getServerSideProps`, `getStaticProps`, `getInitialProps`

### Components
- Server Components by default — do not add `"use client"` unless the component needs:
  - `useState` / `useReducer`
  - `useEffect`
  - Browser APIs
  - Event listeners
- Keep `"use client"` components small and pushed to the leaves of the tree
- No class components — functional components only

### Data Fetching
- Fetch data in Server Components using async/await directly
- Use `fetch()` with Next.js cache options (`{ cache: 'no-store' }` or `{ next: { revalidate: N } }`)
- Client-side fetching: use SWR or native fetch in a `"use client"` component
- Never use `axios` — use native `fetch`

### Routing & Navigation
- Use `next/navigation` not `next/router`
  - `useRouter` from `next/navigation`
  - `usePathname`, `useSearchParams` from `next/navigation`
- Use `next/link` for all internal links
- File-based routing only — no manual route config

### Imports
- Use `@/` alias for all imports from the project root
- Example: `import Button from '@/components/ui/Button'`
- Never use relative imports that traverse up more than one level

### Styling
- Tailwind CSS only
- No CSS modules, no styled-components, no emotion
- No inline `style` props unless dynamically computed

### Images
- Always use `next/image` — never a raw `<img>` tag

### Fonts
- Use `next/font` — never import fonts via `<link>` in layout

### Metadata
- Use the `export const metadata` API in `layout.tsx` or `page.tsx`
- Never use `next/head`

### Environment Variables
- Server-only vars: `VARIABLE_NAME` (never exposed to browser)
- Browser-safe vars: `NEXT_PUBLIC_VARIABLE_NAME`
- Access via `process.env.VARIABLE_NAME` — never hardcode values

### API Communication
- All API calls go to Django backend at `process.env.NEXT_PUBLIC_API_URL`
- JWT token stored in httpOnly cookie — never localStorage
- Use Server Actions or Route Handlers (`/app/api/`) for server-side API proxying when needed

---

## Backend — Django

### Version & Style
- Django 5.x + Django REST Framework
- Function-based views with DRF `@api_view` decorator preferred for simple endpoints
- Class-based views (`APIView`, `ModelViewSet`) for CRUD-heavy resources

### Auth
- `djangorestframework-simplejwt` for JWT tokens
- All endpoints require `IsAuthenticated` unless explicitly public
- Public endpoints must explicitly set `@permission_classes([AllowAny])`

### Models
- Use Django ORM — no raw SQL unless absolutely necessary
- Always define `__str__` on every model
- Use `created_at` / `updated_at` timestamps on all models via a base model or explicit fields

### Celery
- All background tasks in `/callback/tasks/`
- Tasks must be idempotent — safe to retry on failure
- Always use `.delay()` or `.apply_async()` — never call task functions directly
- Log task start, success, and failure explicitly

### Settings
- Use `python-decouple` for all env var access (`config('VAR_NAME')`)
- Never use `os.environ` directly
- Never hardcode secrets

### URLs
- All API endpoints prefixed with `/api/`
- Version prefix not required at MVP (`/api/jobs/` not `/api/v1/jobs/`)

---

## Lambda — Browser Use

### Language
- Python 3.13
- One function: `callback-submit-application`
- One invocation = one job application (fan-out pattern)

### Patterns
- Always write result back to Postgres directly on completion
- Log all steps — browser navigation is hard to debug without logs
- Handle exceptions explicitly — write `status: failed` + `failure_reason` on any unhandled error, never let Lambda silently fail

---

## General

### Never do this
- No TypeScript — plain JS only in frontend
- No `console.log` left in committed code — use proper logging
- No hardcoded URLs, API keys, or credentials anywhere
- No `TODO` comments without a linked task
- No `any` type workarounds (even in JS, avoid duck-typed assumptions)

### Git
- Branch from `main` for all features: `feature/`, `fix/`, `chore/`
- Commit messages: imperative present tense (`Add job scoring task` not `Added` or `Adding`)
- Never commit `.env`, `node_modules/`, `__pycache__/`, or build artifacts
<!-- END:nextjs-agent-rules -->
