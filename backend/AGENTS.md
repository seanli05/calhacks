# AGENTS.md: start here

A map of the backend for any agent (or human) picking up work. It points to the docs that hold the details instead of repeating them.

## Read in this order

1. [CLAUDE.md](../CLAUDE.md): product rules that can't be broken, plus team conventions (ownership, git, tests, secrets).
2. [Plan.md](../Plan.md): **the source of truth.** What the product does, the handoff payloads (H1, R1, R2, H2, P1–P3), events, data model, failure rules. Its C-tags (C1–C35) explain each decision.
3. [docs/data-layer-guide.md](../docs/data-layer-guide.md): how to use the database helpers and contracts, with recipes per component, case stages, gotchas, and open issues.
4. [docs/dashboard-AGENTS.md](../docs/dashboard-AGENTS.md) if your component writes rows or events: what it must write so the dashboard shows it (event `data` fields, brief keys, call states).
5. The spec or task doc for your area (below).

If two docs disagree, Plan.md wins, then the code. Fix the doc that's wrong.

## Docs index

| Doc | What it's for |
|---|---|
| [README.md](../README.md) | Setup, run commands, env vars, WhatsApp sandbox + ngrok, repo layout, team table |
| [docs/data-layer-guide.md](../docs/data-layer-guide.md) | Using `app.db` and `app.contracts` |
| [docs/specs/data-layer-schema.md](../docs/specs/data-layer-schema.md) | Every table and column, and which component writes it (locked) |
| [docs/specs/task-a-db.md](../docs/specs/task-a-db.md) | How the data layer was specified (done) |
| [docs/specs/task-b-contracts.md](../docs/specs/task-b-contracts.md) | How the contracts were specified (done) |
| [docs/specs/task-c-dashboard.md](../docs/specs/task-c-dashboard.md) | Dashboard task: steps and the approved design |
| [docs/specs/dashboard-api.md](../docs/specs/dashboard-api.md) | Dashboard API routes, feed templates, masking, seed |
| [docs/specs/dashboard-build.md](../docs/specs/dashboard-build.md) | Building dashboard pages: conventions, work split, start prompts |
| [docs/specs/dashboard-done.md](../docs/specs/dashboard-done.md) | Dashboard: what's left before it's done |
| [docs/dashboard-AGENTS.md](../docs/dashboard-AGENTS.md) | **Integrating with the dashboard:** what each component must write (event `data`, brief keys, call states) so it shows up |
| [docs/specs/phone-ports.md](../docs/specs/phone-ports.md) | Phone agent: its ports, fakes, and which rules they enforce |
| [docs/specs/phone-live-checks.md](../docs/specs/phone-live-checks.md) | Phone agent: manual calls on real phones (the bridge, the minute alone with the rep, finding the person, the mock line), with results |
| [docs/overnight-2026-10-24.md](../docs/overnight-2026-10-24.md) | What person 1's session changed overnight Oct 24, by owner, for review |
| [docs/specs/case-brief.md](../docs/specs/case-brief.md) | **The case brief:** the research → phone contract, field by field, who writes and reads each, the rules every brief keeps |
| [docs/research-integration.md](../docs/research-integration.md) | **Joining the research agent to `main`:** a runbook two agents execute end to end (status table, decisions, step 1 for person 1, step 2 for person 3) |
| [docs/whatsapp-pipe.md](../docs/whatsapp-pipe.md) | WhatsApp side: what works, how to plug in (`send_template`, `messages` fields), concerns |
| [docs/whatsapp-AGENTS.md](../docs/whatsapp-AGENTS.md) | Reviewing the WhatsApp side: every file person 2 built, deliberate choices, what to check |
| [docs/handoff-shorter-messages.md](../docs/handoff-shorter-messages.md) | **For person 3:** a short `summary_en` in R1 and a short R2 call goal, so WhatsApp messages stop repeating themselves |
| [mock_agency/README.md](../mock_agency/README.md) | The mock USCIS phone line the agent calls: menu tree, hold, officer |

## Backend layout (`backend/app/`)

| Package | What | Owner | State |
|---|---|---|---|
| `main.py`, `settings.py` | FastAPI app (creates tables on startup); the single settings object | 1 | Done |
| `contracts/` | Shared Pydantic payloads; import from `app.contracts` | Team | Done (`CaseBrief` provisional) |
| `db/` | Tables, reads, per-writer write modules, jobs, events, deletes, reset/seed (`seed_story.py`: messages, memory, events, `--after-call`) | 1 | Done |
| `api/` | Dashboard API: routes, feed and suggestion templates (`feed_templates.py` lists the event `data` fields it expects; `localize` takes the seed's strings from the fixed Spanish table `stand_in_es.py` and any other free text from `translations.py`, which translates it once in the background with `translation/`'s translator and caches it in memory) | 1 | Done; spec in `docs/specs/dashboard-api.md` |
| `relay/` | WhatsApp webhook, Twilio send/download, templates (`send_template`); ask_user relay | 2 | Webhook, sending, templates, ask_user (`relay.ask_user.ask_user(request)`, P1) done |
| `orchestrator/`, `translation/`, `memory/` | WhatsApp agent, translation, memory writer | 2 | Pipe (language pick, photo grouping), call-status messages (C36, `orchestrator/call_status.py`), letter → `research_fast` with a job watcher (`orchestrator/letters.py`, `job_watch.py`), the Claude turn with its tools plus translation at the edges (`orchestrator/turn.py`, `translation/translate.py`), results, consent and calls, and the memory writer (`memory/worker.py`, `writer.py`, `filters.py`; starts with the app when `MEMORY_WORKER=true`) with asking before saving (`orchestrator/fact_consent.py`, `memory/consent.py`) done, glossary grounding in every translation prompt (`translation/glossary.py`), and pacing (`orchestrator/conversation.py`: one speaker and one numbered question at a time). Interfaces and decisions: [docs/whatsapp-pipe.md](../docs/whatsapp-pipe.md) |
| `dev/` | Dev-only stand-ins: `POST /dev/fake-call` (a scripted call without the phone agent), `POST /dev/fake-research` (finishes research jobs from the contract fixtures). Off unless `DEV_ENDPOINTS=true`; local requests only | 2 | Done |
| `glossary/` | Preset glossary: `terms.csv` (75 English terms; es, fa (Dari), ne for every term, official-only ar, ps, ru, vi), sources in `SOURCES.md`, review sheets for the Dari and Nepali checkers, loader `python -m app.glossary.load [--dry-run] [--language xx]` (run from `backend/`; tell the team first, and re-run after a reset). The automatic glossary worker is out of the MVP (C28) | 2 | Data, loader and tests done; translation reads it per prompt (`translation/glossary.py`) |
| `research/` | Letter reading, verification, case brief | 3 | Work is on branch `research_agent` (top-level `research/`, own models); integration plan in [docs/research-integration.md](../docs/research-integration.md) |
| `research/`, `glossary/` | Letter reading, verification, case brief; glossary | 3 | Research done: fast pass (R1, refs), deep pass (verification, alternative contacts, brief), `research_question`, on `app.contracts` and `app.db`. `worker.py` claims its jobs and starts with the app (`RESEARCH_WORKER`); `jobs.py` holds the handlers; `cli.py` runs each pass alone (README → The research agent). Tests and a DB fake in `tests/research/`, letter and web fixtures in `tests/fixtures/research/`. Glossary not started |
| `phone/` | Call state machine, hold/human detection, bridge, call report | 4 | State machine (`state.py`), menu decider (`menu.py`), phase classifier (`phase.py`), ports and fakes (`ports.py`, `fakes.py`), the call runner (`runner.py` + `runner_*.py`, `executor.py`), the call report (`report.py`: deterministic for calls that never reached a person, Claude over the transcript for connected ones, with a manual eval in `report_eval.py`), and the job worker (`worker.py`: claims `call`, runs the call on a real Twilio line, finishes the job, queues `memory_write`; starts with the app when `PHONE_WORKER=true`) done, with a text-tree simulator (`simulate.py`, `sim_trees.py`) and an interactive playground (`playground/`, where you play the line). The real line over Twilio + Pipecat (`twilio_line.py`, `twilio_urls.py`, `twilio_rest.py`, `listener.py`, `audio_pipeline.py`, `routes.py`): the agency leg, live-tested with the smoke test (`smoke.py`, a dev tool the app never imports), and the bridge to the applicant (join gate, conference, listen-only forks for the transcript), built and tested on fakes; see [docs/specs/phone-ports.md](../docs/specs/phone-ports.md). The bridge's first live runs and the report eval next |

Tests live in `backend/tests/`. Contract fixtures in `backend/tests/fixtures/contracts/` double as fake inputs for any component.

## Working rules, in short

The full versions are in CLAUDE.md and the data-layer guide.

- **Stay in your package.** Ask before touching contracts, the schema, Plan.md, or someone else's package.
- **Database:** import only your own `app.db.writes.<component>` module, plus `reads`, `jobs`, `events`, `messages`. No raw SQL.
- **Dialing:** the only number the phone agent may dial comes from `reads.official_dial_number(case_id)`.
- **Sensitive values** (receipt number, A-Number, date of birth, interview location) go in `case_refs` and travel as `<ref:name>`. Events carry IDs, never content.
- **Config:** everything comes from env vars via `app.settings`. Never commit secrets or personal data; the only phone number allowed in git is the mock agency line in `.env.example`.

## Running things

```bash
python -m venv .venv && source .venv/bin/activate     # 3.12 per README; 3.13 works
pip install -r requirements-dev.txt
uvicorn app.main:app --app-dir backend --reload --reload-dir backend   # from the repo root; one process, never --workers
ruff format . && ruff check --fix . && pytest         # before every push
```

- **Database:** one shared Neon Postgres; URLs are in the repo-root `.env.local` (ask person 1). It's already seeded with the demo case.
- **`python -m app.db.reset --yes`** (run from `backend/`) wipes the shared database for everyone. Ask the team first.
- **DB tests** run only when `TEST_DATABASE_URL` points at your own Neon branch (never the shared database; they drop every table). A full run with them takes about a minute.
- **Only the deployed backend claims jobs on the shared database.** Running locally against it, set `RESEARCH_WORKER=false` and `MEMORY_WORKER=false`, leave `PHONE_WORKER` off, and keep `DEV_ENDPOINTS` off; to run workers or dev endpoints, use your own branch. README → "Using the database".

## Git

- Branch per feature, small commits with one short imperative line and no AI attribution. Fast-forward merge to `main` (`gh` isn't installed).
- Pull before you start and before you merge.
- Several agents may share this clone. Do your work in your own worktree (`git worktree add ../calhacks26-<topic> -b <name>/<topic> main`), so branch switches don't collide.

## Open issues

Tracked in [data-layer-guide.md → Open issues](../docs/data-layer-guide.md#open-issues):
- the fake WhatsApp number in the seed.
