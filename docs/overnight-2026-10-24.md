# Overnight report: Oct 24 → 25 (person 1's session)

What person 1's Claude session did overnight while nobody else was committing, grouped by owner so each person can review what touched their code.

Every piece passed the gate before it merged to `main`: ruff, every test (867 at the end) including the DB tests on Neon `research-int-p1`, and `npm run build`. Nothing touched the shared database.

## Summary

1. **Research is on `main`.** Person 3's step 2 (`research/integrate`) merged after rebasing; 846 tests passed at merge. Its live end-to-end test still needs a run with an Anthropic key (status table in [research-integration.md](research-integration.md)).
2. **Sean's call agent and playground comply with the contracts.** The one gap was the brief, now specified and enforced (3).
3. **The research → call contract is specified:** [docs/specs/case-brief.md](specs/case-brief.md). The phone agent validates every brief against it, and research now fills `expected_menu_path`.
4. **Person 2's hand-offs are built**, not just sent: research's "which letter?" question (C39) and official-source answers to user questions (C38).
5. **A phone-free rehearsal harness** (`python -m app.dev.rehearsal`) runs the whole demo path on a test branch: letter → research → consent → Sean's real runner on a simulated line → report. It checks the dashboard API and takes screenshots at every stage. It found five bugs, all fixed (below).
6. **Dashboard close-out:**
   - live data is the default;
   - item 7's checks pass on the seeded test branch, delete included;
   - the done list is updated ([dashboard-done.md](specs/dashboard-done.md)).

## Changes by owner

### Person 4 (Sean): `backend/app/phone/`
- `adapters.py` → `DbCaseReader.get_brief` now validates the brief against `CaseBrief`. A brief that breaks the contract stops the call before it dials. The runner still reads it as JSON, defensively, as designed; `menu.py` is unchanged.
- `ports.py`: the `CaseReader` docstring says so.
- `runner_menu.py`: a fix for `RuntimeWarning: coroutine 'decide' was never awaited`. When 1c fired before the decide task started, the task was cancelled and the `menu.decide(...)` coroutine it had been handed was never awaited. The coroutine is now created inside the task (`_classify_and_decide`). Behavior is otherwise unchanged; the rehearsal runs clean with warnings turned into errors.
- `tests/test_phone_adapters_db.py`: saves a real `CaseBrief`, and checks that a brief breaking the contract is refused.
- **To read:** [case-brief.md](specs/case-brief.md). Your menu decider's three inputs are documented there, and research now fills the menu hints.

### Person 3 (research): `backend/app/research/`
- Step 2 merged (your commits `b7b7abc`, `d92a8af`, rebased onto `main` unchanged).
- `brief.py`: research now fills `expected_menu_path`, menu hints by meaning with no key numbers, which the phone agent's decider reads. It's deterministic and issuer-agnostic (`MENU_*` constants); tests are in `tests/research/test_brief.py`.
- `fast_pass.py`, `prompts.py`, `jobs.py`: the fast pass reads `user_note_en` (C39) as the user's words, marked as data (`USER_NOTE_PROMPT`), and only when it's set. Tests: `test_user_note_reaches_the_model_as_data`, `test_fast_passes_the_users_note_through`.
- **Still yours:**
  - run `RESEARCH_E2E=1 pytest backend/tests/research/test_e2e_live.py` on `research-int-p3` and record it in the status table;
  - review [case-brief.md](specs/case-brief.md);
  - `research_question` (C38) is wired end to end now, so a real run would be worth a look.

### Person 2: `backend/app/orchestrator/`, `relay/`, `dev/`
- **C39, research's question** (`letter_result.py`, `letters.py`, `pipe.py`, templates `letter.which_letter`, `letter.reading_again`):
  - An R1 with `needs_user_input` gets research's `question_en`, translated (with a template fallback), and no explanation; the verdict isn't watched yet.
  - The user's next text, in English, re-runs the fast pass on the same case as `user_note_en`.
  - The pipe routes it after "same letter or new?" and before consent.
  - Tests are in `test_orchestrator_results.py` and `test_orchestrator_letters.py`.
- **C38, official-source answers** (new `orchestrator/research_questions.py`):
  - The turn gets a seventh tool, `ask_official_source`, which queues `ResearchQuestionJob` and tells the user it's looking.
  - When the job finishes, the answer goes out translated with up to three source URLs.
  - Declines (legal advice, the asylum claim, not found) and failures get fixed templates (`research_question.*`).
  - The system prompt tells the model when to use it. Tests are in `test_research_questions.py`.
- `dev/fake_research.py`, `dev/fake_call.py`: they save valid `CaseBrief`s (from the seed's `demo_brief`), because the phone agent now refuses loose briefs.
- `dev/rehearsal.py`: new (above). It lives in `dev/` because it writes several owners' tables on a test branch.
- `docs/whatsapp-pipe.md` → "What works" describes both flows.

### Person 1 (data layer, API, dashboard, docs)
- [case-brief.md](specs/case-brief.md) (new); links from `backend/AGENTS.md` and the data layer guide.
- **Stage mapping:** a call in `wrap_up` is now `call_ended`, not `connected`. Wrap-up means the line has closed, and the call may never have reached a person. Before this, a call that failed in the menu briefly showed the green "a person answered" panel.
- **Dashboard:**
  - Live data is the default (`NEXT_PUBLIC_DATA=fixtures` for fake data).
  - The ended headline follows the outcome ("We couldn't reach a person at USCIS" / "We couldn't reach you").
  - The tracker marks only the steps a failed call reached.
  - `wrap_up` is no longer the green moment.
- **Feed:** `call.menu_heard` is hidden; it fired on every menu prompt and buried everything else. "The call ended after N min" fixes "1 minutes".
- **Seed:** the immigration fact is `pending_consent`, with a `memory.fact_pending_consent` event (C15, C25).
- **README:** "Rehearse without a phone"; live data is the default.

## What the rehearsal found (all fixed)

| Found | Fix |
|---|---|
| Research never filled `expected_menu_path`, so the phone agent's menu decider had no hints | Meaning-based hints in `research/brief.py` |
| `call.menu_heard` per menu prompt flooded the feed | Hidden from the feed (still logged) |
| A call that failed in the menu briefly showed "A person answered" (`wrap_up` → `connected`) | `wrap_up` → `call_ended`; not the green moment |
| A failed call's headline said "We spoke with USCIS", and the tracker showed every step done | Outcome-aware headline; the tracker stops where the call did |
| "1 minutes" in the feed | "N min" |
| `coroutine 'decide' was never awaited` in the runner | Coroutine created inside the task |

Screenshots of every stage are in `rehearsal/` (not committed).

## Still open (needs a person)

- **Translation in the dashboard API.** Text outside the seed (a real call's next steps, new checklist items) shows in English. Person 2's `translation/` exists now, so `localize` can use it with a cache. Not done tonight; it wasn't on the list.
- **Design questions:** the tracker shows "Llamando" as the current step while a case only awaits consent, and the hold → menu → person sequence in rehearsals came from the scripted classifier, not the real one.
- **The shared database** still needs the reset with the new seed (dashboard-done item 5), and the team should hear about it first.
- **Person 4** should confirm whether the agent number needs a voice webhook in the Twilio console (README → Deploying).
- Runbook row 3: the person 2 hand-offs are done (above); person 4's note is in this report.
