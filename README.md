# Cal Hacks: Government Letter Agent

*Name TBD (shortlist: Kinvoy, Unhold).*

A WhatsApp agent that helps immigrant families deal with immigration letters, starting with the USCIS I-797C asylum interview notice. Send a photo of a letter, and the agent:

1. explains it in your language: what it is, the deadline, and what's being asked;
2. checks that it's legitimate by comparing the letter's phone number with the agency's official one;
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
- A local Postgres database (set `DATABASE_URL`)
- ngrok for public webhook URLs (set `PUBLIC_BASE_URL`)

Run commands for each service will be added here as they land.

### Research agent (solo, no Postgres)

```bash
python -m research.sim fixtures/letters/i797c_asylum_interview_degraded/   # add --fake for no API key
python -m research.sim.devui   # dev test page at http://127.0.0.1:8000
```

If an agency site blocks our fetch (uscis.gov returns 403), save its contact page from a browser and seed it. The page is re-checked by code on every run and is only used when the live site can't be fetched:

```bash
python -m research.cli seed fixtures/web/seed/uscis_contactcenter.html \
  --url https://www.uscis.gov/contactcenter --phone +18003755283 --captured 2026-10-23
# other issuers: add --purpose (case_questions, renewal, housing_case, general)
```

The dev page takes a photo or PDF upload and shows the explanation, checklist, verdict, official phone with its trust chain, and the event log. Tick "fake passes" to run without an API key, or "skip deep" for extraction only. For redacted test copies, "simulate redacted fields" assumes a blacked-out case number has the issuer's expected shape; the verdict is then labeled SIMULATED (dev page only, never the real flow). Nothing is saved.

## Development

```bash
ruff format . && ruff check --fix .   # format + lint
pytest                                # tests
```

- Work on a branch, open small PRs, and merge to `main` often.
- Read [CLAUDE.md](CLAUDE.md) before writing code. It has the product rules that can't be broken and the team's engineering conventions.

## Team

| Person | Owns |
| --- | --- |
| 1 | Postgres schema, DB helpers, dashboard, deployment |
| 2 | Orchestrator, WhatsApp webhook, translation, memory writer, message relay |
| 3 | Research agent, glossary, mock agency line |
| 4 | Phone agent: call state machine, hold/human detection, bridge, call report |
