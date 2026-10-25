# Running the whole thing end to end

From a photo on WhatsApp to a real phone call: the letter is read, explained, and verified; the user says YES; the phone agent calls, works the menu, holds, and rings the user when a person answers; the summary comes back on WhatsApp.

**The default: use the team host's backend** (currently Sean's laptop). It runs `main` with every worker on, and the team's WhatsApp sandbox points at it. You need only your phone, plus the dashboard if you want to watch. Host your own only to test code that isn't on `main` yet.

| | Team host (default) | Host your own |
|---|---|---|
| You run | Nothing, or just the dashboard | Backend, ngrok, dashboard |
| Code | The host's checkout of `main` | Yours |
| Database | The host's Neon branch | Your own Neon branch |
| WhatsApp | The team sandbox, already pointed at the host | You take the team sandbox's one webhook, so nobody else gets messages |

## Use the team host (default)

Everything is keyed by WhatsApp number: each of you is a separate user with your own cases and calls, and the bridge rings your own phone. Several people can run the flow at once.

1. **Join the sandbox.** Ask the host for the join code. From your phone, send `join <two-words>` to **+1 415 523 8886**. The join lasts 3 days; send it again if replies stop.
2. **Text "hi"** and follow [The flow](#the-flow).
3. **Dashboard (optional).** Ask the host for their ngrok URL and your `user_…` ID (there's no lookup by phone number). Then, on your laptop:
   ```bash
   cd dashboard && npm install        # once
   BACKEND_URL=https://<host-ngrok-domain> npm run dev
   ```
   and open `http://localhost:3000/u/<your user_id>`.

What to know:
- **To test a branch end to end,** merge it to `main` and ask the host to pull and restart.
- **A restart clears in-memory state** (an open consent request, photos being grouped). The host warns before restarting; if the bot loses track, send your message again.
- **Test letters only.** The dashboard API behind the host's ngrok URL has no login: anyone with the URL and a `user_…` ID can read that user's messages and photos. Don't send real letters or personal documents.

### For the host

Keep the backend on `main`, and pull and restart when teammates merge (warn them first). Look up a teammate's ID in the database's `users` table: each row has its `whatsapp_number`. Keep `DEMO_DIAL_NUMBER` on the mock line, since every teammate's call uses it. If several people call at once, check with person 3 that the mock line takes concurrent calls.

## Host your own

Also the setup for whoever is the team host. If you're not the team host, tell the team before step "Point WhatsApp at you": it moves the sandbox off the team host, so nobody else gets replies until it's moved back.

### Once

1. **Your own Neon branch.** Ask person 1. Put its URLs in the repo-root `.env.local` (gitignored):
   ```
   DATABASE_URL=postgresql://...
   DATABASE_URL_UNPOOLED=postgresql://...
   ```
   Never run the workers against the shared database: only one backend may claim jobs there (README → Using the database).
2. **`.env`** (copy from `.env.example`). Besides the keys (`ANTHROPIC_API_KEY`, `CARTESIA_API_KEY`, `CARTESIA_AGENT_VOICE_ID`, and the team's funded Twilio account: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_AGENT_NUMBER`):
   ```
   PUBLIC_BASE_URL=https://<your-ngrok-domain>
   RESEARCH_WORKER=true
   MEMORY_WORKER=true
   PHONE_WORKER=true
   PHONE_JOIN_GATE=false   # the demo: join on pick-up, no key press (README → the phone agent)
   DEV_ENDPOINTS=false
   DEMO_DIAL_NUMBER=<the mock agency line, from .env.example>
   ```
   `DEMO_DIAL_NUMBER` replaces the verified number at dial time, and only for a verified case (Plan.md C40). Keep it on the mock line unless you're testing with a friend as the agency (below).
3. **ngrok.** Install it, add your token, and use the free static domain from the ngrok dashboard (Domains) so the URL survives restarts.
4. **Dashboard deps:** `cd dashboard && npm install`.

### Each session

Three terminals, from the repo root:

```bash
# 1. ngrok
ngrok http --url=<your-ngrok-domain> 8000

# 2. backend
source .venv/bin/activate
uvicorn app.main:app --app-dir backend --reload --reload-dir backend

# 3. dashboard
cd dashboard && npm run dev    # http://localhost:3000
```

Restart the backend after any `.env` change: `--reload` only watches code.

Check it's reachable:

```bash
curl http://localhost:8000/health/db
curl https://<your-ngrok-domain>/health
```

### Point WhatsApp at you

The sandbox has one webhook, so tell the team before you take it.

1. Twilio console (the team account) → **Messaging → Try it out → Send a WhatsApp message → Sandbox settings**.
2. **When a message comes in:** `https://<your-ngrok-domain>/whatsapp`, method **POST**. Save, then reload the page to check it stuck.
3. Join the sandbox from your phone (see above), and text "hi".

**Expect a few minutes of mixed routing after a change.** Twilio kept sending some messages to the previous URL for a while after the save; those messages are simply lost (error 11200). If a message gets no reply, check where it went (see [When it doesn't work](#when-it-doesnt-work)) and send it again.

### The dashboard

The landing page shows the seeded demo user, not you. Open `http://localhost:3000/u/<your user_id>`. Find the ID in the uvicorn log, or in your database's `users` table (the newest row after your first message).

## The flow

1. **"hi"** → the bot asks to confirm your language. Answer with the number.
2. **Photo of the letter.** For a test letter, photograph `backend/tests/fixtures/research/letters/i797c_asylum_interview/page_1.png` on another screen. The bot asks if there are more pages; say no.
3. **Explanation**, then **verification** against uscis.gov. Research takes a minute or two.
4. **"Would you like me to call USCIS for you?"** Answer YES with the number. The uvicorn log shows `Call queued`.
5. **The call.** The agent dials `DEMO_DIAL_NUMBER`, answers the menu by speaking, and holds. If it can't tell which option fits, it asks you on WhatsApp; answer with the number.
6. **Your phone rings** within ~5 s of a person answering. Pick up (press a key when asked, if `PHONE_JOIN_GATE` is on), and answer the representative's questions yourself (the agent never answers for you).
7. **Summary on WhatsApp** after the call, with the reference number and next steps.

### Who plays the agency

The bridge rings the WhatsApp number that started the case, so the applicant and the agency must be different phones.

- **Mock line** (default): `DEMO_DIAL_NUMBER` = the mock agency line. You're the applicant. Ask person 3 for a short hold (`MOCK_AGENCY_HOLD_SECONDS`), or for `MOCK_AGENCY_MODE=quick`, where the officer picks up at once with no menu or hold ([mock_agency/README.md](../mock_agency/README.md#modes)).
- **A friend as the agency** (on your own backend, not the team host, since it changes every teammate's calls): `DEMO_DIAL_NUMBER` = their phone (E.164, in `.env` only, never in code). Restart. They read a menu ("For case status, press 1…"), put the agent on hold, then greet like a rep ("USCIS, this is Maria, how can I help?"). The agent answers a menu after the whole prompt and ~1.5 s of quiet. Set it back to the mock line afterwards.

## When it doesn't work

Check in this order: the ngrok inspector (http://127.0.0.1:4040), then Twilio **Monitor → Logs → Errors**, then the uvicorn log.

| Symptom | Cause | Fix |
|---|---|---|
| No reply, nothing in the ngrok inspector, Twilio error **11200** | Twilio sent it to another URL: the error's URL is the old webhook | Check the sandbox settings are on the team account and saved. Right after a change, wait a few minutes and resend |
| Save in sandbox settings shows no confirmation | The save request failed in the browser | Private window or another browser; log in again |
| `POST /whatsapp` → **403** | Signature check failed | `TWILIO_AUTH_TOKEN` and `PUBLIC_BASE_URL` must match the account and ngrok URL the sandbox uses. Restart after editing `.env` |
| `POST /whatsapp` → 200 but no reply; log full of `connection was closed in the middle of operation` / `TimeoutError` | The database connection dropped. Venue wifi cuts idle connections | Resend the message. For the full run, put the backend laptop on a phone hotspot, but never the applicant's phone (next row) |
| Worker tracebacks `claiming research_… failed` | Same; the worker retries a second later | Noise unless it doesn't stop |
| Bot forgot the consent question after a restart | Open consent requests live in memory | Ask it to call again; it re-asks |
| YES accepted, but no call | `PHONE_WORKER` is off, or a setting is missing | The startup log names missing settings. Restart after changing `.env` |
| Listen-in goes silent and drops; at the same moment, `phase reading failed: TimeoutError`, `menu decision failed`, Cartesia `peer has stopped reading` | The backend laptop is on the hotspot of the phone being called: a voice call on that phone stalls its hotspot data (Oct 24) | Put the laptop on wifi or another phone's hotspot |
| Your phone never rings for the bridge | You're also the agency (same phone), or voicemail took it | Two phones; see [Who plays the agency](#who-plays-the-agency) |
| Replies stop entirely | Sandbox join expired (3 days) | Send the join code again |

To see where Twilio sent recent messages without the console (from `backend/`, venv active):

```bash
python - <<'EOF'
import urllib.parse as u
from twilio.rest import Client
from app.settings import get_settings
s = get_settings(); c = Client(s.twilio_account_sid, s.twilio_auth_token)
for n in c.monitor.v1.alerts.list(limit=5):
    a = c.monitor.v1.alerts(n.sid).fetch(); q = dict(u.parse_qsl(a.alert_text or ""))
    print(a.date_created, a.error_code, q.get("httpResponse"), q.get("url"))
EOF
```

More on each piece: README (WhatsApp, the phone agent, deploying for the demo), [specs/phone-live-checks.md](specs/phone-live-checks.md) (manual call checks), [research-live-test.md](research-live-test.md).
