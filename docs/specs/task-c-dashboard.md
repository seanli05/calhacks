# Task C: dashboard API and Next.js dashboard

You are building the web dashboard: FastAPI routes in `backend/app/api/` over the DB helpers, and a Next.js app in `dashboard/`. Then you set up deployment (ngrok for Twilio). This doc is everything you need; the conversation that wrote it may be gone.

**Progress:** step 1 (design) is approved, see [Design](#design). The dashboard foundation and the live case view are built. The rest is split for parallel work in [dashboard-build.md](dashboard-build.md) (pages, conventions, start prompts) and [dashboard-api.md](dashboard-api.md) (step 2 in detail, which supersedes the route table below). What's left before this task is done: [dashboard-done.md](dashboard-done.md).

## Read first
1. [CLAUDE.md](../../CLAUDE.md): product rules and conventions.
2. [Plan.md](../../Plan.md) → **Events** (C14, C23, C27), **Data model and memory** (C26), **MVP** item 11, **Decisions** (dashboard access is a plain link).
3. [data-layer-schema.md](data-layer-schema.md): tables and columns.
4. [data-layer-guide.md](../data-layer-guide.md): how to use the helpers and contracts, case stages, gotchas, open issues.

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
- **Reset:** `cd backend && python -m app.db.reset --yes` drops, recreates, and seeds one Spanish-speaking user (fake WhatsApp number) plus the demo I-797C case: refs, R1, a provisional case brief in the shape of `CaseBrief` from `research/models.py`, and a verified verification whose official phone is the mock agency line (`TWILIO_MOCK_AGENCY_NUMBER`, in `.env.example`). Its stage is `awaiting_consent`. The shared database was seeded this way. Reset wipes it for everyone, so ask Chris first; use it on the test branch freely.
- **Seed is thin for the dashboard:** no messages, facts, profile, or finished call yet, and only two events. Extending the seed in `backend/app/db/reset.py` with fictional dashboard data (a WhatsApp exchange, a few facts, a finished call with transcript and report, the matching events) is in scope for this task; keep every value fictional.
- **Helpers** the dashboard uses (all async):
  - `app.db.reads`: `list_events(user_id, since)` (returns `Event` contracts, oldest first, `since` exclusive), `list_active_cases(user_id)`, `case_progress(case_id)` (returns a `CaseStage`: `received`, `explaining`, `needs_better_image`, `checking`, `suspicious`, `unknown`, `awaiting_consent`, `calling`, `on_hold`, `connected`, `call_ended`, `closed`), `get_case`, `latest_verification`, `get_brief`, `get_call`, `get_transcript(call_id)`, `get_document`, `get_media`, `get_user`, `get_profile`, `list_facts(user_id, statuses)`, `list_messages(user_id)`.
  - `app.db.deletes`: `delete_fact`, `delete_document` (and its page images), `delete_transcript`, `delete_everything(user_id)`. Each commits with a `*.deleted` event that carries IDs only.
  - Missing rows raise `app.db.errors.NotFound`; map it to 404.
- No read lists a case's calls or briefs, or all users, yet. `app.db.reads` is Chris's, so add small reads there as you need them (same style: one `select`, explicit args, return table rows).
- **Translation module** (person 2, `backend/app/translation/`) is still empty. The feed needs it only for event types without a template (C23); until it lands, show `summary_en` for those.
- **Tests:** DB tests run when `TEST_DATABASE_URL` is set (it's in Chris's `.env.local`; a separate Neon branch named `test`). Never point it at the shared database. A full run with DB tests takes about a minute.
- Python 3.12 isn't installed; use 3.13 in a gitignored `.venv`. Node is 20.15.

## Scope
- **Edit:** `backend/app/api/`, `backend/app/main.py` (mount the router only), `backend/app/db/reads.py` (new reads only), `backend/app/db/reset.py` (seed data only), `backend/tests/test_api_*.py`, `dashboard/`, README run commands.
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
Approved by Chris (step 1). Mockups are drawn in English; the real UI shows the user's language.

### Look
- **Canvas:** dark, deep green-black (around `#0B1410`), not pure black.
- **Green:** forest-toned surfaces; mint (around `#3DF5A7`) only for live things (call pulse, current step, hold timer).
- **Type:** a warm serif for big headlines, a clean sans (Inter or Geist) for UI. Fonts must cover every script we show; use Noto fallbacks. Arabic and right-to-left are out.
- **Futuristic:** glassy cards, hairline borders, a soft glow from the active element. No gradient mesh, no illustrations.
- **Human:** copy is plain sentences in the user's language, not system logs. Rounded corners, slow pulses.
- **Status colors:** "verified" is a mint check plus a label, never color alone. Warnings are amber, "suspicious" is coral (not bright red).
- **1080p video:** big type, high contrast, relative times ("3 min ago"), no tiny clock text.

### Language
- Language-agnostic: UI labels come from one string file per language, picked from the user's profile. Feed templates are per language (step 2). Adding a language means adding those two files.
- Spanish and English for the demo, plus a language switch in the header to flip the whole dashboard live.
- Feed lines: the user's language, with English smaller and muted underneath.

### Other decisions
- **User:** the single seeded user, from the URL. No picker.
- **Refs:** masked to the last 4 (`Receipt ••••4821`).
- **Product name:** not chosen yet; `[App]` placeholder.
- **Assistant panel:** a mirror of the WhatsApp thread with three suggestion cards on top and a chat bar at the bottom. The suggestion buttons and the chat bar open WhatsApp (`wa.me` link) with the text prefilled. The orchestrator answers there, and the reply shows up in the panel through polling. This keeps rules 1 and 5. Sending directly from the dashboard would need a team decision.
- **Suggestions:** rule-based, with no model call: a countdown to the interview date, checklist items still open, and glossary terms that appear in the letter. Rendered server-side from the per-language templates.
- **Deletes:** only on the memory page.

### What this adds to steps 2 and 3
- `GET /api/users/{user_id}/suggestions`: the three cards, rendered in the user's language with their `wa.me` prefill text.
- A new read in `app.db.reads` for the glossary terms that appear in a case's letter.
- Landing QR: the WhatsApp sandbox number (`TWILIO_WHATSAPP_FROM`) plus the sandbox join code. The join code needs a new env var (for example `TWILIO_SANDBOX_JOIN_CODE`).

### Pages

**1. Landing `/`:** explains the product, and a QR code opens WhatsApp with the sandbox join message prefilled, so judges can try it.
```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◉ [App]                                                    [ EN ▾ ]      │
│                Your letter, explained. Your call, made.                  │
│                     (serif headline, mint glow behind)                   │
│        We read immigration letters in your language, check they're       │
│           real, and wait on hold with the agency for you.                │
│                        ┌────────┐                                        │
│                        │  [QR]  │   Scan to try it on WhatsApp           │
│                        └────────┘                                        │
│    ① Send a photo  ───────  ② We check it's real  ───────  ③ We call     │
│    of your letter          against official sources        and ring you  │
│                                                            when a human  │
│                                                            picks up      │
└──────────────────────────────────────────────────────────────────────────┘
```

**2. My cases `/u/<id>`:** active cases with a five-step tracker, a history list, and the assistant panel.
```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◉ [App]      My cases · What we know about you                 [ EN ▾ ]  │
├───────────────────────────────────────────────┬──────────────────────────┤
│  My cases                                     │  ASSISTANT               │
│  ┌─────────────────────────────────────────┐  │ ┌──────────────────────┐ │
│  │ [thumb]  Asylum interview · I-797C      │  │ │ Your interview is in │ │
│  │ ● On hold with USCIS          12:34     │  │ │ 20 days  [Prepare →] │ │
│  │ ●─────●─────●─────◉─────○               │  │ └──────────────────────┘ │
│  │ Letter Verified Calling Hold Person     │  │ ┌──────────────────────┐ │
│  └─────────────────────────────────────────┘  │ │ Key English words    │ │
│                                               │ │ asylum · interpreter │ │
│  HISTORY                                      │ │          [Practice →]│ │
│  📄  Letter received              2 days ago  │ └──────────────────────┘ │
│  ✓   Confirmed it's real          2 days ago  │ ┌──────────────────────┐ │
│  📞  Call to USCIS                 now        │ │ Still need: an       │ │
│  💬  12 messages                  see all     │ │ interpreter  [Ask →] │ │
│                                               │ └──────────────────────┘ │
│                                               │ ──────────────────────── │
│                                               │   [letter photo]    You  │
│                                               │ This is an asylum        │
│                                               │ interview notice. Want   │
│                                               │ us to call USCIS?        │
│                                               │                Yes ✓ You │
│                                               │ ┌──────────────────────┐ │
│                                               │ │ Ask anything...    ➤ │ │
│                                               │ └──────────────────────┘ │
└───────────────────────────────────────────────┴──────────────────────────┘
```
The tracker collapses the 12 `CaseStage` values into Letter → Verified → Calling → Hold → Person.

**3. Case live view `/u/<id>/cases/<id>`:** on screen for the whole call segment of the demo. The feed is newest at the bottom. When the call ends, the headline block becomes the call report, with a "View transcript" slide-over.
```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◉ [App]   ← My cases                                           [ EN ▾ ]  │
├──────────────────┬───────────────────────────────────┬───────────────────┤
│ YOUR LETTER      │  We're on hold with USCIS         │  ASSISTANT        │
│ [thumb]  I-797C  │  ● 12:34      (serif, mint pulse) │ ┌───────────────┐ │
│ Asylum interview │                                   │ │ suggestion    │ │
│ Nov 12 · 9:00 AM │  ●─────●─────●─────◉─────○        │ └───────────────┘ │
│ Receipt ••••4821 │  Letter Verified Calling Hold Pers│ ──────────────── │
│                  │                                   │ Want us to call   │
│ ✓ It's real      │  3 min ago                        │ USCIS?            │
│   number matches │  We confirmed the official number │           Yes ✓   │
│   uscis.gov      │  1 min ago                        │ Calling now. We'll│
│                  │  We chose option 2 in the menu    │ ring you when a   │
│ WHAT TO DO       │  now                              │ person answers.   │
│ ☐ Bring an       │  We're on hold                    │                   │
│   interpreter    │                                   │ ┌───────────────┐ │
│ ☐ Bring passport │                                   │ │ Ask...      ➤ │ │
└──────────────────┴───────────────────────────────────┴───────────────────┘
```

**4. What we know about you `/u/<id>/memory`:** profile and facts, documents, and transcripts, each with a delete button, plus "Delete everything". A deleted row fades out and leaves "(deleted Oct 23)" in the feed.
```
┌──────────────────────────────────────────────────────────────────────────┐
│ ◉ [App]      My cases · What we know about you                 [ EN ▾ ]  │
├──────────────────────────────────────────────────────────────────────────┤
│  What we know about you                                                  │
│  You can delete anything, any time.                                      │
│  PROFILE      Name · Language · City                                     │
│  FACTS        "Has two children"                            [ Delete ]   │
│               "Has a lawyer at a legal aid clinic"          [ Delete ]   │
│  DOCUMENTS    [thumb]  I-797C interview notice              [ Delete ]   │
│  CALLS        Transcript · call to USCIS, Oct 23            [ Delete ]   │
│                          [ Delete everything ]                           │
└──────────────────────────────────────────────────────────────────────────┘
```
