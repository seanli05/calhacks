# Cal Hacks: Government Letter Agent

*Name TBD (shortlist: Kinvoy, Unhold).*

A WhatsApp agent that helps immigrant families deal with immigration letters, starting with the USCIS I-797C asylum interview notice. Send a photo of a letter, and the agent:

1. explains it in your language: what it is, the deadline, and what's being asked;
2. checks that it's legitimate against the agency's official site (form, links, receipt number format, official phone number);
3. with your consent, calls the agency, navigates the phone menu, and waits on hold;
4. rings your phone when a human picks up, then sends a summary on WhatsApp afterward.

A web dashboard shows the live call timeline, the case, and what the agent remembers about you.

## How it works

| Component | Role |
| --- | --- |
| **Orchestrator** | The only agent that converses with the user on WhatsApp |
| **Research agent** | Reads the letter, verifies it, and writes the case brief for the call |
| **Phone agent** | Places the call, handles the menu and hold, and brings in the user |
| **Shared modules** | Translation, memory writer, message relay, glossary worker |

Components hand work to each other through Postgres (`jobs` and `events` tables), not direct calls.

**Stack:** Python 3.12 · FastAPI · Postgres (SQLModel + asyncpg) · Claude (Anthropic SDK) · Pipecat · Twilio Voice and WhatsApp · Cartesia · Next.js dashboard · ngrok

## Getting started

```bash
git clone <repo-url> && cd calhacks
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill in your keys
```

You'll need:
- Anthropic and Cartesia API keys
- Twilio credentials, an agent number, and a mock agency number
- Your phone joined to the Twilio WhatsApp sandbox (the session expires 3 days after joining, so re-join before the demo)
- The team's shared hosted Postgres URL (set `DATABASE_URL`; ask person 1)
- ngrok for public webhook URLs (set `PUBLIC_BASE_URL`)

Run the backend (from the repo root, with the venv active):

```bash
uvicorn app.main:app --app-dir backend --reload   # http://localhost:8000/health
```

Startup creates any missing tables. To rebuild the database and seed the demo case (one Spanish-speaking user, the I-797C case from `mock_agency`, verified), run the command below. **This wipes the shared database for everyone**, so check with the team first:

```bash
cd backend && python -m app.db.reset --yes           # add --empty to skip the seed
```

### Using the database

Import only your own writer module, plus the shared ones. That's how "one writer per table" is enforced.

Full guide, with per-component recipes: [docs/data-layer-guide.md](docs/data-layer-guide.md).

| Module | Who imports it |
| --- | --- |
| `app.db.writes.<orchestrator\|research\|phone\|relay\|memory\|glossary>` | That component only |
| `app.db.reads` | Anyone. Includes `case_progress`, `official_dial_number` (the only way to get a number to dial), `resolve_ref`, `list_events` |
| `app.db.jobs` | `enqueue` (creator); `claim_next`, `finish`, `fail` (handler) |
| `app.db.events` / `app.db.messages` | `append_event` (everyone); `append_message` (orchestrator, relay) |
| `app.db.deletes` | The "What we know about you" page |

`case_progress(case_id)` returns one of `received`, `explaining`, `needs_better_image`, `checking`, `suspicious`, `unknown`, `awaiting_consent`, `calling`, `on_hold`, `connected`, `call_ended`, `closed`.

### WhatsApp (Twilio sandbox + ngrok)

1. Install ngrok (version 3.20 or newer; run `ngrok update` if needed) and add your token: `ngrok config add-authtoken <token>`.
2. Run `ngrok http 8000` and copy the `https://...` URL.
3. In `.env`, set `PUBLIC_BASE_URL` to that URL (no trailing slash) and fill in `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`. Restart the server; `--reload` doesn't pick up `.env` changes.
4. In the Twilio console, go to **Messaging → Try it out → Send a WhatsApp message → Sandbox settings** and set **When a message comes in** to `POST <PUBLIC_BASE_URL>/whatsapp`. New accounts land on a "Try out WhatsApp" page with no webhook setting; switch to the legacy Console (account menu) to get the sandbox page with the **Sandbox settings** tab.
5. From your phone, send the join code shown on that page to the sandbox number shown there.

`/whatsapp` checks Twilio's request signature against `PUBLIC_BASE_URL` and the auth token, so both must match the account whose sandbox points at you. If you get Twilio's default "Configure your WhatsApp Sandbox's Inbound URL" reply, the webhook URL isn't saved. For now the bot echoes text and replies to photos with their type and size.

## Repo layout

| Path | What | Owner |
| --- | --- | --- |
| `Plan.md` | The spec: source of truth | Team |
| `backend/app/main.py`, `settings.py` | FastAPI app and the single settings object | 1 |
| `backend/app/db/`, `api/` | Tables, DB helpers, dashboard API | 1 |
| `backend/app/contracts/` | Shared Pydantic payloads (jobs, results, events) | Team |
| `backend/app/orchestrator/`, `relay/`, `memory/`, `translation/` | WhatsApp side | 2 |
| `backend/app/research/`, `glossary/` | Letter → case brief | 3 |
| `backend/app/phone/` | The call | 4 |
| `backend/tests/` | Backend tests | Everyone |
| `dashboard/` | Next.js dashboard (coming) | 1 |
| `mock_agency/` | Mock USCIS line on Cartesia; deploys on its own | 3 |
| `docs/specs/` | Build specs that implement Plan.md | Spec owner |

## Development

```bash
ruff format . && ruff check --fix .   # format + lint
pytest                                # tests
```

DB helper tests (`backend/tests/test_db_helpers.py`) are skipped unless `TEST_DATABASE_URL` is set (env or `.env.local`; person 1 has the URL). Point it at a separate Neon branch (`neon branch create --name test`), never the shared database: the tests drop and rebuild every table.

- Work on a branch, open small PRs, and merge to `main` often.
- Read [CLAUDE.md](CLAUDE.md) before writing code. It has the product rules that can't be broken and the team's engineering conventions.

## Team

| Person | Owns |
| --- | --- |
| 1 | Postgres schema, DB helpers, dashboard, deployment |
| 2 | Orchestrator, WhatsApp webhook, translation, memory writer, message relay |
| 3 | Research agent, glossary, mock agency line |
| 4 | Phone agent: call state machine, hold/human detection, bridge, call report |
