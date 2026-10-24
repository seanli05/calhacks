# WhatsApp pipe: status and notes for the team

Owner: person 2 (Lauren). Last updated 2026-10-23, branch `lauren-whatsapp-pipe`.

## What works

Goal 2 (the WhatsApp pipe) is built and was tested end to end on a real phone, through the Twilio sandbox and the shared Neon database:

- **Language pick.** "Hola, recibí una carta" gets the Spanish one-tap confirm; replying `1` sets `users.language`.
- **Letters.** A photo gets "Recibido. ¿Tiene más páginas?"; photos within 6 s of each other become one `documents` row.
- **Other text.** It's echoed back as a placeholder until the orchestrator's Claude turn (Goal 4).
- **Logging.** Every message in both directions is in `messages`, with its Twilio SID.

The test suite (`pytest`) covers every routing path on fakes, with no network.

| Piece | File |
|---|---|
| Webhook: checks the Twilio signature, queues the work, returns empty TwiML in ~5 ms | `backend/app/relay/webhook.py` |
| The pipe: user row → media saved → message logged → routed | `backend/app/orchestrator/pipe.py` |
| Language pick (detection uses `MODEL_FAST`) | `orchestrator/language.py`, `translation/detect.py` |
| Grouping photos into letters (C20) | `orchestrator/photos.py` |
| Sending and logging: `send_template`, `send_text` | `relay/outbound.py` |
| Twilio wrapper: REST send, split over 1,600 chars, media download | `relay/whatsapp.py` |
| Message templates, `en` + `es` | `relay/templates.py` |

## If your code touches WhatsApp

- **Phone agent (person 4).** Anything you send the user goes through `relay.outbound.send_template(whatsapp, user, template_id, values)`, never free text (rule 1). New templates go in `relay/templates.py` in both `en` and `es`; a test fails if one is missing. ask_user and call-status messages are Goal 3, next. Call-status messages follow C36 (agreed): you log every call event to `events` unfiltered, and the orchestrator picks which ones to send to the user as templates. Still open with you: how ask_user is wired (a relay function you await, or you poll the `questions` row).
- **Dashboard (person 1).** In `messages`:
  - `sender` is `relay` for templates and `orchestrator` for free text.
  - Templated rows carry `template` and an English `body_en`.
  - Incoming Spanish messages have `body_en = null` until translation lands (Goal 5).
  - Before a user picks a language, incoming messages are logged as the detected language, or `en` if detection can't tell. The bilingual language menu is logged as `es`.
- **Research (person 3).** When a batch of photos closes, the pipe only creates the `documents` row. Goal 4 adds minting the `case_id` and queuing `research_fast` for it.

## Concerns

1. **"Same letter or new?" can't trigger yet.** It's only asked once a `cases` row exists, and research creates that row. Until research runs, and in the gap before it inserts the case, a second photo sent a minute later becomes a separate letter. Proposed fix: the pipe also remembers the letter it just created.
2. **None of this shows on the dashboard timeline.** Picking a language, creating a letter, and adding pages write no `events`, because no event types exist for them. Adding types is a contract change, so it's a team decision.
3. **Run the backend as one process.** Open photo batches live in memory, so don't use `--workers`. A restart drops batches that haven't closed (the photos stay in `media`), and a reload mid-message drops that message. Keep `--reload-dir backend` so the reloader doesn't restart on `.venv` changes.
4. **The sandbox is slow.** Twilio takes 5–9 s to forward each message to us (photos are the slow end); our reply goes out 1–2 s after that. Users wait about 7–10 s in total. The "< 2 s" ack target holds for our code only.
5. **The Spanish template text needs a native speaker's check**, using USCIS's official Spanish terms where they apply.
6. **`.env.example` fix.** It used to pre-fill `DATABASE_URL_UNPOOLED` with localhost. Settings prefer that variable, so a copied `.env` with only `DATABASE_URL` filled in silently used localhost. It's blank now. If your own `.env` still has the localhost line, delete it.

## Still open from Goal 1

- **ask_user wiring**: decide with person 4 (see above). Call-status delivery is settled by C36.
- **Noticing finished jobs**: the orchestrator needs to know when research and call jobs finish. Either person 1 adds a helper like `list_finished_jobs(since)`, or it checks each job it knows about with `get_job`.
- **Recording the language and photo decisions in Plan.md**: done in this change. Sean, check the wording.
