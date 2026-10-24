# Integrating the research agent

How the research agent on branch `research_agent` (person 3) joins `main`. It covers where research sits in the system, the design decisions already made, what person 1 changes first, and the steps for person 3's agent.

Read first:
1. [CLAUDE.md](../CLAUDE.md) and [backend/AGENTS.md](../backend/AGENTS.md).
2. [data-layer-guide.md](data-layer-guide.md), especially **Research agent** under Recipes.
3. [dashboard-AGENTS.md](dashboard-AGENTS.md), the person 3 section.

[Plan.md](../Plan.md) is the source of truth: H1, R1, R2, the case brief, and the failure rules.

## Where research sits

Research never talks to another component directly. It claims jobs from Postgres and writes its own tables. Other components read what it wrote.

```
User sends a letter photo
  → orchestrator saves it (`documents`) and queues `research_fast` (H1)          [on main: orchestrator/letters.py]
  → research claims the job and reads the pages
      writes `cases` + R1, and `case_refs` for every sensitive value
      finishes the job with R1, then queues `memory_write` (proposed facts) and `research_deep`
  → orchestrator sees R1 done → explains the letter on WhatsApp
  → research deep pass: web lookups, verification
      writes `verifications` (verdict, official phone, evidence) and `case_briefs` (the call plan)
      finishes the job with R2
  → orchestrator sees R2 → asks the user for consent to call
  → phone agent reads straight from the database:
      number to dial ← reads.official_dial_number(case_id) ← the verification
      call plan      ← reads.get_brief(brief_id), with brief_id from the call job
  → dashboard reads everything research wrote
```

- **Memory:** research never writes `facts` or `profile`. It queues `memory_write` with *proposed* facts, and the memory writer (person 2) decides what to keep (Plan.md → job table). Research may *read* the profile, for example the county as a fallback.
- **Sensitive values** (receipt number, A-Number, date of birth, interview location) go in `case_refs` through `put_ref` and travel only as `<ref:name>`. This includes R1, R2, the brief, events and logs.

## Decisions (person 1, Oct 24)

1. **The contracts adopt research's richer models**, limited to the fields person 3 marks as needed in the table below. Those shapes go into `app.contracts`, and their `CaseBrief` becomes the contract. The fields are mostly additive, so existing callers keep working. `DeepResult.brief_id` becomes optional, because a suspicious letter gets no brief. One exception: sensitivity stays `normal` / `sensitive` (the value `facts` already stores), so research renames `high` to `sensitive`.
2. **`needs_user_input` stays.** Research uses it when the photos come from different letters: the orchestrator groups photos sent within 6 seconds into one letter, and only research can see that they don't belong together. It needs a small new flow, described in "The `needs_user_input` flow" below.
3. **Signals travel in the deep job.** The fast pass's `signals` (letterhead, phones, URLs, form IDs; no personal data) and `call_purpose` go into `ResearchDeepJob` when the fast pass queues the deep pass. There's no schema change and no reset.
4. **The demo dials the mock line, decided on the phone side.** Research saves the real official number it finds, so the dashboard shows the true verification. When `DEMO_DIAL_NUMBER` is set, `reads.official_dial_number` returns that number instead, and only for a case that passes the same verified check. The phone agent still has exactly one way to get a number, and an unverified case still gets none. **Team note:** this means the number dialed is no longer the verified number itself. It's a deliberate demo exception to rule 2, so leave `DEMO_DIAL_NUMBER` unset only once the agent should call real agencies.

## Where research differs from the contracts today

Each row is something `app.contracts` would reject once research writes through the real helpers. The contracts forbid unknown fields, so it fails loudly. Locations are on branch `research_agent` (top-level `research/`) and on `main`, as of Oct 24.

**Person 3: fill in "Needed?"** with `yes` (the agent depends on it), `nice` (useful, but the agent works without it), or `no` (drop it on your side). Person 1 adds to the contracts only the `yes` and `nice` rows. Rows marked "fix on research's side" aren't a choice.

Person 3's answers (Oct 24) are filled in below. `yes` means the agent breaks or gets less safe without it.

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

Not violations: `ResearchFastJob` matches. The safety handling also matches Plan.md: refs, `LeakGuard`, the required `must_not_do`, and never using the letter's phone number.

## Step 1: person 1's prep (lands before the integration)

These touch person 1's code, so person 1 makes them in one PR, **after person 3 fills in the table above**. The list below is the full set; drop whatever person 3 marked `no`.

**Contracts (`backend/app/contracts/`):**
- `FastResultStatus` gains `needs_user_input`, and `FastResult` gains `question_en` and `key_dates`.
- `KeyFact` becomes theirs: exactly one of `value` or `ref`, plus `quote` and `page`.
- `Appointment.time` and `location_ref` become optional.
- `ProposedFact` gains `sensitivity`.
- `Verification` gains `signals`.
- `DeepResult` gains `official_phone_purpose` and `alternative_contacts`, and `brief_id` becomes optional.
- `ResearchDeepJob` gains `signals` and `call_purpose` (not `answers`: row 12 is `no`).
- `CaseBrief` becomes their model, including the required `must_not_do`.
- `JobType` gains `research_question`, with its payload and `QuestionAnswer` result, and `EventType` gains `research.question_started`, `research.question_done` and `research.question_failed` (row 19; needs person 2's OK too).
- `EventType` gains `research.fast_slow`, `research.fast_failed`, `research.deep_failed`, `research.search`, `research.fetch`, `research.check` and `research.needs_user_input`.
- The fixtures in `backend/tests/fixtures/contracts/` are updated to match.

**Callers of those contracts:**
- `app/dev/fake_research.py` (person 2's file, with their OK): skip key facts that have no `ref`.
- `app/db/reset.py`: the seed's key facts.
- `app/api/`: an appointment without a time or location, and the new stage.

**Data layer:**
- A new `CaseStage.NEEDS_ANSWER`, computed when the latest R1 is `needs_user_input`.
- `create_case` becomes idempotent, because the `needs_user_input` flow re-runs the fast pass for the same case.
- `DEMO_DIAL_NUMBER` in settings and `.env.example`, and its use in `official_dial_number`.

**Dashboard:** strings and the tracker for `needs_answer`, plus feed templates for the new event types.

## Step 2: person 3's integration (on a branch from `main` after step 1)

1. **Move the code.** Rebase on `main`. Move top-level `research/` into `backend/app/research/`, which already exists with its owner docstring, and `tests/research/` into `backend/tests/research/`. Delete `research/sim/`, except anything the tests still use as fakes.
2. **Use the contracts.** Delete `research/models.py`'s copies of R1, R2, `Verification`, `KeyFact`, `Appointment`, `ChecklistItem`, `ProposedFact`, `CaseBrief` and the job payloads. Import them from `app.contracts` instead. Models internal to research stay, for example `FastPassOutput`, `DeepFindings`, `SensitiveValue` and `LegitimacySignals`, unless step 1 moved them into the contracts.
3. **Replace the simulated `Store` with the real helpers.** Only `research/jobs.py` uses it, so the swap stays in one file:

   | `Store` call | Real helper |
   |---|---|
   | `get_document` | `reads.get_document(id)`: `pages` is `[{"media_id", "added_at"}]`. Get the bytes and content type with `reads.get_media(media_id)` |
   | `insert_case` | `writes.research.create_case(case_id, user_id, document_ids)`, then `save_fast_result(case_id, r1)` |
   | `get_case` (deep pass) | Not needed: `signals` and `call_purpose` arrive in the `ResearchDeepJob` payload. R1 is in `reads.get_case(case_id).fast_result` if needed |
   | `insert_case_ref` | `writes.research.put_ref(case_id, field, value)` returns nothing; build the placeholder `<ref:field>` yourself |
   | `insert_verification` | `writes.research.save_verification(case_id, verification)` |
   | `insert_case_brief` | `writes.research.save_brief(case_id, brief.model_dump(mode="json"), handoff_note)` returns the row; use its `id` as `brief_id` |
   | `create_job` | `jobs.enqueue(payload_model, Component.RESEARCH_AGENT, user_id, case_id)` with a contract model, not a dict |
   | `update_job` | `jobs.claim_next` sets `running`; finish with `jobs.finish(job.id, result_model)` or `jobs.fail(job.id, reason)` |
   | `add_event` | `events.append_event(Event(...))` with **`user_id`**, which every event requires; take it from the job |

   Check the exact signatures in `backend/app/db/`, which is authoritative.
4. **Settings.** Replace `ResearchSettings` with `app.settings.get_settings()`: `anthropic_api_key`, `model_default`, `model_deep`. Ask person 1 before adding a setting.
5. **Worker.** Add `backend/app/research/worker.py`: a background task that polls `jobs.claim_next(JobType.RESEARCH_FAST)` and `RESEARCH_DEEP` about once a second and runs the handlers. Start it from the app's lifespan in `main.py` (tell person 1). There's one backend process, so no `--workers`.
6. **Fake research off.** `/dev/fake-research` claims from the same queue. Don't run it when the real worker is running; keep `DEV_ENDPOINTS=false`.
7. **What the dashboard reads.** Follow [dashboard-AGENTS.md](dashboard-AGENTS.md) → person 3:
   - the official source first in `evidence`;
   - `verification.verified` carries `source` (the domain);
   - the brief has `call_goal_en` and `questions_to_ask`;
   - `issuer` is set.

## The `needs_user_input` flow

Today research emits it in one case: the pages look like different letters, and it asks "Which letter should I look at first?" The new flow:

1. **Research:**
   - writes R1 with `status=needs_user_input` and `question_en`;
   - finishes the job;
   - doesn't queue the deep pass (it already behaves this way);
   - logs `research.needs_user_input`.
2. **Orchestrator (person 2):** on that R1, asks `question_en` in the user's language. That's free-form, so the orchestrator sends it (rule 1). When the user replies, it queues `research_fast` again for **the same `case_id`**, with the reply, in English, as `user_note_en`. This is the same pattern as "same letter or new?", which `orchestrator/photos.py` already handles.
3. **Research:** the fast pass reads `user_note_en` to pick the pages, and runs as usual from there. `create_case` is idempotent after step 1.
4. **Dashboard:** shows stage `needs_answer` ("We need one answer from you") until the second fast pass runs.

`ResearchDeepJob.answers` is dropped (row 12): nothing sends it, and research deletes its one fallback at `research/jobs.py:227`. The county comes from the letter or the profile.

Rough cost: person 1 about an hour (in step 1), person 2 about 2 hours, research about 30 minutes. The demo letter, a clean I-797C, never triggers it.

## Migration cost (to estimate)

The work each row implies, grouped by owner, for sizing the migration later. Additive changes keep existing callers working; changes to required fields also touch callers and fixtures.

**Research's side (person 3), not a choice:**
- Rename sensitivity `high` to `sensitive` (row 7).
- Pass `user_id` on every job and event (rows 15, 16).
- Delete the `answers` fallback (row 12).

**Contracts and callers (person 1, step 1):**

| Row | Change | Kind | Callers and fixtures to touch | Cost |
|---|---|---|---|---|
| 2 | `FastResult.key_dates` | additive | fixtures | |
| 3 | `KeyFact`: `value` or `ref`, `quote`, `page`; drop `citation` | breaking | `app/dev/fake_research.py`, `app/db/reset.py`, dashboard letter panel, fixtures | |
| 4, 5 | `Appointment.time` and `location_ref` optional | loosening | `app/api/`, dashboard, fixtures | |
| 6, 14 | `ProposedFact.sensitivity` | additive | memory writer (person 2) must hold `sensitive` facts | |
| 8 | `Verification.signals` | additive | fixtures | |
| 9 | `DeepResult.official_phone_purpose` (nice) | additive | fixtures | |
| 10 | `DeepResult.alternative_contacts` | additive | orchestrator relays them (person 2), fixtures | |
| 11 | `DeepResult.brief_id` optional | loosening | callers that assume a brief | |
| 13 | `ResearchDeepJob.signals`, `call_purpose` | additive | fixtures | |
| 17 | new research event types | additive | dashboard feed templates | |
| 18 | `CaseBrief` model | replaces a dict | `save_brief`, phone agent's brief reader (person 4) | |
| 19 | `research_question` job, result, events | new | orchestrator queues it and relays answers (person 2), dashboard templates | |
| 1 | `needs_user_input` flow | new | see that section: person 1 about an hour, person 2 about 2 hours, research about 30 minutes | |

**Research's integration (person 3, step 2):** move the code, switch to `app.contracts`, swap the simulated `Store` for the real helpers in `research/jobs.py`, use `app.settings`, add the worker (row 20 and step 2).

## Done when

- `ruff format . && ruff check --fix . && pytest` passes from the repo root, including the moved research tests.
- With the backend running (`DEV_ENDPOINTS=false`) on your own Neon branch, a photo of the demo letter sent on WhatsApp produces, in order:
  - the R1 explanation;
  - the `verification.verified` event, with the `source` domain;
  - a brief;
  - the consent question.
- The dashboard's case view (`NEXT_PUBLIC_DATA=live`) shows the letter panel filled: explanation, checklist, masked refs, the "checked against" source, and the brief's questions.
- `reads.official_dial_number(case_id)` returns the mock line with `DEMO_DIAL_NUMBER` set, and the real verified number without it.
- Nothing sensitive in events, logs or job results. Their `LeakGuard` keeps checking this.
