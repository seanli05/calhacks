# Task B: shared contracts

You are implementing `backend/app/contracts/`: the Pydantic models every component imports for job payloads, results, ask_user, and events. Another agent (task A) builds the database layer in parallel. This doc is everything you need.

## Read first
1. [CLAUDE.md](../../CLAUDE.md): product rules and engineering conventions. Follow them.
2. [Plan.md](../../Plan.md) → **Handoffs** (H1, R1, R2, H2, P1, P2, P3, other job payloads, events, shared formats). These example payloads are the source of truth for field names and shapes.
3. [data-layer-schema.md](data-layer-schema.md) → **Conventions**, **Contracts**, and **Resolutions** (resolution 3 adds `user_id` to the event envelope).

If Plan.md and this doc disagree, Plan.md wins; stop and tell the user rather than guessing.

## Scope
- **Edit only:** `backend/app/contracts/` and `backend/tests/test_contracts.py`, plus fixtures under `backend/tests/fixtures/contracts/`.
- **Don't touch:** `backend/app/db/` (task A), `Plan.md`, other components' packages.
- No new dependencies (Pydantic 2 is already pinned).

## Order of work
1. **`common.py` first, merged to `main` immediately.** Task A imports these enums. Commit it alone, then fast-forward `main` and push (`gh` isn't installed; the team merges with `git merge --ff-only`). Pull first.
2. The rest on branch `chris/contracts`, committing after each module. Leave it unmerged for the user to review.

## `common.py`
`StrEnum`s with exactly these values (they're stored as text in the DB):

| Enum | Values |
|---|---|
| `JobType` | `research_fast`, `research_deep`, `call`, `memory_write`, `glossary_lookup` |
| `JobStatus` | `queued`, `running`, `done`, `failed` |
| `VerificationStatus` | `pending`, `verified`, `suspicious`, `unknown` |
| `FactSource` | `user_said`, `from_document`, `from_call`, `inferred` |
| `FactStatus` | `active`, `pending_consent`, `superseded` |
| `Sensitivity` | `normal`, `sensitive` |
| `CallState` | `dialing`, `menu`, `hold`, `human_detected`, `bridging`, `connected`, `wrap_up`, `ended` |
| `CallOutcome` | `resolved`, `partial`, `failed`, `user_unreachable` |
| `QuestionStatus` | `open`, `answered`, `timed_out` |
| `FastResultStatus` | `ok`, `needs_better_image` |
| `Urgency` | `low`, `medium`, `high` |
| `ChecklistKind` | `who_must_come`, `bring`, `deadline` |
| `MessageDirection` | `in`, `out` |
| `MessageSender` | `user`, `orchestrator`, `relay` |
| `TrustLevel` | `official`, `community`, `machine` |
| `Component` | `orchestrator`, `research_agent`, `phone_agent`, `relay`, `memory_writer`, `translation`, `glossary_worker`, `dashboard`, `delete_helper` |

Annotated string types (use `Annotated[str, StringConstraints(...)]`):
- `LanguageCode`: two lowercase letters (ISO 639-1).
- `PhoneE164`: `^\+[1-9]\d{6,14}$`.
- `RefPlaceholder`: `^<ref:[a-z_]+>$`.
- ID aliases, one per prefix in data-layer-schema.md (`UserId`, `CaseId`, `DocumentId`, `BriefId`, `CallId`, `JobId`, `QuestionId`, `MessageId`, `FactId`, `EventId`, `TranscriptId`, `VerificationId`, `MediaId`): plain `str` aliases, **no pattern**, since Plan.md's examples (`case_123`) are shorter than real IDs.

A shared base model, `Contract`, with `model_config = ConfigDict(extra="forbid")` so a misspelled field fails loudly. Every contract inherits it.

## Other modules
Model names and fields follow the Plan.md examples exactly; types:

- **`jobs.py`:** `ProposedFact` (`fact`, `source: FactSource`); `ResearchFastJob` (H1), `ResearchDeepJob`, `CallJob` (H2), `MemoryWriteJob`, `GlossaryLookupJob`. Each has `job: Literal["<type>"]` matching `JobType`, and `JobPayload` is a discriminated union on `job`. In `CallJob`, `consent_at` is a `datetime`, `max_hold_minutes` an `int`, `dial_number_source: Literal["official_phone"]`. No `user_phone` and no `call_id` (C6, C7).
- **`results.py`:** `KeyFact` (`field`, `ref: RefPlaceholder`, `citation`), `Appointment` (`date: date`, `time: str` "HH:MM", `location_ref: RefPlaceholder`, `citation`), `ChecklistItem` (`kind: ChecklistKind`, `item`, `citation`), `FastResult` (R1). When `status` is `needs_better_image`, every field except `case_id`, `status`, `image_issue` may be empty/null, so make them optional with defaults. `verification` in R1 is a `VerificationStatus`. `Verification` (R2 inner object: `letter_phone_matches: bool | None`, `official_phone: PhoneE164 | None`, `evidence: list[str]`, `red_flags: list[str]`), `DeepResult` (R2), `CallReport` (P3: `outcome: CallOutcome`, `new_deadlines: list[date]`, `rep_name`/`reference_number` optional).
- **`ask_user.py`:** `AskUserRequest` (P1), `AskUserReply` (`question_id`, `choice: int`, `ge=1`). Validate that `default_option` is between 1 and `len(options_en)` (1-based, C5).
- **`events.py`:** `EventType` `StrEnum` with every type in Plan.md → Events (including `case.closed`, `call.ask_user_late_reply`, and the four delete types). `USER_MESSAGING_EVENTS`: frozenset of the four P2 types. `Event` envelope: `event_id`, `created_at: datetime`, `type: EventType`, `source: Component`, `user_id`, optional `case_id`/`call_id`/`job_id`, `summary_en`, `data: dict[str, Any]`.
- **`brief.py`:** `CaseBrief = dict[str, Any]` with a docstring saying persons 3 and 4 define it.
- **`__init__.py`:** re-export the public names so callers write `from app.contracts import CallJob`.

## Tests (`backend/tests/test_contracts.py`)
- Copy every example payload from Plan.md → Handoffs into `backend/tests/fixtures/contracts/<name>.json` verbatim, and test that each validates. Two exceptions, fixed in the fixture and noted in a comment: P3's `outcome` is written as `"resolved | partial | failed | user_unreachable"` (use `"resolved"`); add `user_id` to the event example (resolution 3).
- Round trip: `model_validate(model.model_dump(mode="json"))` equals the original.
- Rejections: unknown field, bad language code, `default_option` 0 or past the end, a `CallJob` carrying `user_phone`.
- `JobPayload` picks the right model from `job`.
- These fixtures double as fake inputs other components can reuse; keep them valid.

## Done when
- `ruff format . && ruff check --fix . && pytest` passes from the repo root.
- `common.py` is on `main`; everything else is on `chris/contracts`, unmerged, for the user to review.
- You report: what you built, any place you had to interpret Plan.md, and test output.

## Setup notes
- Python 3.12 isn't installed on this machine; 3.13 works (`python -m venv .venv`, then `pip install -r requirements-dev.txt`; installing `pipecat-ai` is slow and not needed for this task, so `pip install pydantic==2.14.1 pytest==9.1.1 pytest-asyncio==1.4.0 ruff==0.17.2 fastapi==0.162.0 httpx==0.28.1 pydantic-settings==2.16.1 sqlmodel==0.0.48 asyncpg==0.32.0 greenlet==3.5.6` is enough).
- Commits: one short imperative line, no AI attribution, commit often (CLAUDE.md).
