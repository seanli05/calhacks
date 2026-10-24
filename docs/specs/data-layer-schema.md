# Spec: database schema and shared contracts

Owner: person 1 · Status: **draft, not locked** · Implements: Plan.md → Handoffs, Data model and memory

This turns Plan.md's table list and payloads into columns and Pydantic models. It doesn't change Plan.md. Where Plan.md left a mechanical detail open, the resolution is listed under [Resolutions](#resolutions).

## Conventions

- **IDs:** `<prefix>_<16 hex chars>` (e.g. `case_3f9a01c2b7d4e865`), made by `new_id(prefix)` in `app.db`. Prefixes from Plan.md C19, plus `media_` and `term_`. Stored as `TEXT` primary keys.
- **Times:** `TIMESTAMPTZ`, always UTC. Dates without a time: `DATE`.
- **Enums:** stored as `TEXT`, validated by Python `StrEnum`s in `app.contracts`. No Postgres enum types, so adding a value never needs a migration.
- **JSON:** `JSONB`. A JSON column holds one Plan.md payload (or part of one) and is typed in Python by the matching contract model.
- **Schema changes:** tables auto-create on startup; `python -m app.db.reset` drops, recreates, and seeds demo data. No migration tool.
- **Writers:** each table lists its one writer (Plan.md). Exceptions: append-only `messages` and `events` (C2), and the delete helper (C26).

## Tables

Typed columns are the ones we filter, join, or sort on. Everything else sits in JSON.

### `users` — writer: orchestrator
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `user_` |
| `whatsapp_number` | text, unique | E.164. Also the number the user is rung on (C29) |
| `language` | text, null | ISO 639-1; null until the user picks (C1) |
| `created_at` | timestamptz | |

### `profile` — writer: memory writer
| Column | Type | Notes |
|---|---|---|
| `user_id` | text PK, FK users | One row per user |
| `fields` | jsonb | County, household size, contact prefs |
| `updated_at` | timestamptz | |

### `facts` — writer: memory writer (deletes: delete helper)
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `fact_` |
| `user_id` | text, FK users, indexed | |
| `fact` | text | English |
| `category` | text | Free text (e.g. `immigration`, `contact`) |
| `source` | text | `user_said` · `from_document` · `from_call` · `inferred` (C4) |
| `source_ref` | text, null | ID of the message, document, or call it came from |
| `sensitivity` | text | `normal` · `sensitive` (sensitive = immigration, income, health, C25) |
| `status` | text | `active` · `pending_consent` · `superseded` (C16) |
| `supersedes` | text, null | Fact ID it replaced (logic post-MVP, C28) |
| `recorded_at` | timestamptz | |

### `media` — writer: orchestrator
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `media_` |
| `user_id` | text, FK users | |
| `content_type` | text | e.g. `image/jpeg`, `audio/ogg` |
| `data` | bytea | The file itself (see [Resolutions](#resolutions)) |
| `twilio_media_url` | text, null | Where it was downloaded from |
| `created_at` | timestamptz | |

### `documents` — writer: orchestrator
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `doc_` |
| `user_id` | text, FK users, indexed | |
| `pages` | jsonb | Ordered `[{"media_id": "media_…", "added_at": "…"}]` (C20) |
| `created_at` | timestamptz | |

### `cases` — writer: research agent
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `case_`; minted by the orchestrator in H1 |
| `user_id` | text, FK users, indexed | |
| `document_ids` | jsonb | From H1 |
| `doc_type` | text, null | e.g. `uscis_i797c_asylum_interview` |
| `deadline` | date, null | Earliest date the user must act (C31) |
| `fast_result` | jsonb, null | R1 payload |
| `created_at`, `updated_at` | timestamptz | |

No status column: progress is computed from jobs, verification, calls, and a `case.closed` event (C17, C22).

### `case_briefs` — writer: research agent
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `brief_` |
| `case_id` | text, FK cases, indexed | |
| `brief` | jsonb | Case brief model (persons 3 and 4 define) |
| `handoff_note` | text | |
| `created_at` | timestamptz | |

### `verifications` — writer: research agent
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `ver_` |
| `case_id` | text, FK cases, indexed | |
| `status` | text | `pending` · `verified` · `suspicious` · `unknown` (C18) |
| `official_phone` | text, null | E.164. **The only number the phone agent may dial**, and only when `status = verified` |
| `result` | jsonb | R2 `verification` object |
| `created_at` | timestamptz | |

### `case_refs` — writer: research agent (read only via `resolve_ref`)
| Column | Type | Notes |
|---|---|---|
| `case_id` | text, FK cases | PK part 1 |
| `name` | text | PK part 2; e.g. `receipt_number`, `a_number`, `interview_location`, `date_of_birth` |
| `value` | text | The real value (C11, C34) |
| `created_at` | timestamptz | |

### `glossary` — writer: glossary worker (hand seed: person 3)
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `term_` |
| `term` | text | English |
| `language` | text | ISO 639-1; unique with `term` |
| `translation` | text | |
| `source_url` | text, null | |
| `trust_level` | text | `official` · `community` · `machine` |
| `created_at` | timestamptz | |

### `calls` — writer: phone agent
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `call_`; minted by the phone agent (C7) |
| `case_id` | text, FK cases, indexed | Several calls per case |
| `job_id` | text, FK jobs | The `call` job it came from |
| `brief_id` | text, FK case_briefs | |
| `consent_message_id` | text, FK messages | The user's YES (C8) |
| `state` | text | `dialing` · `menu` · `hold` · `human_detected` · `bridging` · `connected` · `wrap_up` · `ended` |
| `twilio_call_sid` | text, null | |
| `outcome` | text, null | `resolved` · `partial` · `failed` · `user_unreachable` |
| `report` | jsonb, null | P3 payload (C12) |
| `started_at`, `ended_at` | timestamptz | `ended_at` null while live |

### `transcripts` — writer: phone agent
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `transcript_` |
| `call_id` | text, FK calls, unique | |
| `lines` | jsonb | `[{"at": "…", "speaker": "agent" \| "agency" \| "user", "text": "…"}]` |
| `created_at` | timestamptz | |

### `messages` — writers: orchestrator, relay (append-only)
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `msg_` |
| `user_id` | text, FK users, indexed | |
| `case_id` | text, null | Best guess at the letter it's about |
| `direction` | text | `in` · `out` |
| `sender` | text | `user` · `orchestrator` · `relay` |
| `body_original` | text | As sent or received |
| `body_en` | text, null | English version |
| `language` | text | ISO 639-1 of `body_original` |
| `media_ids` | jsonb | Photos and voice notes |
| `template` | text, null | Relay template name, if templated |
| `question_id` | text, null | Linked ask_user question |
| `twilio_sid` | text, null | |
| `created_at` | timestamptz, indexed | |

### `questions` — writer: relay
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `question_` |
| `call_id` | text, FK calls, indexed | |
| `user_id` | text, FK users | So an inbound reply finds its open question |
| `template` | text | e.g. `menu_choice` |
| `options_en` | jsonb | |
| `default_option` | int | 1-based (C5) |
| `timeout_s` | int | |
| `status` | text | `open` · `answered` · `timed_out` |
| `choice` | int, null | 1-based |
| `answered_at`, `late_reply_at` | timestamptz, null | `late_reply_at` set for C24 |
| `created_at` | timestamptz | |

### `jobs` — writers: creator inserts, handler updates
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `job_` |
| `type` | text, indexed | `research_fast` · `research_deep` · `call` · `memory_write` · `glossary_lookup` (C13) |
| `status` | text, indexed | `queued` · `running` · `done` · `failed` |
| `created_by` | text | Component name |
| `user_id` | text, FK users | |
| `case_id` | text, null | |
| `payload` | jsonb | The job payload contract |
| `result` | jsonb, null | R1 / R2 / P3 / … |
| `error` | text, null | |
| `created_at`, `started_at`, `finished_at` | timestamptz | |

### `events` — writer: every component (append-only)
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `event_` |
| `created_at` | timestamptz, indexed | |
| `type` | text, indexed | Dotted name (C14) |
| `source` | text | Component name |
| `user_id` | text, FK users, indexed | **Added to the envelope**, see [Resolutions](#resolutions) |
| `case_id`, `call_id`, `job_id` | text, null | |
| `summary_en` | text | Never contains fact or document content (C27) |
| `data` | jsonb | Template vars and IDs |

## Contracts (`backend/app/contracts/`)

One module per concern. Each model validates the matching example in Plan.md.

| Module | Models |
|---|---|
| `common.py` | ID and enum types: `Language`, `JobType`, `JobStatus`, `VerificationStatus`, `FactSource`, `FactStatus`, `Sensitivity`, `CallState`, `CallOutcome`, `QuestionStatus`, `Component` |
| `jobs.py` | `ResearchFastJob` (H1), `ResearchDeepJob`, `CallJob` (H2), `MemoryWriteJob`, `GlossaryLookupJob`, `ProposedFact` |
| `results.py` | `FastResult` (R1, with `Appointment`, `ChecklistItem`, `KeyFact`), `DeepResult` (R2, with `Verification`), `CallReport` (P3) |
| `ask_user.py` | `AskUserRequest` (P1), `AskUserReply` |
| `events.py` | `Event` envelope, `EventType` (every type in Plan.md's list) |
| `brief.py` | `CaseBrief`: a placeholder `dict` until persons 3 and 4 define it |

## Resolutions

Mechanical gaps Plan.md left open. None changes behavior or ownership.

1. **Who inserts the case row.** H1 carries a `case_id` minted by the orchestrator, but `cases` is research's table. The orchestrator mints the ID; research inserts the row when it picks up the job. So `documents` doesn't reference cases; `cases.document_ids` points the other way.
2. **Where files live.** With one hosted database, a file saved on one laptop is invisible to everyone else. Media bytes go in the `media` table: a handful of photos and voice notes is small, and nobody runs a file server.
3. **`user_id` on events.** The feed is per user, and memory and delete events have no case. Adding `user_id` to the C14 envelope is additive; it's the only contract change here.
4. **Enums as text.** Adding an event type or call state shouldn't need a schema change.

## Not in this spec

- DB helpers (read/write functions, `resolve_ref`, delete helper, case progress): next spec.
- Dashboard API and screens: later spec.
- The case brief model: persons 3 and 4.
