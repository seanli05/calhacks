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
uvicorn app.main:app --app-dir backend --reload --reload-dir backend   # http://localhost:8000/health
```

The dashboard API lives under `/api` (routes in [docs/specs/dashboard-api.md](docs/specs/dashboard-api.md)); try `http://localhost:8000/api/demo`. Set `TWILIO_SANDBOX_JOIN_CODE` (the code on Twilio's sandbox page, without "join") so the landing page's QR can show the join message.

Startup creates any missing tables. To rebuild the database and seed the demo case (one Spanish-speaking user, the I-797C case from `mock_agency`, verified, with the WhatsApp exchange, memory, and feed events up to the consent question), run the command below. **This wipes the shared database for everyone**, so check with the team first:

```bash
cd backend && python -m app.db.reset --yes           # add --empty to skip the seed
python -m app.db.reset --yes --after-call             # or: also a finished call, for the ended screens
```

To try the seed without touching the shared database, point it at the test branch: `DATABASE_URL_UNPOOLED=<TEST_DATABASE_URL> python -m app.db.reset --yes`.

Run the dashboard (Node 20, from the repo root):

```bash
cd dashboard && npm install
npm run dev     # http://localhost:3000, on fake data (fixtures) by default
NEXT_PUBLIC_DATA=live npm run dev   # against the backend on :8000
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
| `app.db.deletes` | The "What we know about you" page (through the dashboard API) |

`case_progress(case_id)` returns one of `received`, `explaining`, `needs_better_image`, `checking`, `suspicious`, `unknown`, `awaiting_consent`, `calling`, `on_hold`, `connected`, `call_ended`, `closed`.

### WhatsApp (Twilio sandbox + ngrok)

1. Install ngrok (version 3.20 or newer; run `ngrok update` if needed) and add your token: `ngrok config add-authtoken <token>`.
2. Run `ngrok http 8000` and copy the `https://...` URL.
3. In `.env`, set `PUBLIC_BASE_URL` to that URL (no trailing slash, no `/whatsapp`) and fill in `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`. Use the team's one funded Twilio account (ask person 2): a trial account with a negative balance rejected every reply. Restart the server; `--reload` doesn't pick up `.env` changes.
4. In that account's console, go to **Messaging → Try it out → Send a WhatsApp message → Sandbox settings** and set **When a message comes in** to the full URL `https://<your-ngrok-domain>/whatsapp`, method **POST**, then Save and reload the page to check it stuck. New accounts land on a "Try out WhatsApp" page with no webhook setting; switch to the legacy Console (account menu) to get the sandbox page with the **Sandbox settings** tab.
5. From your phone, send that account's join code (`join <two-words>`) to the sandbox number shown there.

`/whatsapp` checks Twilio's request signature against `PUBLIC_BASE_URL` and the auth token, so both must match the account whose sandbox points at you.

**Gotchas (each cost us time on Oct 23):**
- The sandbox number (+1 415 523 8886) is shared by every Twilio account. Your message goes to whichever sandbox your phone joined most recently, so join with the code of the account in your `.env`.
- A sandbox has one webhook URL, so only one laptop receives at a time. Agree who it points at.
- If the URL is missing `https://`, Twilio silently doesn't call it: Twilio's logs show the message as received, with no error, and nothing reaches ngrok. If the method is GET, ngrok shows `GET /whatsapp` with a 405.
- Twilio's default "Configure your WhatsApp Sandbox's Inbound URL" reply means no URL is saved.
- Expect 5–9 s from send to webhook on the sandbox (photos are the slow end); that delay is Twilio's, not ours.
- To debug, check in order: the ngrok inspector (http://127.0.0.1:4040), then Twilio **Monitor → Logs** (Messaging and Errors), then the uvicorn log. Failed replies there show Twilio's error code.

The webhook returns empty TwiML at once and handles the message in a background task (`orchestrator/pipe.py`); every reply goes out through the Twilio REST API (`relay/whatsapp.py`) and is logged to `messages`. The pipe needs `DATABASE_URL`; without `ANTHROPIC_API_KEY`, language detection is skipped and first contact always gets the language menu. What a new number sees:

- **Language pick:** a text first message gets a one-tap confirm in the detected language; a photo-only one gets the bilingual menu.
- **Photos:** photos sent within 6 s of each other become one letter (`documents` row), and the orchestrator queues the research fast pass for it. Once research has started, a new photo gets "same letter or new?".
- **Other text:** echoed back until the orchestrator's Claude turn lands (Goal 4).

Reply templates live in `relay/templates.py` (`en` and `es`). Status, interfaces (ask_user, call status), decisions, and open concerns for the WhatsApp side: [docs/whatsapp-pipe.md](docs/whatsapp-pipe.md). To see ask_user and the call-status messages on your phone without the phone agent, set `DEV_ENDPOINTS=true` and use `POST /dev/fake-call` (local only; steps in that doc). `POST /dev/fake-research` stands in for the research agent the same way.

### Deploying for the demo

Everything runs on one laptop (the one recording the video). Only the backend is public, through ngrok, so Twilio can reach it. The dashboard stays on `localhost`.

1. **A fixed public URL.** Every free ngrok account gets one static domain (ngrok dashboard → **Domains**). Using it means the Twilio webhook URLs survive ngrok restarts:

   ```bash
   ngrok http --url=<your-name>.ngrok-free.app 8000
   ```

   Without a static domain, use `ngrok http 8000` and redo steps 2 and 3 every time ngrok restarts.
2. **Point the backend at it.** In `.env`, set `PUBLIC_BASE_URL=https://<your-name>.ngrok-free.app` (no trailing slash). Keep `DEV_ENDPOINTS=false`. Then start the backend without `--reload`, as one process:

   ```bash
   uvicorn app.main:app --app-dir backend --port 8000
   ```

3. **Point Twilio at it.**
   - WhatsApp: in the sandbox settings, set **When a message comes in** to `https://<your-name>.ngrok-free.app/whatsapp`, method POST (details in the WhatsApp steps above).
   - Voice: the phone agent passes its webhook URLs, built from `PUBLIC_BASE_URL`, when it places each call, so the agent number shouldn't need a console setting. Person 4 confirms this when `phone/` lands.
4. **Reset the shared database** to the seeded demo case (ask the team first; it wipes everyone's data): `cd backend && python -m app.db.reset --yes`.
5. **Run the dashboard** as a production build on live data:

   ```bash
   cd dashboard && npm install
   NEXT_PUBLIC_DATA=live npm run build && npm start   # http://localhost:3000
   ```

   `NEXT_PUBLIC_DATA` is baked in at build time, so rebuild after changing it. Open `http://localhost:3000`, follow the demo link to the case page, and record at 1920×1080.

Checks before recording: `http://localhost:8000/health` and `https://<your-name>.ngrok-free.app/health` both answer, a WhatsApp message to the sandbox shows up in the ngrok inspector (http://127.0.0.1:4040), and your phone joined the sandbox within the last 3 days.

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
| `dashboard/` | Next.js dashboard ([build guide](docs/specs/dashboard-build.md)) | 1 |
| `mock_agency/` | Mock USCIS line on Cartesia; deploys on its own | 3 |
| `spikes/` | Throwaway experiments (e.g. `dtmf/`: key presses on the mock line); not imported by the backend | Spike owner |
| `docs/specs/` | Build specs that implement Plan.md | Spec owner |
| `docs/whatsapp-pipe.md` | WhatsApp side: what works, notes for teammates, concerns | 2 |

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
