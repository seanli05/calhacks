# Task A: database tables, reset script, and DB helpers

You are implementing `backend/app/db/`: the SQLModel tables, a reset/seed script, and the helpers every component uses to read and write. Task B builds `backend/app/contracts/` in parallel. This doc is everything you need; the conversation that wrote it may be gone.

## Read first
1. [CLAUDE.md](../../CLAUDE.md): product rules and conventions.
2. [data-layer-schema.md](data-layer-schema.md): **the locked schema.** Every table, column, type, and writer. Build exactly this.
3. [Plan.md](../../Plan.md) → **Handoffs** and **Data model and memory**: what the tables hold and why (C-tags explain each choice).
4. [task-b-contracts.md](task-b-contracts.md): the enums you import from `app.contracts.common`.

Plan.md is the source of truth. Don't apply anything from older docs (a PRD or the original Plan.txt); they're gone for a reason.

## Who you're working for
Chris (person 1) owns the data layer. Working style:
- Hackathon scope: build what the demo shows; skip edge cases the demo never hits. Maximally impressive for minimal dev friction.
- Commit often; one short imperative line; no AI attribution. Merge to `main` by fast-forward when green (`gh` isn't installed). Ask before changing Plan.md or another person's package.
- Questions to Chris: simple, framed by what the user or team experiences. Tell Chris when something needs relaying to the team, and keep that rare.

## State of the repo (as of this doc)
- `main` has: backend skeleton (`backend/app/main.py`, `settings.py`, owner packages), `pyproject.toml` (ruff + pytest config; `pythonpath = ["backend"]`), and the Neon connection: `backend/app/db/engine.py` (`get_engine()`, `session()`, `ping()`), `GET /health/db`.
- Database: one shared **Neon** Postgres for the whole team. Chris's connection URLs are in the repo-root `.env.local` (gitignored). `settings.async_database_url` converts Neon's URL for asyncpg and prefers the unpooled one.
- Untracked `neon.ts`, `package.json`, `package-lock.json`, `node_modules/` in the repo root are from `neon init`; don't commit them (Chris may delete them).
- Python 3.12 isn't installed; use 3.13 in a gitignored `.venv`. `pipecat-ai` is slow to install and not needed here.

## Scope
- **Edit:** `backend/app/db/`, `backend/app/main.py` (startup hook only), `backend/tests/test_db_*.py`, README run commands.
- **Don't touch:** `backend/app/contracts/` (task B; import from it), other packages, Plan.md.
- If `app.contracts.common` isn't on `main` yet, start with plain `str` columns and swap in the enums when it lands.

## Steps (commit after each)

### 1. Tables (`db/tables.py`)
- SQLModel `table=True` classes for every table in the schema spec, columns exactly as listed.
- `JSONB` via `sa_column=Column(JSONB)`; timestamps `DateTime(timezone=True)`, defaulting to now in UTC; enums as text, typed with the `StrEnum`s.
- `new_id(prefix)` in `db/ids.py`: `f"{prefix}_{secrets.token_hex(8)}"`.
- `create_all()` on app startup (FastAPI lifespan in `main.py`).

### 2. Reset and seed (`db/reset.py`, run as `python -m app.db.reset`)
- Drops and recreates every table, then seeds the demo.
- **The database is shared, so this wipes everyone's data.** Require `--yes`, print the target host first, and refuse without the flag.
- Seed values must match `mock_agency/agency/case_record.py` (`DEMO_CASE`): receipt `ZLA2690012345`, A-Number `A212345678`, date of birth 1988-03-14, interview 2026-11-12 8:30 AM, Los Angeles Asylum Office, 1585 Corporate Drive, Tustin, California. Seed: one demo user (fake WhatsApp number, language `es`), one case with those values in `case_refs`, and a verified verification. Seeding writes several owners' tables; the script is a dev tool, exempt from the one-writer rule.
- `--empty` drops and recreates with no seed.

### 3. Helpers
One module per writer, plus shared reads. Every component imports only its own writer module plus `reads`; that convention is how one-writer is enforced.

| Module | Writer | Functions (async, take explicit args, return table rows or contract models) |
|---|---|---|
| `db/writes/orchestrator.py` | orchestrator | `get_or_create_user(whatsapp_number)`, `set_language(user_id, language)`, `save_media(...)`, `create_document(user_id, media_ids)`, `add_pages(document_id, media_ids)` |
| `db/writes/research.py` | research agent | `create_case(case_id, user_id, document_ids)`, `save_fast_result(case_id, FastResult)`, `save_verification(case_id, Verification)`, `save_brief(case_id, brief, handoff_note)`, `put_ref(case_id, name, value)` |
| `db/writes/phone.py` | phone agent | `create_call(case_id, job_id, brief_id, consent_message_id)`, `set_call_state(call_id, state)`, `save_call_report(call_id, CallReport)`, `save_transcript(call_id, lines)` |
| `db/writes/relay.py` | relay | `create_question(AskUserRequest, user_id)`, `answer_question(question_id, choice)`, `time_out_question(question_id)`, `record_late_reply(question_id)` |
| `db/writes/memory.py` | memory writer | `upsert_profile(user_id, fields)`, `add_fact(...)`, `set_fact_status(fact_id, status)` |
| `db/writes/glossary.py` | glossary worker | `add_term(...)` |
| `db/messages.py` | orchestrator, relay | `append_message(...)` (append-only) |
| `db/events.py` | everyone | `append_event(Event)` (append-only) |
| `db/jobs.py` | creator + handler | `enqueue(payload: JobPayload, created_by, user_id, case_id)`, `claim_next(job_type)` (`FOR UPDATE SKIP LOCKED`), `finish(job_id, result)`, `fail(job_id, error)` |
| `db/deletes.py` | delete helper (C26) | `delete_fact`, `delete_document` (and its media), `delete_transcript`, `delete_everything(user_id)`; each appends a `*.deleted` event with IDs only (C27) |
| `db/reads.py` | anyone | `get_user_by_number`, `get_profile`, `list_facts(user_id, statuses)`, `get_case`, `list_active_cases(user_id)`, `case_progress(case_id)`, `official_dial_number(case_id)`, `resolve_ref(case_id, name)`, `list_events(user_id, since)`, `list_messages(user_id)`, `get_open_question(user_id)`, `get_glossary(language)` |

Key behaviors:
- **`official_dial_number(case_id)`** returns the latest verification's `official_phone` only when its status is `verified`, and raises otherwise. It's the only way the phone agent gets a number (product rule 2).
- **`case_progress(case_id)`** computes the stage (C17); no status column. Values: `received`, `explaining` (fast pass queued or running), `needs_better_image`, `checking` (deep pass running or verification pending), `suspicious`, `unknown`, `awaiting_consent` (verified, no call yet), `calling` / `on_hold` / `connected` (from the latest call's state), `call_ended`, `closed` (a `case.closed` event exists). `list_active_cases` is every case not `closed`. This is a new shape person 2 consumes through `get_case_status`; tell Chris to relay it once it lands.
- **`list_events(user_id, since)`** is what the dashboard feed polls.
- **`delete_everything(user_id)`** erases the user's rows in every table except `events` and the `users` row, then logs `user.deleted_all`.

### 4. Tests
- CLAUDE.md says tests don't hit external services, and the database is shared. So DB tests run only when `TEST_DATABASE_URL` is set (skip otherwise), and that URL must be a separate Neon branch, never the shared one. Ask Chris to create it (`neon branch create --name test`) when you get here.
- Test what would hurt in the demo: `official_dial_number` refuses unverified numbers; `case_progress` across the stages; `claim_next` never hands one job to two claimers; deletes leave only IDs in events; reset refuses without `--yes`.
- Pure tests (`new_id`, reset flag parsing) run always.

## Done when
- `ruff format . && ruff check --fix . && pytest` passes from the repo root.
- `python -m app.db.reset --yes` builds and seeds the shared database (after Chris confirms nobody's mid-test).
- Each step is merged to `main`. Report to Chris: what landed, and the one team message (helpers + `case_progress` values are on main).

## After this
Dashboard spec and build (`dashboard/`, Next.js, polling `list_events`), then deployment (ngrok). Chris starts those after tasks A and B are both done.
