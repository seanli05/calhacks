# Integrating the research agent: runbook

This runbook brings the research agent (person 3, branch `research_agent`) onto `main`. Two Claude sessions run it end to end without stopping for questions:
- **Step 1** runs in person 1's session: contracts, data layer, dashboard, Plan.md.
- **Step 2** runs in person 3's session: moving the research code and wiring it to the real database.

Every decision is already made. If something comes up that this doc doesn't cover, follow "When to stop" below.

**Prompt for step 1 (person 1's session):**
> Read `docs/research-integration.md` and carry out step 1 end to end, including the gate and the merge. Update the status table as you go.

**Prompt for step 2 (person 3's session):**
> Read `CLAUDE.md`, `backend/AGENTS.md`, `docs/data-layer-guide.md`, `docs/dashboard-AGENTS.md` (person 3), then `docs/research-integration.md`. Carry out step 2 end to end, including the end-to-end check, the gate and the merge. Update the status table as you go.

## Status

Each step updates its row when it starts and when it finishes, and pushes that change to `main` right away. The other agent reads this table from `origin/main` to know where things are.

| Step | Owner | State | Commit on `main` | Notes |
|---|---|---|---|---|
| 1. Contracts, data layer, dashboard, Plan.md | person 1's session | in progress: code done, gate blocked | | Branch `chris/research-contracts` (pushed). ruff, the non-DB tests (508) and `npm run build` pass. **Blocked:** the DB tests and the seed check need the `research-int-p1` Neon branch, which person 1 creates (see "Before anyone starts"). Step 2 can start 2b–2e against this branch's contracts now. Small fixes in other packages: `orchestrator/letter_result.py` (date-only appointment; `needs_user_input` sends nothing yet), `orchestrator/tools.py` (only ref'd facts are "identifiers"), `relay/templates.py` (new `letter.appointment_date`), `dev/fake_research.py` (skips value facts and missing locations) |
| 2. Move and wire the research agent | person 3's session | in progress | | Preparing 2b–2e on `research/integrate`; waiting for step 1. No `research-int-p3` URL yet (needed for the gate and the end-to-end check) |
| 3. Hand-offs sent | person 1 | not started | | |

## Before anyone starts (humans, about 5 minutes)

1. **A Neon branch per agent.** The person who owns the Neon project (person 1) creates them from the shared database. In a terminal logged in to Neon (`npx neonctl auth`):
   ```bash
   npx neonctl branches create --name research-int-p1   # for step 1
   npx neonctl branches create --name research-int-p3   # for step 2
   npx neonctl connection-string research-int-p3
   ```
   Send person 3 their URL privately, never through git. Each person puts their URL in their own repo-root `.env.local` as `TEST_DATABASE_URL`. The end-to-end check also points `DATABASE_URL` and `DATABASE_URL_UNPOOLED` at it. **No agent ever uses the shared database.**
2. **Person 3's `.env`** has `ANTHROPIC_API_KEY`. The end-to-end check makes real model calls and fetches from the web, at a cost of a few cents.

## Decisions (final)

1. **The contracts adopt research's models** for every row marked `yes` or `nice` in the table below. Their `CaseBrief` becomes the contract. Sensitivity stays `normal` / `sensitive`.
2. **`needs_user_input` is in.** This integration adds the contract, the new `needs_answer` stage, and the research side. Person 2 builds the orchestrator side after the merge (the prompt is under "Hand-offs"). Until then the orchestrator must not crash on it (step 1).
3. **`research_question` is in.** This integration adds the contracts, the job type, Plan.md entry C38, the worker, and feed templates. Person 2 wires the orchestrator side after the merge.
4. **Signals travel in the deep job.** `ResearchDeepJob` gains `signals` and `call_purpose`. There's no schema change and no reset.
5. **The demo dials the mock line, decided on the phone side.**
   - Research saves the real official number.
   - When `DEMO_DIAL_NUMBER` is set, `reads.official_dial_number` returns it instead, and only for a case that passes the same verified check.
   - This is recorded in Plan.md as C40, a demo exception to rule 2.
6. **The code is copied, not rebased.** Step 2 starts a fresh branch from `main` and copies person 3's files in. The `research_agent` branch merged an old `main`, and replaying its history would conflict with tonight's work.
7. **The research worker** starts with the app when `RESEARCH_WORKER=true` (the default) and `ANTHROPIC_API_KEY` is set. Set it to `false` to run the backend without research.
8. **`research.search`, `research.fetch` and `research.check` are kept out of the feed.** They're logged for debugging and fire many times per check.
9. **The agents merge to `main` themselves**, each after its own gate passes.

## Ground rules for both agents

- **Never touch the shared database:** no reset, no tests against it, no running the app against it. Use only your Neon branch.
- **Commits:** one short imperative line each, with **no `Co-Authored-By` or other AI attribution** (CLAUDE.md). Commit after each logical piece.
- **Another person's package:** if a change breaks a caller in someone else's package, make the **smallest fix that keeps today's behavior**, and list it under "Notes" in the status table so that person hears about it. Don't add features there.
- **Before merging:** `git pull --rebase origin main`, run the gate, then `git push origin HEAD:main`. If the push is rejected, pull, rerun the gate, and push again.
- **Secrets:** never log or commit secrets, letter contents, or real phone numbers. Research's `LeakGuard` must keep running on everything it writes.

### When to stop

Stop, write the reason in the status table's "Notes", push it, and report to your human, if:
- a product rule in CLAUDE.md would have to bend, other than the C40 exception;
- the gate fails twice for the same reason after a real fix attempt;
- a change would alter the shape of a contract that other components already write (beyond the rows here);
- you'd need the shared database, someone else's credentials, or a design decision this doc doesn't cover.

## Where research differs from the contracts

The record of each mismatch, with person 3's answers from Oct 24. Line numbers are on branch `research_agent`.

| # | Mismatch | Research code | Contract on `main` | Needed? |
|---|---|---|---|---|
| 1 | R1 status `needs_user_input` (+ `question_en`) | `research/models.py:25`, `:94` | `backend/app/contracts/common.py:77` (`FastResultStatus`), `results.py:44` (`FastResult`) | (kept; see "The `needs_user_input` flow") |
| 2 | R1 `key_dates` | `research/models.py:98` | `backend/app/contracts/results.py:44` | **yes**: immigration notices often have no deadline, only an interview or biometrics date. Built at `research/fast_pass.py:290`, and the explanation depends on it |
| 3 | `KeyFact`: `value` or `ref` (ref optional), plus `quote` and `page`; no `citation` | `research/models.py:49`–`56` | `backend/app/contracts/results.py:24`–`27` (ref and citation required) | **yes**: public facts like the form ID have no sensitive value, so a required ref is wrong. The quote is how facts stay grounded in the letter |
| 4 | `Appointment.time` optional | `research/models.py:71` | `backend/app/contracts/results.py:32` (required) | **yes**: many letters give a date with no time; a required field pushes the model to invent one |
| 5 | `Appointment.location_ref` optional | `research/models.py:72` | `backend/app/contracts/results.py:34` (required) | **yes**: some appointment notices have no location; a required field means making up a ref |
| 6 | `ProposedFact.sensitivity` | `research/models.py:85` | `backend/app/contracts/jobs.py:20` | **yes** (safety): facts research marks sensitive reach the memory writer marked, so they're held until the user consents |
| 7 | Sensitivity value `high` | `research/models.py:23` | `backend/app/contracts/common.py:48` (`normal` / `sensitive`) | Fix on research's side: rename to `sensitive` |
| 8 | `Verification.signals` | `research/models.py:155` | `backend/app/contracts/results.py:65` | **yes**: `research/brief.py:96` builds the brief from it, and it explains why a letter is `unknown` rather than `suspicious` |
| 9 | R2 `official_phone_purpose` | `research/models.py:170` | `backend/app/contracts/results.py:75` (`DeepResult`) | **nice**: lets the brief say which line is being called; the agent works without it |
| 10 | R2 `alternative_contacts` | `research/models.py:171` | `backend/app/contracts/results.py:75` | **yes**: the housing and medical letter types depend on it. A private landlord letter or an unverified letter gets verified alternatives instead of a dead end (`research/deep_verify.py:820`) |
| 11 | R2 `brief_id` optional (no brief for a suspicious letter) | `research/models.py:173` | `backend/app/contracts/results.py:81` (required) | Contract changes: research is right |
| 12 | Deep job `answers` | `research/models.py:238`, read at `research/jobs.py:227` | `backend/app/contracts/jobs.py:36` (`ResearchDeepJob`) | **no**: nothing ever sends it. Research deletes the one fallback that reads it (`research/jobs.py:227`); the county comes from the letter or the profile |
| 13 | Deep pass needs `signals` and `call_purpose` from the fast pass | `research/sim/store.py:39`–`40`, `research/models.py:254`–`255` | `backend/app/db/tables.py:123` (`cases` has no columns for them) | Decided: add them to `ResearchDeepJob` |
| 14 | Proposed facts in the `memory_write` job carry `sensitivity` | `research/jobs.py:133` | `backend/app/contracts/jobs.py:59` (`MemoryWriteJob`) | Follows row 6 |
| 15 | Jobs have no `user_id` | `research/sim/store.py:43`, `:86` | `backend/app/db/jobs.py:27` (`enqueue` requires it) | Fix on research's side: pass `user_id` |
| 16 | Events have no `user_id` | `research/sim/store.py:53`, `:100`, `research/events.py:70` | `backend/app/contracts/events.py:83` (required) | Fix on research's side: pass `user_id` |
| 17 | Event types `research.fast_slow`, `fast_failed`, `deep_failed`, `search`, `fetch`, `check` | `research/events.py:17`–`25` | `backend/app/contracts/events.py:20` (`EventType`) | **yes** for `fast_failed` and `deep_failed` (the failure rules and the dashboard need them). **nice** for `fast_slow` (lets the orchestrator send a "still working" message) and `search` / `fetch` / `check` (the dashboard's live research log, and debugging) |
| 18 | `CaseBrief` model | `research/models.py` (`CaseBrief`) | `backend/app/contracts/brief.py` (a plain dict) | Not a violation; becomes the contract (decision 1) |
| 19 | New job `research_question` (chat questions): `ResearchQuestionPayload`, result `QuestionAnswer` / `QuestionSource` / `QuestionStatus`, events `research.question_started` / `question_done` / `question_failed` | `research/models.py:241`–`280`, `research/events.py:24`–`26`, `research/sim/store.py:18` | Not in `backend/app/contracts/common.py:13` (`JobType`), `jobs.py`, `results.py` or `events.py:20` (`EventType`) | **yes** for the chat-question feature person 2 agreed to; added after this table was written. A new contract, so it needs persons 1 and 2. A question sent with `case_id` reads only the case's R1 and refs |
| 20 | Structure: code in top-level `research/`, `research/models.py` duplicates contract models, the simulated `Store` and `ResearchSettings` | `research/`, `research/sim/store.py`, `research/sim/settings.py` | `backend/app/research/`, `app.contracts`, `app.db`, `app.settings` | **no** (the agent doesn't need any of it); step 2 removes it when the code moves |

## Step 1: person 1's session

Work on the branch `chris/research-contracts` from `main`. Set the status row to `in progress`.

**1a. Contracts (`backend/app/contracts/`).** Take field names, types and validators from `research/models.py` on `origin/research_agent` (`git show origin/research_agent:research/models.py`), and put each in the contract module that already owns that kind of thing:
- `common.py`:
  - `FastResultStatus` gains `needs_user_input`.
  - `JobType` gains `research_question`.
  - New `KeyDateType`, `SignalState` and `QuestionStatus` enums.
- `results.py`:
  - `FastResult` gains `question_en` and `key_dates` (new `KeyDate`), and their `R1` status validator.
  - `KeyFact` becomes theirs: exactly one of `value` or `ref`, plus `quote` and `page`; no `citation`.
  - In `Appointment`, `time` and `location_ref` become optional. Keep this contract's stricter time pattern.
  - `Verification` gains `signals` (new `SignalResult`).
  - `DeepResult` gains `official_phone_purpose` and `alternative_contacts` (new `AlternativeContact`). `brief_id` becomes optional, and their `call_recommended` validator comes too.
  - New `QuestionSource` and `QuestionAnswer`, with its validator.
- `jobs.py`:
  - `ProposedFact` gains `sensitivity: Sensitivity = NORMAL`.
  - `ResearchDeepJob` gains `signals: LegitimacySignals` and `call_purpose: str | None`. `LegitimacySignals` and `LetterPhone` move into the contracts.
  - New `ResearchQuestionJob` (their `ResearchQuestionPayload`), added to the `JobPayload` union.
- `brief.py`: `CaseBrief` becomes their model (with `RepQuestion` and `REQUIRED_MUST_NOT_DO`). It includes `brief_id` and `case_id`.
- `events.py`: `EventType` gains these, and `USER_MESSAGING_EVENTS` doesn't change:
  - `research.fast_slow`, `research.fast_failed`, `research.deep_failed`;
  - `research.search`, `research.fetch`, `research.check`;
  - `research.needs_user_input`;
  - `research.question_started`, `research.question_done`, `research.question_failed`.
- Export everything new from `app/contracts/__init__.py`.
- Update `backend/tests/fixtures/contracts/*.json`, and add `research_question_job.json` and `question_answer.json`.

**1b. Data layer (`backend/app/db/`).**
- `writes.research.create_case` is idempotent: it returns the existing row when the case ID already exists.
- `writes.research.save_brief(case_id, brief, handoff_note, brief_id=None)` uses the given `brief_id` when there is one. The brief's own `brief_id` and the row's ID must match.
- `progress.py`: a new `CaseStage.NEEDS_ANSWER`, which applies when the latest R1 is `needs_user_input` and no newer fast job is running. Add it to the stage table in `docs/data-layer-guide.md`.
- `settings.py`: `demo_dial_number: str = ""` (with an E.164 check when set), and `research_worker: bool = True`. Add both to `.env.example`, with `DEMO_DIAL_NUMBER` defaulting to the mock agency line.
- `reads.official_dial_number`: keep every existing check. When `demo_dial_number` is set, return it instead of the verified number, and add a comment pointing to C40.
- `reset.py` and `seed_story.py`: the seed's key facts use the new `KeyFact` shape, and the seed's brief validates against the new `CaseBrief`.
- Tests:
  - `create_case` is idempotent;
  - `save_brief` with a `brief_id`;
  - `needs_answer` in the stage tests;
  - `official_dial_number` with and without `DEMO_DIAL_NUMBER`, and still refusing an unverified case either way.

**1c. Callers in other packages (smallest fixes that keep today's behavior; list them in Notes).**
- `app/dev/fake_research.py`: collect refs only from key facts that have a `ref`. Its brief must validate against the new `CaseBrief`.
- `app/orchestrator/letter_result.py:55`: when there's no appointment time, leave the time out.
- The orchestrator's R1 handling: a `needs_user_input` R1 gets the existing generic "still working on it" reply, or nothing, but never an exception.
- `app/phone/`: the brief is still read as a dict (`model_dump`). Confirm `menu.py` and `adapters.py` still read their keys.
- Run the whole test suite; it shows any other caller.

**1d. Dashboard API and pages.**
- `app/api/case_views.py`: an appointment with no `location_ref` skips the lookup. `Appointment.time` is optional in `app/api/models.py` and `dashboard/lib/api/types.ts`. The dashboard shows the date alone when there's no time.
- `feed_templates.py`, with English and Spanish:
  - `research.fast_slow`: "Still reading your letter"
  - `research.fast_failed` / `research.deep_failed`: "We couldn't finish reading your letter"
  - `research.needs_user_input`: "We need one answer from you"
  - `research.question_started` / `research.question_done`: "Looking up your question" / "We found an answer to your question"
  - `research.question_failed`: "We couldn't find an official answer"
  - Hide `research.search`, `fetch` and `check` from the feed (decision 8).
- The `needs_answer` stage:
  - `CaseStage` in `types.ts`;
  - `lib/stage.ts`: it sits on the tracker's "Letter" step and is a warning;
  - the hero copy in `lib/i18n/strings/{en,es}/case.ts`: "We need one answer from you" / "Necesitamos una respuesta suya";
  - a fixture step is optional.

**1e. Plan.md** (person 1 owns this change, and these decisions are the team's record):
- **C38**: the `research_question` job: the orchestrator queues it with an English question; research answers only from official sources, with quotes, or declines (legal advice, the asylum claim, out of scope); the orchestrator relays the answer. Add a row to the job table.
- **C39**: R1 `needs_user_input` with `question_en` (pages from different letters). The orchestrator asks the question, then queues `research_fast` again for the same case with the reply as `user_note_en`.
- **C40**: the demo dial override (decision 5), as an explicit exception to rule 2 that holds only while `DEMO_DIAL_NUMBER` is set.
- In the handoff sections, write R1, R2 and the brief with their new fields.

**1f. Gate, then merge.**
- `ruff format . && ruff check --fix . && pytest` passes, with `TEST_DATABASE_URL` set to `research-int-p1`.
- `cd dashboard && npm run build` passes.
- `python -m app.db.reset --yes` runs against `research-int-p1` (with `DATABASE_URL_UNPOOLED` pointed at it), and `/api/cases/{id}` returns 200 for the seeded case.
- Merge (ground rules). Set the status row to `done` with the commit.

## Step 2: person 3's session

**2a. Wait for step 1.** Step 2's code depends on step 1's contracts. While step 1's status row isn't `done`, prepare 2b–2e on the branch, then rebase it on `main` once step 1 is merged. Check `git fetch && git show origin/main:docs/research-integration.md` for the status.

**2b. Bring the code across** on the branch `research/integrate` from `main`. Set the status row to `in progress`.
```bash
git checkout -b research/integrate origin/main
git checkout origin/research_agent -- research tests/research fixtures
git mv research/* backend/app/research/        # keep backend/app/research/__init__.py's owner docstring
git mv tests/research backend/tests/research
git mv fixtures backend/tests/fixtures/research
```
- Fix the imports from `research.` to `app.research.`.
- Paths that pointed at `fixtures/...` now resolve from the module's own location (`Path(__file__)`), never from the working directory.
- Don't touch the other files on `research_agent` (Plan.md, CLAUDE.md, README.md, `pyproject.toml`, `.env.example`). `main` has newer copies.
- Copy only the research lines from its `requirements.txt` (pillow, phonenumbers, tldextract, beautifulsoup4, pypdf, pinned as they are).
- `pyproject.toml` needs no change, since the tests now live under `backend/tests`.

**2c. Use the contracts.**
- Delete from `research/models.py` everything that step 1 moved into `app.contracts`, and import those from `app.contracts`.
- Keep the models internal to research there: `SensitiveValue`, `FastPassOutput`, `DeepFindings` and the other pass outputs.
- Rename sensitivity `high` to `sensitive` everywhere.
- Delete `ResearchDeepPayload.answers` and its fallback in `jobs.py` (row 12).
- When the fast pass queues the deep pass, put `signals` and `call_purpose` in the `ResearchDeepJob`. The deep pass reads them from the payload, not from a case record.

**2d. Use the real database.**
- In `research/jobs.py`, replace every `Store` call using the table below. Then delete `research/sim/`, after moving anything the tests still use as a fake into `backend/tests/research/`.
- Every job and event carries `user_id`, taken from the job payload.

| `Store` call | Real helper |
|---|---|
| `get_document` | `reads.get_document(id)`. Its `pages` is `[{"media_id", "added_at"}]`; for each page, `reads.get_media(media_id)` gives `.data` and `.content_type` |
| `insert_case` | `writes.research.create_case(case_id, user_id, document_ids)` (idempotent), then `save_fast_result(case_id, r1)` |
| `get_case` | Not needed: the deep pass reads `signals` and `call_purpose` from its job. R1 is in `reads.get_case(case_id).fast_result` if needed |
| `insert_case_ref` | `writes.research.put_ref(case_id, field, value)` returns nothing; the placeholder is `<ref:field>` |
| `insert_verification` | `writes.research.save_verification(case_id, verification)` |
| `insert_case_brief` | `writes.research.save_brief(case_id, brief.model_dump(mode="json"), handoff_note, brief_id=brief.brief_id)` |
| `create_job` | `jobs.enqueue(<contract model>, Component.RESEARCH_AGENT, user_id, case_id)` |
| `update_job` | `jobs.claim_next` sets `running`; finish with `jobs.finish(job.id, result_model)` or `jobs.fail(job.id, reason)` |
| `add_event` | `events.append_event(Event(event_id=new_id("event"), created_at=utcnow(), type=EventType..., source=Component.RESEARCH_AGENT, user_id=..., case_id=..., job_id=..., summary_en=..., data=...))` |

- The `data` fields the dashboard reads are in `docs/dashboard-AGENTS.md`. For example, `verification.verified` carries `source`, and the official source comes first in `evidence`.
- The brief has `call_goal_en` and `questions_to_ask`.

**2e. Settings and the worker.**
- Replace `ResearchSettings` with `app.settings.get_settings()` (`anthropic_api_key`, `model_default`, `model_deep`). If research needs another setting, add it to `app/settings.py` and `.env.example`, and list it in Notes.
- New `backend/app/research/worker.py`: one background task that polls `jobs.claim_next` for `research_fast`, `research_deep` and `research_question` about once a second, and runs each job in its own task. A failure in one job is logged with the case and job IDs, and fails only that job.
- Start it from the `lifespan` in `backend/app/main.py`, when `settings.research_worker` is true and `anthropic_api_key` is set. Stop it cleanly on shutdown.
- Keep `research/cli.py` and `research/eval_harness.py` working as dev tools (`python -m app.research.cli`). Their replay mode runs from `backend/tests/fixtures/research/web` with no network.

**2f. End-to-end check: `backend/tests/research/test_e2e_live.py`.** It runs only when `RESEARCH_E2E=1` and `TEST_DATABASE_URL` are set; otherwise it's skipped. It's a dev-only test, so it may write as the orchestrator to create its input.
1. Rebuild the tables on the test branch the same way `test_db_helpers.py` does.
2. Create a user (`writes.orchestrator`), the media for `backend/tests/fixtures/research/letters/i797c_asylum_interview/page_1.png`, and a document. Queue `ResearchFastJob` with a new `case_id` and `user_language="es"`.
3. Start the worker, then wait up to 4 minutes for the deep job to reach `done`.
4. Assert:
   - `case_progress` is `awaiting_consent` (verified);
   - R1 has `doc_type` and an `explanation_en`, and its key facts follow the new shape;
   - the case has refs and a brief with `call_goal_en`, `questions_to_ask` and the required `must_not_do`;
   - events for `research.fast_done`, `research.deep_done` and `verification.verified` (with `source`), each with `user_id`;
   - nothing sensitive in any event, job result or brief: the receipt number and A-Number from `expected.json` don't appear;
   - with `DEMO_DIAL_NUMBER` set, `reads.official_dial_number(case_id)` returns it. Without it, it returns the verified number.
5. Queue a `ResearchQuestionJob` ("What should I bring to my asylum interview?", with the `case_id`). Assert a `QuestionAnswer` with status `answered` and at least one official source, or a valid decline status.
6. Call the dashboard API in the same process with `httpx.ASGITransport`. `GET /api/cases/{case_id}?lang=es` returns 200 with an `issuer`, a `verification` whose evidence has a source first, masked refs and the brief's questions. `GET /api/users/{user_id}/feed?lang=es` has no line in English except hidden types.

**2g. Gate, then merge.**
- `ruff format . && ruff check --fix . && pytest` passes, with `TEST_DATABASE_URL` set to `research-int-p3`. All of research's moved tests pass.
- `RESEARCH_E2E=1 pytest backend/tests/research/test_e2e_live.py` passes.
- `README.md` has `RESEARCH_WORKER`, `DEMO_DIAL_NUMBER`, and how to run the research CLI and the end-to-end test. In `backend/AGENTS.md`, the `research/` row is updated to "Done" with a short summary, and this doc's status row is set.
- Merge (ground rules). Set the status row to `done` with the commit.
- Delete nothing on `origin/research_agent`; person 3 retires it.

## Hand-offs after both steps (step 3, person 1)

Send these, then set row 3 to `done`.

**Person 2**, prompt for their agent:
> Read `docs/research-integration.md` (decisions 2 and 3, C38, C39 in Plan.md). In `orchestrator/`:
> 1. On an R1 with status `needs_user_input`, ask the user `question_en` in their language. On their reply, queue `research_fast` again for the same `case_id` with the reply in English as `user_note_en`, the same pattern as "same letter or new?".
> 2. Add a tool to the Claude turn that queues `ResearchQuestionJob` for a factual question about the user's letter or process. Relay the `QuestionAnswer` with its sources, or explain the decline.
> 3. Optionally, offer the R2 `alternative_contacts` when a letter isn't verified.
>
> Stay in your packages. Test with fakes. Merge as usual.

**Person 4:** the brief is now the `CaseBrief` model in `app.contracts.brief`, stored as its JSON. The phone agent can keep reading it as a dict or validate it with the model. `official_dial_number` returns `DEMO_DIAL_NUMBER` while it's set (C40).

**Everyone:**
- research runs for real once `ANTHROPIC_API_KEY` is set;
- don't call `/dev/fake-research` while the worker runs;
- person 1 resets the shared database before the next rehearsal.

## Done when

All three status rows are `done`, and a photo of the demo letter sent on WhatsApp (shared database, after the reset) produces, in order:
- the explanation;
- the verified verdict;
- the consent question.

The dashboard's case view shows the letter panel filled in.
