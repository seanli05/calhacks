# Dashboard: what's left before it's done

Owner: person 1 · Tracks: task C ([task-c-dashboard.md](task-c-dashboard.md) → Done when) · Design changes are out of scope here

Every page and every API route is built and on `main`. This is the non-design work left before task C is officially done. Tick items off here as they land.

## Must do

- [ ] **1. Verify the API fixes.** The speed fix (concurrent reads) and the Spanish stand-in for seeded text (`backend/app/api/stand_in_es.py`) landed in `d83c8be` and `cf6aac3`. Check on the shared database with `NEXT_PUBLIC_DATA=live`: the case view updates within about a second, and the Spanish screens show no English except the muted lines under each item. `GET /api/cases/{id}` took about 4.2s before the fix and about 1.9s after it, measured on 2026-10-24. Each DB read costs about 375ms against Neon in `us-east-2`. Then `engine.py` dropped `pool_pre_ping`, recycled connections at 240s (under Neon's 5-minute suspend) and grew the pool to 20: warm, the case page is about 1.0s, the case list about 1.0s, the feed about 0.6s and the memory page about 0.46s (2026-10-24). Speed is done. What's left is checking the Spanish screens by eye.
- [ ] **2. Make live data the default.** `dashboard/lib/api/client.ts` still serves fixtures unless `NEXT_PUBLIC_DATA=live`. Flip the default to live, keep `NEXT_PUBLIC_DATA=fixtures` for building pages without the backend, and update `dashboard/.env.example`, [dashboard-build.md](dashboard-build.md) and the README.
- [ ] **3. Deployment (task step 5).** Write the exact commands in the README:
  - `ngrok http 8000`, with a reserved ngrok domain if the account has one, so webhook URLs survive restarts;
  - `PUBLIC_BASE_URL`, and pointing the WhatsApp sandbox and the voice webhooks at it;
  - the dashboard on the recording laptop: `NEXT_PUBLIC_DATA=live npm run build && npm start`. It doesn't need to be public.
- [ ] **4. Tell the team which event `data` the feed needs.** Feed lines are only specific when the emitter includes certain `data` fields; otherwise they fall back to a generic line. The table is at the top of [`backend/app/api/feed_templates.py`](../../backend/app/api/feed_templates.py). Persons 2 (consent, memory) and 4 (`call.*`) need it.
- [ ] **5. Reset the shared database with the new seed:** `cd backend && python -m app.db.reset --yes` (no `--after-call`, so the case starts at `awaiting_consent`). Again right before the rehearsal and before recording.
- [ ] **6. End-to-end rehearsal with the real components**, once the phone agent is on `main`. One real call with the case view on screen at 1920×1080. Check that:
  - the tracker and headline move through calling → on hold → person answered → connected → call ended as the real events arrive;
  - the hold timer starts at `call.on_hold`;
  - the panel turns forest when a person answers;
  - the call report and transcript appear after the call;
  - the feed lines are specific (item 4) and in Spanish;
  - the WhatsApp mirror shows the relay messages as they're sent.
- [ ] **7. Task C "Done when" checks.**
  - `ruff format . && ruff check --fix . && pytest` pass from the repo root, and `npm run build` passes in `dashboard/`.
  - On the seeded database at 1080p: the feed, the case view, the memory page including one delete (it shows "(borrado …)" in the feed), and the WhatsApp mirror all work.
  - Everything is merged and pushed to `origin/main`.
  - Report to the team what landed.

## Can wait

- [ ] **Landing QR.** Set `TWILIO_SANDBOX_JOIN_CODE` in `.env` (the code from Twilio's sandbox page, without "join"). Until then the QR has no join message.
- [ ] **Product name.** `[App]` is a placeholder in `common.appName` and `case.speakers.agent` in `dashboard/lib/i18n/strings/*/`.
- [ ] **Real translation.** Person 2's translation module replaces the Spanish stand-in. Then delete `backend/app/api/stand_in_es.py` and its test, and route `localize` through the module. Until then, anything outside the seed (a live demo's call report, new facts) shows in English.
- [ ] **Optional speed-up.** A Neon project in `us-west-2` would cut every database round trip about 5× from California. It changes the URLs for the whole team.
