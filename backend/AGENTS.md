# AGENTS.md: start here

A map of the backend for any agent (or human) picking up work. It points to the docs that hold the details instead of repeating them.

## Read in this order

1. [CLAUDE.md](../CLAUDE.md): product rules that can't be broken, plus team conventions (ownership, git, tests, secrets).
2. [Plan.md](../Plan.md): **the source of truth.** What the product does, the handoff payloads (H1, R1, R2, H2, P1–P3), events, data model, failure rules. Its C-tags (C1–C35) explain each decision.
3. [docs/data-layer-guide.md](../docs/data-layer-guide.md): how to use the database helpers and contracts, with recipes per component, case stages, gotchas, and open issues.
4. The spec or task doc for your area (below).

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
| [docs/whatsapp-pipe.md](../docs/whatsapp-pipe.md) | WhatsApp side: what works, how to plug in (`send_template`, `messages` fields), concerns |
| [docs/whatsapp-AGENTS.md](../docs/whatsapp-AGENTS.md) | Reviewing the WhatsApp side: every file person 2 built, deliberate choices, what to check |
| [mock_agency/README.md](../mock_agency/README.md) | The mock USCIS phone line the agent calls: menu tree, hold, officer |

## Backend layout (`backend/app/`)

| Package | What | Owner | State |
|---|---|---|---|
| `main.py`, `settings.py` | FastAPI app (creates tables on startup); the single settings object | 1 | Done |
| `contracts/` | Shared Pydantic payloads; import from `app.contracts` | Team | Done (`CaseBrief` provisional) |
| `db/` | Tables, reads, per-writer write modules, jobs, events, deletes, reset/seed (`seed_story.py`: messages, memory, events, `--after-call`) | 1 | Done |
| `api/` | Dashboard API: routes, feed and suggestion templates (`feed_templates.py` lists the event `data` fields it expects; `stand_in_es.py` is a temporary Spanish table for the seed's strings, to delete once `translation/` lands) | 1 | Done; spec in `docs/specs/dashboard-api.md` |
| `relay/` | WhatsApp webhook, Twilio send/download, templates (`send_template`); ask_user relay | 2 | Webhook, sending, templates, ask_user (`relay.ask_user.ask_user(request)`, P1) done |
| `orchestrator/`, `translation/`, `memory/` | WhatsApp agent, translation, memory writer | 2 | Pipe (language pick, photo grouping) and call-status messages (C36, `orchestrator/call_status.py`) done; Claude turn, translation, memory not started. Interfaces and decisions: [docs/whatsapp-pipe.md](../docs/whatsapp-pipe.md) |
| `dev/` | Dev-only stand-ins, e.g. `POST /dev/fake-call` (a scripted call without the phone agent). Off unless `DEV_ENDPOINTS=true`; local requests only | 2 | Done |
| `research/`, `glossary/` | Letter reading, verification, case brief; glossary | 3 | Work is on branch `research_agent` (top-level `research/`, own models) |
| `phone/` | Call state machine, hold/human detection, bridge, call report | 4 | Not on `main` yet |

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
- **DB tests** run only when `TEST_DATABASE_URL` points at the separate Neon `test` branch. A full run with them takes about a minute.

## Git

- Branch per feature, small commits with one short imperative line and no AI attribution. Fast-forward merge to `main` (`gh` isn't installed).
- Pull before you start and before you merge.
- Several agents may share this clone. Do your work in your own worktree (`git worktree add ../calhacks26-<topic> -b <name>/<topic> main`), so branch switches don't collide.

## Open issues

Tracked in [data-layer-guide.md → Open issues](../docs/data-layer-guide.md#open-issues):
- the provisional `CaseBrief` shape;
- the research models that don't match the contracts yet;
- the fake WhatsApp number in the seed.
