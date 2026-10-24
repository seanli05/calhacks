# Task C: dashboard API and Next.js dashboard

You are building the web dashboard: FastAPI routes in `backend/app/api/` over the DB helpers, and a Next.js app in `dashboard/`. Then you set up deployment (ngrok for Twilio). This doc is everything you need; the conversation that wrote it may be gone.

## Read first
1. [CLAUDE.md](../../CLAUDE.md): product rules and conventions.
2. [Plan.md](../../Plan.md) → **Events** (C14, C23, C27), **Data model and memory** (C26), **MVP** item 11, **Decisions** (dashboard access is a plain link).
3. [data-layer-schema.md](data-layer-schema.md): tables and columns.
4. `README.md` → **Using the database**: which helper module does what.

Plan.md is the source of truth. Don't apply anything from older docs (a PRD or the original Plan.txt).

## Who you're working for
Chris (person 1) owns the data layer, the dashboard, and deployment. Working style:
- Hackathon scope: build what the demo shows; skip edge cases the demo never hits. Maximally impressive for minimal dev friction.
- Commit often; one short imperative line; no AI attribution. Merge to `main` by fast-forward when green (`gh` isn't installed). Ask before changing Plan.md or another person's package.
- Questions to Chris: simple, framed by what the user or team experiences. Tell Chris when something needs relaying to the team, and keep that rare.
- Other agents may be working in the same repo. Work in your own git worktree (`git worktree add ../calhacks26-dash -b chris/dashboard main`) so branch switches don't collide.

## State of `main` (as of this doc)
- **Contracts** (`backend/app/contracts/`): every Plan.md payload as a Pydantic model; `Event` and `EventType` in `events.py`; enums in `common.py`. Import as `from app.contracts import Event`.
- **Tables** (`backend/app/db/tables.py`): all 16, created on app startup. Class names can match contract names (`Event`, `Verification`, `CaseBrief`), so import the module (`from app.db import tables`) and qualify.
- **Reset:** `cd backend && python -m app.db.reset --yes` drops, recreates, and seeds one Spanish-speaking user plus the demo I-797C case (verified, so its stage is `awaiting_consent`). It wipes the shared database, so ask Chris first. Use it on the test branch freely.
- **Helpers** the dashboard uses (all async):
  - `app.db.reads`: `list_events(user_id, since)` (returns `Event` contracts, oldest first, `since` exclusive), `list_active_cases(user_id)`, `case_progress(case_id)` (returns a `CaseStage`: `received`, `explaining`, `needs_better_image`, `checking`, `suspicious`, `unknown`, `awaiting_consent`, `calling`, `on_hold`, `connected`, `call_ended`, `closed`), `get_case`, `latest_verification`, `get_brief`, `get_call`, `get_transcript(call_id)`, `get_document`, `get_media`, `get_user`, `get_profile`, `list_facts(user_id, statuses)`, `list_messages(user_id)`.
  - `app.db.deletes`: `delete_fact`, `delete_document` (and its page images), `delete_transcript`, `delete_everything(user_id)`. Each commits with a `*.deleted` event that carries IDs only.
  - Missing rows raise `app.db.errors.NotFound`; map it to 404.
- No read lists a case's calls or briefs, or all users, yet. `app.db.reads` is Chris's, so add small reads there as you need them (same style: one `select`, explicit args, return table rows).
- **Translation module** (person 2, `backend/app/translation/`) is still empty. The feed needs it only for event types without a template (C23); until it lands, show `summary_en` for those.
- **Tests:** DB tests run when `TEST_DATABASE_URL` is set (it's in Chris's `.env.local`; a separate Neon branch named `test`). Never point it at the shared database. A full run with DB tests takes about a minute.
- Python 3.12 isn't installed; use 3.13 in a gitignored `.venv`. Node is 20.15.

## Scope
- **Edit:** `backend/app/api/`, `backend/app/main.py` (mount the router only), `backend/app/db/reads.py` (new reads only), `backend/tests/test_api_*.py`, `dashboard/`, README run commands.
- **Don't touch:** contracts, other components' packages, Plan.md. The dashboard is a reader plus the delete helper. It never writes any other table (rule 5).

## Steps (commit after each)

### 1. Design gate (no code until Chris approves)
Before writing any dashboard code, discuss design and visuals with Chris, then record what you agreed in a **Design** section at the bottom of this doc. Building starts only after Chris approves that section. Cover:
- **Layout:** one screen with panels, or separate pages? What's visible during the call segment of the demo video?
- **Look:** palette, type, density. It must be legible in a 1080p screen recording: big type, high contrast, no tiny timestamps.
- **What each screen shows on video:** the live feed, case view, "What we know about you", WhatsApp mirror (see step 3).
- **Open questions to settle there:**
  - Should the case view show real ref values (receipt number, A-Number) masked, in full, or not at all? The demo values are fictional, but the link has no access control.
  - Feed language: the user's language only, or with English underneath for the judges?
  - Which user the dashboard shows: the single seeded user, or a picker?

Bring two or three concrete options (ASCII mockups are fine) rather than open-ended questions.

### 2. API (`backend/app/api/`)
Plain JSON routes under `/api`, response bodies as Pydantic models defined in `api/`. Never send media bytes or table rows with `data` blobs in JSON.

| Route | Returns |
|---|---|
| `GET /api/users/{user_id}/feed?since=<iso>` | Feed items: event ID, time, type, rendered text in the user's language, and `deleted_at` where a referenced fact or document is gone (C27) |
| `GET /api/users/{user_id}/cases` | Active cases with their stage |
| `GET /api/cases/{case_id}` | Case, R1 explanation and checklist, latest verdict, latest brief, calls with state and report |
| `GET /api/calls/{call_id}/transcript` | Transcript lines |
| `GET /api/users/{user_id}/memory` | Profile and facts (with status and sensitivity) |
| `GET /api/users/{user_id}/messages` | WhatsApp mirror: both directions, original and English |
| `GET /api/media/{media_id}` | The image bytes with their content type (letter thumbnails) |
| `DELETE /api/facts/{id}`, `/api/documents/{id}`, `/api/transcripts/{id}` | 204 |
| `POST /api/users/{user_id}/delete-everything` | Per-table counts |

**Feed rendering (C23, C27)** is server-side, so the dashboard stays simple:
- `api/feed_templates.py`: a template per language for each event type shown on the demo screen, filled from the event's `data`. At minimum: `case.created`, `research.fast_done`, `verification.*`, `consent.given`, every `call.*` type, `memory.fact_*`, the four delete types. Spanish and English first.
- Other types: `summary_en`, translated through the translation module once it exists, cached in memory.
- An event that references a fact or document by ID shows its text (looked up at render time) or "(deleted [date])" once it's gone. Event rows never contain the content itself.

### 3. Dashboard (`dashboard/`, Next.js)
- Next.js App Router, TypeScript. Proxy `/api` to `http://localhost:8000` with a `rewrites()` rule, so there's no CORS setup.
- Poll about once a second: the feed with `since` set to the last item's time, plus the visible case and messages. No WebSockets.
- Screens, as agreed in the design gate:
  - **Live feed** in the user's language (C23), newest at the bottom or top per the design.
  - **Case view:** letter facts and checklist, verdict with evidence, brief, call state, call report.
  - **"What we know about you":** profile and facts with delete buttons, delete-letter and delete-transcript, and "Delete everything". Deleted items leave a dated line in the feed (C26).
  - **WhatsApp mirror:** the conversation as the user sees it.
- Pin every new npm dependency to an exact version. Keep it small: no component library unless the design needs one.

### 4. Tests
- API tests with `fastapi.testclient` and the DB helpers monkeypatched with fakes (no network): feed renders a template in Spanish; an event for a deleted fact renders "(deleted …)"; delete routes call the right helper; `NotFound` becomes 404.
- One DB-backed test (gated on `TEST_DATABASE_URL`) that seeds and fetches `/api/cases/{id}` end to end.

### 5. Deployment
- The backend runs locally; ngrok exposes it for Twilio: `ngrok http 8000`, set `PUBLIC_BASE_URL`, then point the WhatsApp sandbox and the voice webhooks at it (README → WhatsApp has the sandbox steps).
- Use an ngrok reserved domain if the account has one, so the webhook URL survives restarts.
- The dashboard runs with `npm run dev` (or `npm run build && npm start` for the recording) on the demo laptop. It doesn't need to be public.
- Document the exact commands in the README.

## Done when
- The design section is approved by Chris and recorded below.
- `ruff format . && ruff check --fix . && pytest` passes from the repo root, and `npm run build` passes in `dashboard/`.
- With the backend and dashboard running on the seeded database, the feed, case view, memory page (including a delete), and WhatsApp mirror all work at 1080p.
- Each step is merged to `main`. Report to Chris: what landed, and anything the team needs to know (for example, which event `data` fields the feed templates expect).

## Design
*To be filled in with Chris during step 1.*
