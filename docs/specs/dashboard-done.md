# Dashboard: what's left before it's done

Owner: person 1 · Tracks: task C ([task-c-dashboard.md](task-c-dashboard.md) → Done when) · Design changes are out of scope here

Every page and every API route is built and on `main`. This is the non-design work left before task C is officially done. Tick items off here as they land. Everything person 1 built, how the rest plays out, and what to ask of the team: [person-1-brief.md](person-1-brief.md). What teammates must write for the dashboard to show it: [docs/dashboard-AGENTS.md](../dashboard-AGENTS.md).

## Must do

- [ ] **1. Verify the API fixes.** The speed fix (concurrent reads) and the Spanish stand-in for seeded text (`backend/app/api/stand_in_es.py`) landed in `d83c8be` and `cf6aac3`. Check on the shared database with `NEXT_PUBLIC_DATA=live`: the case view updates within about a second, and the Spanish screens show no English except the muted lines under each item. `GET /api/cases/{id}` took about 4.2s before the fix and about 1.9s after it, measured on 2026-10-24. Each DB read costs about 375ms against Neon in `us-east-2`. Then `engine.py` dropped `pool_pre_ping`, recycled connections at 240s (under Neon's 5-minute suspend) and grew the pool to 20: warm, the case page is about 1.0s, the case list about 1.0s, the feed about 0.6s and the memory page about 0.46s (2026-10-24). Speed is done. What's left is checking the Spanish screens by eye.
- [x] **2. Make live data the default.** Done Oct 24 (overnight): live unless `NEXT_PUBLIC_DATA=fixtures`; `.env.example`, [dashboard-build.md](dashboard-build.md) and the README updated.
- [x] **3. Deployment (task step 5).** Done: README → "Deploying for the demo". It covers:
  - `ngrok http 8000`, with a reserved ngrok domain if the account has one, so webhook URLs survive restarts;
  - `PUBLIC_BASE_URL`, and pointing the WhatsApp sandbox and the voice webhooks at it;
  - the dashboard on the recording laptop: `NEXT_PUBLIC_DATA=live npm run build && npm start`. It doesn't need to be public.
- [ ] **4. Tell the team which event `data` the feed needs.** Written up in [docs/dashboard-AGENTS.md](../dashboard-AGENTS.md); send it to the team. Feed lines are only specific when the emitter includes certain `data` fields; otherwise they fall back to a generic line. The table is at the top of [`backend/app/api/feed_templates.py`](../../backend/app/api/feed_templates.py). Persons 2 (consent, memory) and 4 (`call.*`) need it.
- [ ] **5. Reset the shared database with the new seed:** `cd backend && python -m app.db.reset --yes` (no `--after-call`, so the case starts at `awaiting_consent`; it loads the glossary too). Again right before the rehearsal and before recording. The demo runs on the team host's branch (`phone-int-p4`), whose glossary was loaded on Oct 24 (`python -m app.glossary.load`, 257 rows).
- [ ] **6. End-to-end rehearsal with the real components**, once the phone agent is on `main`. One real call with the case view on screen at 1920×1080. Check that:
  - **Oct 24 overnight:** `python -m app.dev.rehearsal` (README → "Rehearse without a phone") ran the whole path on `research-int-p1` with fake research and the phone agent's real runner on a simulated line: 11 stage checks, 0 problems, screenshots at every stage, the green moment and the report included. What's left is the same run with real research, a real line and WhatsApp.
  - the tracker and headline move through calling → on hold → person answered → connected → call ended as the real events arrive;
  - the hold timer starts at `call.on_hold`;
  - the panel turns forest when a person answers;
  - the call report and transcript appear after the call;
  - the feed lines are specific (item 4) and in Spanish;
  - the WhatsApp mirror shows the relay messages as they're sent;
  - the live activity: research's searches, pages and checks stream into a card and fold away when the check ends; the call card shows the menus heard;
  - after the bridge: the live translation streams in Spanish, tips appear and glossary terms open the translation book (needs `ANTHROPIC_API_KEY` on the host).
- [ ] **7. Task C "Done when" checks.**
  - **Oct 24 overnight, on `research-int-p1` with the seed:** ruff, all tests (866) and `npm run build` pass. At 1080p My cases, the case view, the memory page and the WhatsApp mirror render. A fact delete shows "(borrado el 24 oct)" in the feed, and no feed line is left in English. Left: the same on the shared database after item 5, and the report to the team.
  - `ruff format . && ruff check --fix . && pytest` pass from the repo root, and `npm run build` passes in `dashboard/`.
  - On the seeded database at 1080p: the feed, the case view, the memory page including one delete (it shows "(borrado …)" in the feed), and the WhatsApp mirror all work.
  - Everything is merged and pushed to `origin/main`.
  - Report to the team what landed.

## Built since (Oct 24)

- **Live call view:** streamed translation of both sides, tips, the translation book (resizable left split). Spec: [dashboard-build.md](dashboard-build.md), [dashboard-api.md → Live call](dashboard-api.md#live-call). Sean's live transcript save is merged (#27).
- **Live activity in the feed:** research and call steps as cards that fold when done ([dashboard-build.md](dashboard-build.md)).
- **Language dropdown with Dari** (`fa`, the team's second language): Dari UI strings (`strings/fa/`), right-to-left layout (`dir` follows the language; CSS uses logical properties), Afghan Gregorian dates (`intlLocale` in `lib/format.ts`: "۱۲ نومبر، ۸:۳۰ صبح") and Vazirmatn for the script. Text without a Dari template (feed, suggestions, step rows) goes through the translation cache and shows English until it lands; the feed refetches until then. `?lang=fa` opens any page in Dari. The UI strings want the same fluent-speaker check as the WhatsApp templates ([docs/dari-review.md](../dari-review.md)).

## Can wait

- [ ] **Landing QR.** Set `TWILIO_SANDBOX_JOIN_CODE` in `.env` (the code from Twilio's sandbox page, without "join"). Until then the QR has no join message.
- [ ] **Product name.** `[App]` is a placeholder in `common.appName` and `case.speakers.agent` in `dashboard/lib/i18n/strings/*/`.
- [x] **Real translation.** `localize` translates text outside the seed with person 2's translator in the background and caches it (`translations.py`); the stand-in stays for the seed's text so it shows at once.
- [ ] **Optional speed-up.** A Neon project in `us-west-2` would cut every database round trip about 5× from California. It changes the URLs for the whole team.
