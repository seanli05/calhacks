# Person 1's work: a brief

Context for a conversation about everything person 1 built (the contracts, the database layer, the dashboard and its API, and deployment): how it fits together, where it stands, and what's left to finish and coordinate with persons 2, 3 and 4. Written to be read aloud or handed to Claude as the opening of a voice chat.

Details live elsewhere, and this brief points to them:
- [Plan.md](../../Plan.md): the product spec.
- [data-layer-guide.md](../data-layer-guide.md): using the database.
- [data-layer-schema.md](data-layer-schema.md): every column.
- [dashboard-api.md](dashboard-api.md): the API.
- [task-c-dashboard.md](task-c-dashboard.md): the dashboard's design.
- [dashboard-done.md](dashboard-done.md): the checklist.
- [docs/dashboard-AGENTS.md](../dashboard-AGENTS.md): what teammates must write.

## The big picture

The product is several agents that never call each other. The orchestrator talks to the user on WhatsApp, the research agent reads and verifies the letter, and the phone agent makes the call. **One Postgres database is how they communicate.** One agent puts a job in a table and another claims it. Every agent appends events to a log, and the dashboard reads the database to show what's happening.

Person 1 built three layers of that:

1. **The shared language:** the contracts, which are the exact shape of every message between agents.
2. **The database:** the tables, plus the only functions allowed to read and write them.
3. **The window onto it:** a read-only API and the web dashboard, plus how the whole thing is configured and deployed.

Everyone else's code sits on top of layers 1 and 2. If those are right and everyone follows them, the components fit together without talking to each other.

## 1. Contracts (`backend/app/contracts/`)

- **What they are:** Pydantic models for every payload in Plan.md.
  - The two research jobs and their results: `ResearchFastJob` and `FastResult` (H1 and R1), then `ResearchDeepJob` and `DeepResult` (R2).
  - The call job, `CallJob` (H2). It carries no phone numbers.
  - Asking the user a question mid-call: `AskUserRequest` and its reply (P1).
  - The call report, `CallReport` (P3).
  - The event: `Event`, with the full list of `EventType` values.
  - Shared enums and types: languages, E.164 phone numbers, `<ref:name>` placeholders and ID types.
- **Strict on purpose:** unknown fields are rejected, so a typo fails loudly instead of silently dropping data.
- **Example data for tests:** `backend/tests/fixtures/contracts/*.json` holds every Plan.md example as data. Teammates use them as fake inputs, and the fake research reuses them.
- **Still open:** the case brief (`CaseBrief`) is a plain dict until persons 3 and 4 agree its shape. The working version is the one from the research branch: `call_goal_en`, `questions_to_ask`, `must_not_do`, `expected_menu_path`, and so on.

## 2. The database (`backend/app/db/`)

**Where it lives.** One shared Neon Postgres in `us-east-2`, plus a separate `test` branch for database tests. The test branch exists because the tests wipe every table. The URLs are in the repo-root `.env.local`, which isn't committed.

**16 tables, each with exactly one writer** (product rule 5):

| Group | Tables | Writer |
|---|---|---|
| The user | `users`, `media` (photo bytes), `documents` (a letter = grouped photos) | orchestrator |
| The case | `cases` (incl. R1), `verifications`, `case_briefs`, `case_refs` (sensitive values) | research |
| The call | `calls` (state, report), `transcripts` | phone |
| Questions mid-call | `questions` | relay |
| What we remember | `profile`, `facts` | memory writer |
| Plain-language terms | `glossary` | glossary worker |
| Shared, append-only | `messages` (every WhatsApp message both ways), `events` (the log), `jobs` (the work queue) | anyone allowed, through their helpers |

**How rule 5 is enforced: by imports, not database permissions.** Each component imports only its own writer module (`app.db.writes.research` and so on), plus the shared ones:
- `reads`: anyone;
- `events`: anyone;
- `messages`: orchestrator and relay;
- `jobs`: whoever creates or handles jobs;
- `deletes`: dashboard only.

Nobody writes raw SQL.

**The ideas worth understanding:**
- **The job queue** (`jobs.py`): `enqueue`, `claim_next`, `finish`, `fail`. `claim_next` uses Postgres row locking (`FOR UPDATE SKIP LOCKED`), so several workers can poll the same queue without taking the same job twice. Workers poll about once a second, and failed jobs aren't retried automatically.
- **The event log** (`events.py`): every significant decision is an event, with IDs only and never content (C27). The dashboard feed and debugging both read it. Four event types trigger a WhatsApp message to the user (P2).
- **The case stage is computed, never stored** (`progress.py`, C17). `case_progress(case_id)` looks at the latest call, verification and research job, and returns one of 12 stages, from `received` to `closed`. Nobody can forget to update a stage, because there's nothing to update. The dashboard's headline and progress tracker come from it.
- **Sensitive values never travel** (C11, C34). The receipt number, A-Number, date of birth and interview location go in `case_refs`. Everything else passes `<ref:receipt_number>` around, and the real value is looked up (`resolve_ref`) only at the point of use. The dashboard shows them masked, like `•••• 2345`, and never shows the date of birth.
- **Safety rules built into the data:**
  - `official_dial_number(case_id)` is the only way to get a number to dial, and it refuses unless the case's latest verification says verified (rule 2).
  - A call row can't exist without a consent message to point to, because the database requires one (rule 4).
- **Deletes** (`deletes.py`, C26): delete a fact, a document and its images, a transcript, or everything for a user. Only the dashboard's memory page calls them. Each one logs a `*.deleted` event that carries only IDs.
- **The connection pool** (`engine.py`). The database is about 130ms away. The pool keeps up to 20 connections open, skips the extra round trip that checks each connection is still alive, and replaces connections after 4 minutes. That's safe because Neon closes connections only after 5 idle minutes. Together with running reads in parallel, this cut the case page from 4.2s to about 1.0s.
- **No migrations.** Startup creates missing tables but never changes existing ones. A column change means a reset.

**Reset and seed** (`reset.py`, `seed_story.py`):
- `python -m app.db.reset --yes` drops everything, recreates the tables and seeds the demo story: a Spanish-speaking user, an I-797C asylum interview notice, verified, with the WhatsApp conversation, memory and feed events up to the moment the agent asks permission to call.
- `--after-call` adds a finished call; `--empty` skips the seed.
- It wipes the shared database for everyone, which is why it needs a heads-up to the team.

## 3. Configuration (`backend/app/settings.py`)

- One settings object reads every key, model name, phone number and URL from environment variables. Nothing is hard-coded.
- Neon's URLs are rewritten for the async driver, and the unpooled URL is preferred.
- The only phone number allowed in git is the mock agency line, in `.env.example`.
- `DEV_ENDPOINTS` (added by person 2) turns on the fake research and fake call tools, for local requests only.

## 4. The dashboard API (`backend/app/api/`)

Fifteen routes under `/api`, almost all reads:

- **Navigation:** `/demo` (the demo user and open case), `/config` (WhatsApp number, sandbox code), `/users/{id}`.
- **Cases:** the case list, the full case (`/cases/{id}`), and a call's transcript.
- **Live:** the feed (`/users/{id}/feed?since=`, polled every second), the WhatsApp messages, letter images (`/media/{id}`).
- **Memory:** the memory page's data, plus the only writes: delete a fact, a document or a transcript, and "delete everything".
- **Suggestions:** three cards in the side panel, from simple rules (a countdown to the interview, terms to review, the checklist), not a model call.

What the API does on top of the raw rows:
- **Masks refs** server-side.
- **Turns events into sentences** in the user's language (`feed_templates.py`). The sentence is specific when the event's `data` has the expected fields, and generic otherwise.
- **Localizes free text** through `localize()`. Today that's a hard-coded Spanish table for the seed's strings (`stand_in_es.py`), until person 2's translation exists.
- **Runs reads in parallel** for speed.

## 5. The dashboard (`dashboard/`)

- **Stack:** Next.js 15, React 19, TypeScript, plain CSS modules. No component library, no Tailwind.
- **Design:** light, in the style of Mercury, Ramp and Stripe's docs. Greens, square corners, light borders. The signature detail is the letter shown as an annotated paper document. Approved in task C.
- **Pages:**
  - **Landing:** a hero with a looping demo call, a ticker, a bento grid of features, the promises, and a closing band with the WhatsApp QR.
  - **My cases** (`/u/{user}`): a feed of every case.
  - **Case view** (`/u/{user}/cases/{case}`): the letter panel, plus the call panel. The call panel shows the headline, hold timer and tracker. It turns solid green when a person answers, and shows the call report and transcript afterwards.
  - **Memory** (`/u/{user}/memory`): what we know about you, with deletes.
- **Every page has the assistant panel:** suggestions, the WhatsApp conversation mirrored, and a chat bar.
- **It never sends anything** (rule 1). The suggestions and the chat bar open WhatsApp with the text already typed in.
- **Languages:** every label comes from per-language string files (`lib/i18n/strings/<lang>/`), Spanish and English for now. A switch in the header changes the language live. Text from the database shows in the user's language, with the English muted underneath.
- **Two data modes:**
  - Live data (the default) reads the real API. It polls every 1–3s, never overlapping requests.
  - Otherwise it uses built-in fake data: a 7-step demo you step through with the arrow keys. That's for building pages without a backend.

## 6. Deployment (README → "Deploying for the demo")

- **One laptop runs everything.** ngrok makes the backend public on a fixed domain, because Twilio's webhooks need to reach it.
- `PUBLIC_BASE_URL` is set to that domain, and the WhatsApp sandbox's webhook points at `/whatsapp`. The dashboard runs locally as a production build on live data.
- Then reset the database, record at 1920×1080, and re-join the sandbox the same day.

## Where things stand (Oct 24)

**Done, tested and on `main`:**
- the contracts, all 16 tables and helpers, reset and seed;
- the settings and the connection pool;
- every API route and every dashboard page;
- the deployment steps;
- 290 tests pass.

**Fixed today:**
- The hold timer would have restarted every time the phone agent repeated `call.on_hold`. It now counts from the first one.
- The landing page scrolled sideways at some widths.

**Teammates' work that landed today:**
- person 4's call state machine and phone-menu decider (`phone/state.py`, `phone/menu.py`). Not yet the part that places the call, holds, bridges the user and writes the report.
- person 2's research jobs from the orchestrator, plus `/dev/fake-research`.

**Not on `main` yet:**
- the rest of the phone agent;
- research on the contract models (person 3 is on branch `research_agent`, with its own models);
- the orchestrator's Claude turn, translation, and the memory writer (person 2).

## The two questions

**Does making live data the default mean we start practice runs?** No, they're separate.
- "Live default" (item 2) only changes what `npm run dev` shows when no setting is given: the real database instead of fake data. It's a 10-minute change and starts nothing.
- Practice runs can already happen today, with person 2's dev tools. Turn them on with `DEV_ENDPOINTS=true`, run the backend, and watch the dashboard (live data is the default). Use your own Neon branch, not the shared database.
  1. **Fake research:** `POST /dev/fake-research` finishes research jobs from the contract fixtures. Send a letter photo on WhatsApp and the case appears on the dashboard: explanation, verdict, brief, masked refs. It takes research jobs from the shared queue, so don't run it while person 3's real research worker is running.
  2. **Fake call:** `POST /dev/fake-call` plays a scripted call through the real tables: dialing, menu, a real WhatsApp question, hold, a person answers, the call ends. It sends real WhatsApp messages to the number you give it. It makes its own throwaway case and closes it at the end, so open that case's page while it runs.
  3. **Real call (item 6):** once person 4's call runner is on `main`.
  - Runs 1 and 2 together cover the whole demo except the real call, without persons 3 and 4.

**If teammates write data that follows the contracts, does the dashboard handle everything else?** Yes, with one caveat.
- The dashboard reads only the database and has no logic tied to any other component. If each component writes its rows through its writer module with the contract models, the pages show it.
- The caveat is the handful of things the types don't check. Those are listed in `docs/dashboard-AGENTS.md`:
  - event `data` fields (otherwise feed lines are generic);
  - the brief's two keys `call_goal_en` and `questions_to_ask`;
  - setting `human_detected` the moment a person answers (the green moment);
  - transcript speakers being exactly `agent`, `agency` or `user`;
  - `body_en` on the orchestrator's free-text messages.
- One real gap: translation. Only the seed's strings have Spanish. Anything new, like a real call's report or new facts, shows in English until person 2's translation is wired into the API. That needs a decision (below).

## What's left for person 1

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
  - the report with English `next_steps_en`;
  - dialing only through `official_dial_number`.
  - One open question for them: does the agent number need a voice webhook set in the Twilio console, or does the agent pass its URLs when it places the call? The README assumes the second.

## Decisions to make

1. **Translation interface.** The API needs Spanish for free text quickly, since it polls every 1–3s; an LLM call per request is too slow. Proposal: person 2's module translates at write time and caches by English text and language, and the API reads the cache. Then person 1 swaps `localize` and deletes the stand-in. Alternative for the demo: extend the stand-in table with the exact strings the rehearsal produces. That's fragile, but needs no work from person 2.
2. **Research models vs contracts.** Person 3's models differ from the contracts:
   - an extra `needs_user_input` status, and `key_dates`;
   - sensitivity `high` where the contracts say `sensitive`;
   - `KeyFact` uses `value`/`page` instead of `citation`.
   
   Decide with person 3 whether the contracts or their models change. Changing a contract is a team decision.
3. **The case brief's shape.** Persons 3 and 4 confirm the working version, or the contract stays a dict for the demo.
4. **Test databases.** Agents collided on the one `test` branch. Proposal: one Neon branch per person (`neon branch create --name <name>`), and nobody writes to the shared database except through the running app.
5. **The seed's phone number.** The seeded user has a fake WhatsApp number, so the real demo phone won't match it. Either seed with the demo phone's number from `.env` at reset time (never committed), or let the real phone create its own user and case during the demo.
6. **Declined sensitive facts** (C15). The memory writer should delete a fact the user says no to, but has no delete helper. Add `writes.memory.delete_fact` (person 1), or treat "declined" as a status.
7. **Demo laptop.** The WhatsApp sandbox has one webhook URL, so agree whose laptop runs the backend and ngrok for the rehearsal and the recording.
8. **Product name** for the `[App]` placeholder, and the `TWILIO_SANDBOX_JOIN_CODE` for the landing page's QR. Both can wait until before recording.

## Risks to watch

- Research not on contract models means an empty letter panel, which is the most visible part of the case view.
- Real-call text in English: the report and new facts aren't in Spanish without translation, unless the stand-in is extended.
- A database reset during someone's test wipes their data. Announce each reset.
- The sandbox session expires 3 days after joining. Re-join the day of recording.
