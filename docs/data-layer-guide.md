# Data layer and contracts: how to use them

This is the guide for writing code against the database and shared contracts. Read it before your component touches Postgres or builds a payload.

It doesn't restate the spec. What things *are* lives in [Plan.md](../Plan.md) (source of truth) and [data-layer-schema.md](specs/data-layer-schema.md) (every table and column). This guide covers how to *use* them. For exact signatures, the code in `backend/app/db/` and `backend/app/contracts/` is authoritative; if this guide disagrees with the code, the code wins and this guide needs a fix.

Owner: person 1. Ask before changing the schema, the contracts, or another writer's module.

## What exists on `main`

| Piece | Where | Status |
|---|---|---|
| Contracts (every Plan.md payload) | `backend/app/contracts/` | Done. `CaseBrief` is still a placeholder `dict` (persons 3 and 4 define it) |
| Tables (all 16) | `backend/app/db/tables.py` | Done; created on app startup |
| Helpers (reads, writes, jobs, events, messages, deletes) | `backend/app/db/` | Done; tested against Postgres |
| Reset and demo seed | `python -m app.db.reset` | Done (`--after-call` adds a finished call) |
| WhatsApp pipe, relay, ask_user, call-status messages | `backend/app/relay/`, `orchestrator/` | On `main`; writes `users`, `media`, `documents`, `messages`, `questions`, events. Status: [whatsapp-pipe.md](whatsapp-pipe.md) |
| Orchestrator's Claude turn, translation, memory writer | their packages | Not on `main` yet |
| Phone agent | `backend/app/phone/` | State machine and menu decider on `main`; the call runner (dial, hold, bridge, report) not yet |
| Research agent | branch `research_agent`, top-level `research/` | Has its own models; not yet on the shared contracts (see [Open issues](#open-issues)). `app/dev/fake_research.py` stands in for it |
| Dashboard and its API | `dashboard/`, `backend/app/api/` | Done. What components must write to show up: [dashboard-AGENTS.md](dashboard-AGENTS.md) |

## Setup

- Database: one shared Neon Postgres. URLs live in the repo-root `.env.local` (gitignored; ask person 1). `settings.py` converts Neon's URL for asyncpg and prefers the unpooled one.
- Startup (`uvicorn app.main:app --app-dir backend`) creates any missing tables. It never alters existing ones; a column change needs a reset.
- `cd backend && python -m app.db.reset --yes` drops every table, recreates them, and seeds the demo case; `--empty` skips the seed. **It wipes the shared database for everyone**, so ask the team first. Without `--yes` it only prints the target host.
- DB tests use `TEST_DATABASE_URL`, a separate Neon branch named `test`. Never point it at the shared database (the tests check this and refuse).

## The import rule (one writer per table)

Each component imports **only its own writer module**, plus the shared modules. Following this convention is what keeps rule 5 (one writer per table) true, so don't import another component's writer, and don't write raw SQL.

| Module | Who may import it | Tables it writes |
|---|---|---|
| `app.db.writes.orchestrator` | orchestrator | `users`, `media`, `documents` |
| `app.db.writes.research` | research agent | `cases`, `case_briefs`, `verifications`, `case_refs` |
| `app.db.writes.phone` | phone agent | `calls`, `transcripts` |
| `app.db.writes.relay` | relay | `questions` |
| `app.db.writes.memory` | memory writer | `profile`, `facts` |
| `app.db.writes.glossary` | glossary worker | `glossary` |
| `app.db.messages` | orchestrator, relay | `messages` (append-only) |
| `app.db.events` | everyone | `events` (append-only) |
| `app.db.jobs` | job creators (`enqueue`) and handlers (`claim_next`, `finish`, `fail`) | `jobs` |
| `app.db.deletes` | dashboard (the "What we know about you" page) | deletes across tables (C26) |
| `app.db.reads` | everyone | nothing |

Need a read that doesn't exist? Add a small one to `app.db.reads` (one query, explicit args, returns table rows) and tell person 1. Need a new write? Ask person 1 first.

## Conventions

- **Everything is async.** Every helper opens its own session and commits before returning. There's no transaction spanning two helper calls; design for each call standing alone.
- **Helpers return table rows** (`tables.Case`, `tables.Job`, …), except `reads.list_events`, which returns `Event` contracts. Rows stay usable after the call (`expire_on_commit=False`).
- **Missing rows:** `get_*` reads return `None`. Writes that update a row raise `app.db.errors.NotFound`.
- **Name clashes:** `tables.Event`, `tables.Verification`, and `tables.CaseBrief` share names with contracts. Import the module (`from app.db import tables`) and qualify; import contracts by name (`from app.contracts import Event`).
- **IDs:** `new_id("case")` gives `case_<16 hex>` (`app.db.ids`). Table rows mint their own IDs when you don't pass one. The orchestrator mints `case_id` before enqueueing H1; the phone agent's `create_call` mints `call_id` (C7).
- **Times:** UTC, timezone-aware. Use `app.db.tables.utcnow()`.
- **Enums:** stored as text. Pass the `StrEnum` (`JobStatus.DONE`); values read back may be plain `str`, which compares equal to the enum.
- **Contracts reject unknown fields** (`extra="forbid"`), so a typo fails loudly. Build payloads from the models; never hand-build the dicts.
- **Options are 1-based** (C5), everywhere: `default_option`, `choice`.
- **Secrets:** sensitive values (receipt number, A-Number, date of birth, interview location) never appear in payloads, events, or logs. Put the value in `case_refs` with `research.put_ref`, pass `<ref:name>` around, and resolve it with `reads.resolve_ref` only at the point of use.

## Contracts at a glance

`from app.contracts import <Name>`. Fixtures for every Plan.md example live in `backend/tests/fixtures/contracts/*.json`; reuse them as fake inputs.

| Plan.md | Model | Where it goes |
|---|---|---|
| H1 | `ResearchFastJob` | `jobs.payload` (type `research_fast`) |
| — | `ResearchDeepJob`, `MemoryWriteJob`, `GlossaryLookupJob` | `jobs.payload` |
| H2 | `CallJob` (no phone numbers, no `call_id`) | `jobs.payload` (type `call`) |
| — | `JobPayload` | Discriminated union on `job`; `jobs.payload_of(row)` parses a row into it |
| R1 | `FastResult` (+ `Appointment`, `ChecklistItem`, `KeyFact`) | `jobs.result` and `cases.fast_result` |
| R2 | `DeepResult` (+ `Verification`) | `jobs.result`; the verdict also goes to `verifications` |
| P1 | `AskUserRequest`; reply `AskUserReply` | `questions` |
| P3 | `CallReport` | `jobs.result` and `calls.report` |
| C14 | `Event`, `EventType`, `USER_MESSAGING_EVENTS` | `events` |
| — | `CaseBrief` (`dict` for now) | `case_briefs.brief` |

Enums and string types (`LanguageCode`, `PhoneE164`, `RefPlaceholder`, ID aliases) are in `app.contracts.common`.

## Recipes

These sketch the demo path per component. Each step names the real helper; check its docstring for details.

### Events (everyone)

Every significant decision is an event. The dashboard feed is built from them.

```python
from app.contracts import Component, Event, EventType
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow

await append_event(
    Event(
        event_id=new_id("event"),
        created_at=utcnow(),
        type=EventType.CALL_MENU_CHOICE,
        source=Component.PHONE_AGENT,
        user_id=user_id,
        case_id=case_id,
        call_id=call_id,
        job_id=job_id,
        summary_en="Pressed 2 (Appointments)",
        data={"digit": "2"},
    )
)
```

- `user_id` is required on every event (schema resolution 3).
- **IDs only (C27):** an event about a fact or document carries its ID in `data`, never its text, and `summary_en` doesn't repeat it.
- Only the four types in `USER_MESSAGING_EVENTS` message the user (P2), and only through the relay.

### Job handlers (research, phone, memory, glossary)

```python
from app.db import jobs

job = await jobs.claim_next(JobType.RESEARCH_FAST)  # None if the queue is empty
if job:
    payload = jobs.payload_of(job)  # -> ResearchFastJob
    try:
        result = ...  # do the work
        await jobs.finish(job.id, result)  # result: a contract model or dict
    except SomeSpecificError as exc:
        await jobs.fail(job.id, str(exc))  # no secrets in the error text
```

- `claim_next` uses `FOR UPDATE SKIP LOCKED`, so several workers can poll one type safely. There's no notification: poll on an interval (about 1 s) in a background task.
- No automatic retries. Retry policy follows Plan.md's failure rules.

### Orchestrator

1. Inbound message: `writes.orchestrator.get_or_create_user(number)` with the plain E.164 number (strip Twilio's `whatsapp:` prefix), then `messages.append_message(user.id, MessageDirection.IN, MessageSender.USER, body, language, body_en=…, media_ids=…, twilio_sid=…)`.
2. Language choice: `set_language(user_id, "es")`.
3. Photo: `save_media(user_id, content_type, data, twilio_media_url)` → `create_document(user_id, [media.id])`. Extra pages of the same letter go to `add_pages(document_id, [media_id])` (C20).
4. Start research: mint `case_id = new_id("case")`, then `jobs.enqueue(ResearchFastJob(case_id=…, user_id=…, document_ids=[…], user_language=…), Component.ORCHESTRATOR, user_id, case_id)`.
5. Watch your jobs (`reads.get_job`) and the case stage (`reads.case_progress`); react to R1, R2, and P3 when their jobs are `done`.
6. Consent: the user's YES is an `append_message` row; enqueue `CallJob(..., consent_message_id=<that msg id>, consent_at=…)`. One YES covers one call (C21).

### Research agent

1. Claim `research_fast`. `reads.get_document` gives the pages (`[{"media_id", "added_at"}]`); `reads.get_media(media_id).data` gives the bytes.
2. `writes.research.create_case(case_id, user_id, document_ids)`. The `case_id` comes from the payload; the orchestrator minted it. It's idempotent, so a second fast pass for the same case (C39) reuses the row.
3. For each sensitive value: `put_ref(case_id, "receipt_number", value)`. Use only `<ref:receipt_number>` in R1.
4. `save_fast_result(case_id, fast_result)` (also sets `doc_type` and `deadline`), `jobs.finish(job.id, fast_result)`, then enqueue `ResearchDeepJob`.
5. Deep pass: `save_verification(case_id, verification)` (adds a row; the latest one counts), then `save_brief(case_id, brief)` with a `CaseBrief` (its own `brief_id` becomes the row's ID, so R2 can name it), then `jobs.finish(job.id, deep_result)`.
6. Glossary misses: enqueue `GlossaryLookupJob` (stretch).

### Phone agent

1. Claim `call`; `payload_of(job)` gives a `CallJob`.
2. **Number to dial: only `reads.official_dial_number(case_id)`** (rule 2). It raises `UnverifiedNumber` unless the case's latest verification is `verified` and has a phone. While `DEMO_DIAL_NUMBER` is set it returns that number instead, after the same checks (Plan.md C40). Never dial anything else, and don't catch the error to fall back.
3. The user's number to ring: `reads.get_user(user_id).whatsapp_number` (C6, C29).
4. The brief: `reads.get_brief(brief_id).brief`. Resolve refs only if needed, with `reads.resolve_ref(case_id, "<ref:…>")`; the agent never speaks identifiers (C35).
5. `writes.phone.create_call(case_id, job.id, brief_id, consent_message_id)`, then `set_call_state(call_id, CallState.MENU, twilio_call_sid=…)` as the call moves. `ENDED` sets `ended_at`.
6. `save_transcript(call_id, lines)` creates or replaces the transcript, so calling it repeatedly is fine. Each line is `{"at", "speaker": "agent"|"agency"|"user", "text"}`.
7. `save_call_report(call_id, report)`, then `jobs.finish(job.id, report)`.

### Relay (ask_user)

1. `writes.relay.create_question(ask_user_request, user_id)`, then send the templated message via `append_message(..., sender=MessageSender.RELAY, template=…, question_id=…)`.
2. Inbound reply: `reads.get_open_question(user_id)` finds the question, then call `answer_question(question_id, choice)`.
3. Timeout: `time_out_question(question_id)`.
4. Answer and timeout race safely: whichever runs second gets `None`. A `None` from `answer_question` means the reply was late: call `record_late_reply`, send the late-reply template, and log `call.ask_user_late_reply` (C24).

### Memory writer

- `writes.memory.add_fact(user_id, fact, category, source, sensitivity, status, source_ref=…)`. Immigration facts are always `FactStatus.PENDING_CONSENT` (C15, C25). Applying that rule is your job; the helper doesn't check it.
- On the user's yes: `set_fact_status(fact_id, FactStatus.ACTIVE)`.
- `upsert_profile(user_id, {...})` merges keys into the profile.
- Agents read facts with `reads.list_facts(user_id, [FactStatus.ACTIVE])`.

### Dashboard

Reads plus `app.db.deletes`: `delete_fact`, `delete_document` (and its images), `delete_transcript`, `delete_everything(user_id)` (keeps `users` and `events`). Each commits with a `*.deleted` event. The feed polls `reads.list_events(user_id, since=<last created_at>)`; `since` is exclusive. The dashboard API (`app/api/`) also uses `first_user`, `list_cases`, `list_calls`, `latest_brief`, `list_case_refs` (real values: mask before showing), `list_documents`, `list_transcripts`, and `first_event` (the hold timer starts at the call's first `call.on_hold`). See [task-c-dashboard.md](specs/task-c-dashboard.md) and [dashboard-api.md](specs/dashboard-api.md).

## Case stage

`reads.case_progress(case_id)` returns a `CaseStage` (in `app.db.progress`). It's computed, never stored (C17). The latest call outranks the verdict, and the verdict outranks research.

| Stage | When |
|---|---|
| `received` | Case exists, nothing started |
| `explaining` | Latest `research_fast` job is queued or running |
| `needs_better_image` | R1 came back `needs_better_image` |
| `needs_answer` | R1 came back `needs_user_input` (C39): waiting for the user's answer |
| `checking` | Deep pass queued or running, verification pending, or R1 ok with no verdict yet |
| `suspicious` / `unknown` | Latest verification says so |
| `awaiting_consent` | Verified, no call yet |
| `calling` | Latest call is `dialing` or `menu` |
| `on_hold` | Latest call is `hold` |
| `connected` | Latest call is `human_detected`, `bridging`, `connected`, or `wrap_up` |
| `call_ended` | Latest call is `ended` |
| `closed` | A `case.closed` event exists (C22) |

`reads.list_active_cases(user_id)` returns every case that isn't `closed`.

## Where the product rules are enforced

| Rule | Enforced by the data layer | Still your job |
|---|---|---|
| 2. Never dial an unverified number | `official_dial_number` raises unless verified | Use nothing else to get a number |
| 4. Recorded consent | `calls.consent_message_id` is a required FK to `messages` | Ask before every call |
| 5. One writer per table | The import convention above | Follow it |
| C11/C34 refs | `case_refs`, read only through `resolve_ref` | Keep real values out of payloads, events, logs |
| C27 IDs-only events | Delete helper events carry IDs only | Same for every event you write |

Rules 1, 3, and 6 (only the orchestrator talks free-form, never impersonate the user, English inside) are component behavior; the data layer can't check them.

## Gotchas

- **JSON columns:** assign a new value (`row.pages = [*row.pages, new]`); mutating in place isn't saved. Only matters if you add a helper.
- **Insert order:** tables have FKs but no ORM relationships. If one session adds a parent and child, `flush()` the parent first.
- **Events need a user:** `events.user_id` is a required FK, so log events only after the user row exists.
- **Tests and event loops:** each pytest test gets a new event loop. Dispose the engine between tests (see `backend/tests/test_db_helpers.py`).
- **No migrations:** after a column change, run reset. Nothing alters existing tables.

## Testing your component

- Unit tests must not hit the network. Monkeypatch the helpers you call (they're plain async functions), and use the contract fixtures as inputs.
- DB-backed tests run only when `TEST_DATABASE_URL` is set; copy the fixture pattern from `test_db_helpers.py`.
- The seeded demo case (`reset --yes` on the test branch) gives a verified case at `awaiting_consent` with a brief, useful for phone and orchestrator work. Seed values are in `backend/app/db/reset.py`.

## Open issues

Open as of this writing; ask person 1 for the latest.

- **Research models vs contracts.** `research/models.py` (branch `research_agent`) differs from `app.contracts`:
  - It adds a `needs_user_input` status and `key_dates`.
  - `Sensitivity` is `high` where the contracts use `sensitive`.
  - `KeyFact` uses `value`/`page` instead of `citation`.
  - It stores `signals`/`call_purpose` on the case, which has no column.
  
  These need reconciling (contracts or models) before research writes to the DB.
- **`CaseBrief`** is a placeholder `dict`. The seed uses the shape of `CaseBrief` in `research/models.py` (branch `research_agent`) as a working version: `call_goal_en`, `expected_menu_path`, `questions_to_ask`, `must_not_do`, `facts` (refs), `handoff_note`, `likely_rep_questions`, `contingencies`. Build against it; persons 3 and 4 still need to confirm it.
- **Demo seed** uses a fake WhatsApp number, so the real demo phone won't match the seeded user yet, and `TWILIO_MOCK_AGENCY_NUMBER` as the verified "official" number (unset means nothing to dial).
- **Declined sensitive facts:** C15 says the memory writer deletes a fact the user says no to. There's no memory-writer delete helper yet. Ask person 1 before deleting through `app.db.deletes` (that path logs a user-facing `fact.deleted` event).
