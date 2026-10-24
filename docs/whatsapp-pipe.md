# WhatsApp side: status, interfaces, and decisions

Owner: person 2 (Lauren). Last updated 2026-10-24, branch `lauren-goal5-option-labels`.

This page is the record for the WhatsApp side (relay, orchestrator pipe, call status). Other components should build against the interfaces and decisions here. If something here conflicts with Plan.md, Plan.md wins; tell person 2.

## What works

**Goal 2, the WhatsApp pipe.** Tested end to end on a real phone, through the Twilio sandbox and the shared Neon database.
- **Language pick.** "Hola, recibí una carta" gets the Spanish one-tap confirm; replying `1` sets `users.language`.
- **Letters.** A photo gets "Recibido. ¿Tiene más páginas?"; photos within 6 s of each other become one `documents` row.
- **Other text.** It goes to the orchestrator's Claude turn (Goal 4.1, below). Without `ANTHROPIC_API_KEY` it's still echoed back.
- **Logging.** Every message in both directions is in `messages`, with its Twilio SID.

**Goal 3, ask_user and call status.** Tested on fakes. Try it on a phone with the fake call below.
- **ask_user (P1).** The phone agent awaits `ask_user(request)`, and the user replies with a number.
  - **Timeout:** the agent gets the default option.
  - **Late answer** (C24): the user is told which option was already taken.
  - **Anything else while the question is open:** the user is asked again for a number.
  - **Priority:** an open question gets the user's reply before anything else.
- **Call status (P2, C36).** The orchestrator watches a call's events and sends four kinds of message: dialing, on hold (at most every 10 minutes), human detected (always, at once), and unreachable.
- **Fake phone agent.** `POST /dev/fake-call` plays a scripted call, so all of the above can be seen on a phone before the real phone agent exists.

**Goal 4, letter to research (4.2–4.4).** Tested on fakes.
- **Research starts.** When a batch of photos closes, the orchestrator mints a `case_id` and queues `research_fast` for the new document.
- **"Same letter or new?"** It's asked from the moment research is queued, not only once a case exists (concern 1 fixed). Answering "same letter" re-runs the fast pass in the same case. If the last fast job is still queued, research reads the new pages anyway, so nothing more is queued.
- **Finished jobs.** One watcher per queued job polls `get_job` until it's done or failed. After 45 s on the fast pass, the user gets "taking longer" (Plan.md failure rules). The R1 reaction itself is Goal 6.1; for now a finished fast pass is only logged.
- **Turns outside the lock.** The orchestrator turn runs after the per-number routing lock is released, so an ask_user reply never waits behind it (concern 8 fixed).
- **The Claude turn (4.1, 4.5).** Free text gets a reply from `MODEL_DEFAULT` with five tools: `list_active_cases`, `get_case_status`, `get_profile`, `close_case`, `set_language`. It answers questions about a letter from the stored R1 (explanation, appointment, checklist) and the verdict. It refuses legal advice and interview interpreting per C33. It never sees a resolved ref. Text that isn't `1`/`2` while "same letter or new?" is open goes to the turn, which answers and reminds the user to pick.
- **Translation at the edges (5.1).** Inbound text is translated to English for `messages.body_en` (`MODEL_FAST`), except replies to an open ask_user question. The turn thinks and writes in English, and its reply is translated into the user's language (Spanish register: warm, simple, *usted*). If the model or the translation fails, the user gets the `orchestrator.unavailable` template, never untranslated English. ask_user option labels are translated too (concern 7).
- **Fake research agent.** `POST /dev/fake-research` claims research jobs and finishes them from the contract fixtures, so the path can be tried before the research agent is on `main`.

`pytest` covers every routing path on fakes, with no network.

| Piece | File |
|---|---|
| Webhook: Twilio signature check, queues the work, empty TwiML in ~5 ms | `backend/app/relay/webhook.py` |
| The pipe: user row → media saved → message logged → routed | `backend/app/orchestrator/pipe.py` |
| Language pick (detection uses `MODEL_FAST`) | `orchestrator/language.py`, `translation/detect.py` |
| Grouping photos into letters (C20) | `orchestrator/photos.py` |
| Sending and logging: `send_template`, `send_text` | `relay/outbound.py` |
| Twilio wrapper: REST send, split over 1,600 chars, media download | `relay/whatsapp.py` |
| Message templates, `en` + `es` | `relay/templates.py` |
| ask_user: ask, wait, timeout, late reply, reply routing | `relay/ask_user.py` |
| Numbered-reply parsing | `relay/replies.py` |
| Call-status rules and the watcher that applies them | `orchestrator/call_status.py` |
| Starting research on a letter; which letter is being read | `orchestrator/letters.py` |
| Watching queued jobs until done or failed | `orchestrator/job_watch.py` |
| The Claude turn, its tools, its prompt | `orchestrator/turn.py`, `tools.py`, `prompts.py` |
| Translation to and from English | `translation/translate.py` |
| Fake phone agent and `POST /dev/fake-call`; fake research and `POST /dev/fake-research` (dev only) | `backend/app/dev/` |
| Test fakes and fixtures for all of the above | `backend/tests/whatsapp_fakes.py`, `conftest.py` |

## If your code touches WhatsApp

### Phone agent (person 4)

**Asking the user mid-call:**

```python
from app.contracts import AskUserRequest
from app.db.ids import new_id
from app.relay.ask_user import ask_user

reply = await ask_user(
    AskUserRequest(
        question_id=new_id("question"),
        call_id=call.id,
        template="menu_choice",
        options_en=["Speak to a representative about an appointment", "Case status"],
        default_option=1,  # the safest option (C5)
        timeout_s=45,
    )
)
reply.choice  # 1-based; equals default_option if the user didn't answer in time
```

- **Don't log `call.ask_user*` events yourself.** The relay writes the `questions` row and all four of those events.
- **Cases you don't need to handle:** if the question can't be sent, you get the default at once. An unknown `template` raises `ValueError` before anything is sent.
- **`template` names the kind of question.** Only `menu_choice` exists so far. Ask person 2 for another kind, and it gets `es` + `en` text.
- **Keep `timeout_s` at 45 or more** (see concern 6).

**Call events.** Log every call event to `events` and don't filter. The orchestrator decides what the user hears (C36). Never send status messages yourself. For the status messages to work:
- **Set `call_id` on every `call.*` event.** The 10-minute on-hold limit is per call.
- **Log `call.ended` when the call ends**, including failed calls. That's what stops the watcher.
- **Optional:** `data.agency` on dialing, on-hold and human-detected events, `data.digit` on `call.menu_choice`, and `data.minutes` on `call.ended`. The dashboard feed shows them (`api/feed_templates.py`).

**Anything else you send the user** goes through `relay.outbound.send_template`, never free text (rule 1).

### Dashboard (person 1)

What to expect in `messages`:
- `sender` is `relay` for templates and `orchestrator` for free text.
- Templated rows carry `template` and an English `body_en`.
- Incoming Spanish messages have `body_en = null` until translation lands (Goal 5).
- A user's reply to an ask_user question has `question_id` set.
- Before a user picks a language, incoming messages are logged as the detected language, or `en`. The bilingual language menu is logged as `es`.

The fake call (dev only) leaves rows like a real one: a case, a brief, a failed `call` job, a call, its events, and a `case.closed` event. It also adds one outbound note, `"[dev] Fake call started…"`, that was never sent to WhatsApp. That note is what the fake call's consent pointer references.

### Research (person 3)

- **H1 is live.** When a batch of photos closes, the orchestrator mints `case_id` and queues `ResearchFastJob` (one document, `user_language` set, `user_note_en` not yet). Create the `cases` row with that ID.
- **A fast job can run twice for one case.** When the user adds a page after you've claimed the job, the orchestrator queues another `research_fast` with the **same `case_id` and document**. Your second run must not fail on the existing `cases` row: the current `insert_case` on `research_agent` (and `writes.research.create_case`) is a plain insert. The orchestrator ignores the older job's result.
- **The orchestrator reacts to the fast job you finish,** so finish it after the `cases` row and R1 are saved and the deep job is queued (`research_agent` already does this).
- **The fake call creates cases** through `writes.research.create_case` and `save_brief`, standing in for you. Those cases have no documents, no verification, and are closed at the end.
- **The fake research agent** (`dev/fake_research.py`) writes your rows from the contract fixtures. It's a stand-in until your agent is on `main`; it never runs unless someone starts it.

## Decisions (person 2, Oct 24)

Made to unblock the build; each follows Plan.md where Plan.md speaks. Raise any you disagree with.

1. **ask_user is a relay function the phone agent awaits** (Plan.md P1: "an asyncio future keyed by `question_id`"). We all run in one FastAPI process, so the wait is in memory. The `questions` row stays the source of truth: `answer_question` and `time_out_question` only close an open row, so when a reply and the timeout race, exactly one wins. The phone agent mints `question_id`. *If the phone agent ever runs in another process,* `ask` would also need to poll the row. That's a small change, not needed yet.
2. **No "call ended" message.** P2 and `USER_MESSAGING_EVENTS` allow exactly four status messages. After the call, the post-call summary (Goal 6.4, within 30 s) is the message. The `call.ended` template from the build order was removed.
3. **The status watcher follows the user, not a call ID.** The phone agent creates the call and its ID only when it picks up the job (C7), so the orchestrator can't know the ID in advance.
   - **Start:** the orchestrator calls `get_call_status().watch(user_id, since)` with the time from just before it queues the `CallJob` (Goal 6.3).
   - **Polling:** about once a second, using `reads.list_events(user_id, since)`. Nothing new was needed from person 1.
   - **Stop:** at `call.ended`, or after 3 hours.
   - **Shared timestamps:** events can share a timestamp (clocks tick in about 15 ms steps on Windows), so the watcher reads from just before its last event and skips IDs it has already seen.
4. **The fake phone agent lives in `backend/app/dev/`, off unless `DEV_ENDPOINTS=true`, and accepts local requests only.** ngrok makes the app public; requests that came through ngrok carry `X-Forwarded-For` and are refused. Because `questions.call_id` needs a real `calls` row, it writes research and phone rows through their writer modules, as their stand-in. Only `dev/` imports `writes.research` or `writes.phone` (the fake research agent too, see decision 7). It never dials:
   - its `call` job is failed the moment it's created;
   - its case is brand new and unverified, so `official_dial_number` would refuse it anyway (rule 2);
   - the consent pointer references a labelled dev note, never a made-up "YES" (rule 4).
5. **Late replies (C24) count for 10 minutes after the timeout, once per question.** The window is held in memory.
6. **The orchestrator watches each job it queues with `get_job`** (one task per job, about once a second, stops at done or failed or after 3 hours). No new helper from person 1. Which letter is being read lives in memory too (`orchestrator/letters.py`), because research creates the `cases` row only when the fast pass finishes. A restart forgets it, and a photo sent then becomes a new letter.
7. **The fake research agent lives in `dev/`, behind the same guard as the fake call.** `POST /dev/fake-research` claims `research_fast` and `research_deep` for 30 minutes (or `{"minutes": n}`), finishing each from `tests/fixtures/contracts/` after 5 s and 10 s. It saves the verification with **our mock agency line** (`TWILIO_MOCK_AGENCY_NUMBER`), never the fixture's real USCIS number. With that unset, the phone is empty and `official_dial_number` refuses the case. It claims from the shared queue, so don't run it while a real research worker uses the same database. It queues no `memory_write`; the memory writer doesn't exist yet.
8. **The turn has five tools for now; `request_consent` and `start_call` come with the consent gate (Goal 6.3).** That keeps C21 in code, not in the model's hands. Until then the prompt tells the model it can't place calls from the chat. That line comes out with Goal 6. Research starts from photos, so there's no `start_research` tool. One turn is one tool-runner loop: up to 6 model calls, 30 s per call, 60 s overall. `effort: low`, and the system prompt is cached.

## Try it on your phone (fake call)

1. **Set things up:** add `DEV_ENDPOINTS=true` to your `.env`, restart uvicorn, and make sure your number has messaged the bot and picked a language.
2. **Start the call.** From the same machine:
   ```
   curl -X POST http://localhost:8000/dev/fake-call -H "Content-Type: application/json" -d "{\"number\": \"+1YOURNUMBER\"}"
   ```
   In PowerShell: `Invoke-RestMethod -Method Post -Uri http://localhost:8000/dev/fake-call -ContentType 'application/json' -Body '{"number":"+1YOURNUMBER"}'`
3. **Expect, about 3 s apart:**
   - "Estoy llamando a USCIS ahora."
   - The menu question: reply `2`, or wait 45 s for the default.
   - One "Sigo en espera…" only: three on-hold events are logged, and the 10-minute rule drops the other two.
   - "Contestó una persona…"
4. **Also try:** text instead of a number (you get the re-prompt), and a number after the 45 s timeout (you get the late-reply message).
5. **Afterwards:** set `DEV_ENDPOINTS=false`. Keep it off for the demo.

## Try the letter path (fake research)

1. **Set things up:** as for the fake call, plus `TWILIO_MOCK_AGENCY_NUMBER` in `.env` if you'll go on to a call.
2. **Start it** from the same machine: `curl -X POST http://localhost:8000/dev/fake-research`. In PowerShell: `Invoke-RestMethod -Method Post -Uri http://localhost:8000/dev/fake-research`.
3. **Send a photo of a letter.** Expect "Recibido…", then in the uvicorn log `Research queued`, and about 5 s later `Fast pass done`. The dashboard should show the case with the fixture's I-797C, and about 10 s later the verdict. The explanation message to the user comes with Goal 6.1.
4. **Also try:** a second photo a minute later (you get "same letter or new?").

## Concerns

1. ~~"Same letter or new?" can't trigger yet.~~ Fixed in Goal 4.2: asked from the moment research is queued (decision 6). The fix uses in-memory state rather than `reads.list_documents`: a document with no `cases` row can also be an unreadable photo or a failed fast pass, and asking "same letter?" about those would join the retake to the blurry page.
2. **The pipe's actions don't show on the dashboard timeline.** Picking a language, creating a letter, and adding pages write no `events`, because no event types exist for them. Adding types is a contract change, so it's a team decision.
3. **Run the backend as one process.** Photo batches, ask_user waits, late-reply windows, and call-status watchers live in memory, so don't use `--workers`.
   - A restart drops open photo batches (the photos stay in `media`).
   - It also stops status messages for a call in progress.
   - Keep `--reload-dir backend`.
4. **The sandbox is slow.** Twilio takes 5–9 s to forward each message to us (photos are the slow end). Our reply goes out 1–2 s after that.
5. **The Spanish template text needs a native speaker's check**, using USCIS's official Spanish terms where they apply. That includes the new `research.slow` and `orchestrator.unavailable` templates, and a sample of translated turn replies.
6. **The sandbox delay eats into ask_user's timeout.** The user has about 30 s of real time out of 45 s. Don't go below 45.
7. ~~ask_user options are in English.~~ Fixed: the labels are translated as the question goes out (`MODEL_FAST`, 3 s cap). If that fails or is slow, they go out in English rather than delay the question. `body_en`, the `call.ask_user` event and the `questions` row keep the English labels. The late-reply message names the default as the user saw it.
8. ~~Goal 4 must not hold up ask_user replies.~~ Fixed: the orchestrator turn runs after the routing lock is released, under a separate per-number turn lock. Job reactions run in their watcher's task, outside both.
9. **Two registers in one demo (person 1).** The dashboard feed says *tú* ("Elegiste la opción"); Plan.md and every WhatsApp template use formal *usted*. Pick one, presumably *usted*.
10. **`.env.example` fix.** It used to pre-fill `DATABASE_URL_UNPOOLED` with localhost, which silently overrode `DATABASE_URL`. It's blank now. Delete that line from your own `.env` if you have it.

## Still open

- **ask_user wiring (person 4):** built per decision 1. Confirm it fits the call loop.
- **Noticing the deep pass (person 1):** research queues `research_deep` itself, so the orchestrator never gets its job ID, and no helper finds it. `case_progress` can't tell a failed deep pass from a running one. Proposal: `reads.latest_job(case_id, job_type) -> Job | None` (the query `_latest_job_status` already makes, returning the row). Needed for Goal 6.2.
- **A failed fast pass (team, Goal 8):** Plan.md has no failure rule for it. Today it's logged and the user hears nothing. Proposal: a template asking them to send the photo again.
- **Retake after `needs_better_image` (Goal 6.1):** research writes no `cases` row then, so the retake becomes a new letter with a new `case_id`. Decide whether the retake should reuse the case.
- **Plan.md wording:** Sean to check the wording of the language and photo decisions.
