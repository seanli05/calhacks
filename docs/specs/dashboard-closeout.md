# Closing out the dashboard: brief for person 1

Context for a conversation about finishing task C: what happens next, what person 1 does, and what to ask of persons 2, 3 and 4. The checklist itself is [dashboard-done.md](dashboard-done.md); the doc teammates' agents follow is [docs/dashboard-AGENTS.md](../dashboard-AGENTS.md).

## Where things stand (Oct 24)

- Every dashboard page and API route is on `main`: landing, My cases, the live case view, the memory page, the WhatsApp mirror. Spanish and English.
- Speed is done. The case page loads in about 1.0s (it was 4.2s), after concurrent reads and a connection-pool fix in `backend/app/db/engine.py`.
- Deployment steps are in the README ("Deploying for the demo").
- Fixed today: the hold timer would have reset every time the phone agent repeated `call.on_hold`; it now counts from the first one. The landing page no longer scrolls sideways or leaves empty space at the bottom.
- Landed later on Oct 24:
  - person 4's call state machine (`phone/state.py`) and menu decider (`phone/menu.py`), but not yet the part that places the call, waits on hold, bridges the user and writes the report;
  - person 2's orchestrator now queues research for each letter, plus `/dev/fake-research`.
- Not on `main` yet:
  - the rest of the phone agent;
  - research on the contract models (person 3, on branch `research_agent`);
  - the orchestrator's Claude turn, translation and the memory writer (person 2).

## The two questions

**Does making live data the default mean we start practice runs?** No, they're separate.
- "Live default" (item 2) only changes what `npm run dev` shows when no setting is given: the real database instead of fake data. It's a 10-minute change and starts nothing.
- Practice runs can already happen today, with person 2's dev stand-ins. Turn them on with `DEV_ENDPOINTS=true`, run the backend, and watch with `NEXT_PUBLIC_DATA=live`. Use your own Neon branch, not the shared database.
  1. **Fake research:** `POST /dev/fake-research` finishes research jobs from the contract fixtures. Send a letter photo on WhatsApp and the case appears on the dashboard: explanation, verdict, brief, masked refs. It takes research jobs from the shared queue, so don't run it while person 3's real research worker is running.
  2. **Fake call:** `POST /dev/fake-call` plays a scripted call through the real tables: dialing, menu, a real WhatsApp question, hold, a person answers, the call ends. It sends real WhatsApp messages to the number you give it. It makes its own throwaway case and closes it at the end, so open that case's page while it runs.
  3. **Real call (item 6):** once person 4's call runner is on `main`.
  - Runs 1 and 2 together cover the whole demo except the real call, without persons 3 and 4. That's the best practice run available now.

**Is everything above the data layer done, so that correct data means a correct dashboard?** Yes, with one caveat.
- The dashboard reads only the database and has no logic tied to any other component. If each component writes its rows through its writer module with the contract models, the pages show it.
- The caveat is the handful of things the types don't check. Those are listed in `docs/dashboard-AGENTS.md`:
  - event `data` fields (otherwise feed lines are generic);
  - the brief's two keys `call_goal_en` and `questions_to_ask` (the brief is still a free dict);
  - setting `human_detected` the moment a person answers (the green moment);
  - transcript speakers being exactly `agent`, `agency` or `user`;
  - `body_en` on the orchestrator's free-text messages.
- One real gap: translation. Today only the seed's strings have Spanish (a hard-coded stand-in). Anything new, like a real call's report or new facts, shows in English until person 2's translation lands and is wired into the API. That needs a decision (below).

## What happens for each remaining item

| # | Item | Who | When |
|---|---|---|---|
| 2 | Live data by default | Person 1 (ask Claude, 10 min) | Any time; harmless |
| 4 | Tell the team the event `data` fields | Person 1 sends `docs/dashboard-AGENTS.md` | Now, so they build it in rather than retrofit |
| 5 | Reset the shared database | Person 1 runs it | When the team's components land, again before the rehearsal, and again right before recording |
| 6 | End-to-end rehearsal | Everyone; person 1 watches the dashboard | After the phone agent and research are on `main` |
| 7 | "Done when" checks and report | Person 1 | After the rehearsal passes |

The real order:
1. Send the integration doc now (item 4).
2. Each person's agent checks their component against it while they build.
3. Merge.
4. Reset the database (item 5).
5. Rehearse with fake research plus the fake call first (possible now), then a real call (item 6).
6. Fix whatever looked wrong.
7. Reset again, then record.
8. Run the final checks (item 7).

## What to ask of each person

Each person gives their Claude this prompt, with their number and area filled in:

> Read `backend/AGENTS.md`, then `docs/dashboard-AGENTS.md`, the section for person N. Check that my component (`<package>`) writes everything that section lists: event types and their `data` fields, the row fields, and the order of the states. List the gaps first, then fix them inside my package only. Verify with the "Check your work against the dashboard" steps on my own Neon branch, not the shared database. Don't edit `app/api/` or `dashboard/`. If the dashboard needs something it doesn't read yet, write it down for person 1.

What each person's agent will find, so you can talk it through with them:

- **Person 2 (WhatsApp side).** Mostly already right: templates fill English, ask_user logs `choice` and `default_option`, and the fake call uses the right fields. Left to do:
  - `body_en` on free-text replies, once the Claude turn lands;
  - the `consent.requested` event with `agency`;
  - `memory.fact_*` events with `fact_id`, once the memory writer exists;
  - the translation interface (decision below).
- **Person 3 (research).** The biggest integration risk. Their branch uses its own models instead of `app.contracts`, so nothing they produce shows up until they write R1, the verification and the brief through `writes.research` with the contract models. `app/dev/fake_research.py` already writes exactly what the dashboard reads, so it's a working example to match. They also need:
  - the brief keys `call_goal_en` and `questions_to_ask`;
  - the official URL first in `evidence`;
  - sensitive values through `put_ref`.
- **Person 4 (phone).** The state machine on `main` already guarantees the order of states. What's left is the call runner writing the right things:
  - `human_detected` set at once when a person answers;
  - `call.on_hold` when hold starts (repeats are fine);
  - `call.ended` with `minutes`;
  - the transcript with the three speaker names;
  - the report with English `next_steps_en`.
  - One open question for them: does the agent number need a voice webhook set in the Twilio console, or does the agent pass its URLs when it places the call? The README assumes the second.

## Decisions to make in the call

1. **Translation interface.** The API needs Spanish for free text quickly, since it polls every 1–3s; an LLM call per request is too slow. Proposal: person 2's module translates at write time and caches by English text and language, and the API reads the cache. Then person 1 swaps `localize` and deletes the stand-in. Alternative for the demo: extend the stand-in table with the exact strings the rehearsal produces. That's fragile, but needs no work from person 2.
2. **Test databases.** Agents collided on the one `test` branch. Proposal: one Neon branch per person (`neon branch create --name <name>`), and nobody writes to the shared database except through the running app.
3. **Demo laptop.** The WhatsApp sandbox has one webhook URL, so agree whose laptop runs the backend and ngrok for the rehearsal and the recording. The dashboard runs on the same laptop.
4. **Product name** for the `[App]` placeholder, and the `TWILIO_SANDBOX_JOIN_CODE` for the landing page's QR. Both can wait until before recording.

## Risks to watch

- Research not on contract models means an empty letter panel, which is the most visible part of the case view.
- Real-call text in English: the report and new facts aren't in Spanish without translation, unless the stand-in is extended.
- A database reset during someone's test wipes their data. Announce each reset.
- The sandbox session expires 3 days after joining. Re-join the day of recording.
