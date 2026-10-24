# WhatsApp side: status, interfaces, and decisions

Owner: person 2 (Lauren). Last updated 2026-10-24, branch `lauren-goal6-consent-call`.

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
- **Finished jobs.** One watcher per queued job polls `get_job` until it's done or failed. After 45 s on the fast pass, the user gets "taking longer" (Plan.md failure rules). A finished fast pass goes on to the explanation (Goal 6, below).
- **Turns outside the lock.** The orchestrator turn runs after the per-number routing lock is released, so an ask_user reply never waits behind it (concern 8 fixed).
- **The Claude turn (4.1, 4.5).** Free text gets a reply from `MODEL_DEFAULT` with six tools (decision 8). It answers questions about a letter from the stored R1 (explanation, appointment, checklist) and the verdict. It refuses legal advice and interview interpreting per C33. It never sees a resolved ref. Text that isn't `1`/`2` while "same letter or new?" is open goes to the turn, which answers and reminds the user to pick.
- **Translation at the edges (5.1).** Inbound text is translated to English for `messages.body_en` (`MODEL_FAST`), except replies to an open ask_user question. The turn thinks and writes in English, and its reply is translated into the user's language (Spanish register: warm, simple, *usted*). If the model or the translation fails, the user gets the `orchestrator.unavailable` template, never untranslated English. ask_user option labels are translated too (concern 7).
- **Fake research agent.** `POST /dev/fake-research` claims research jobs and finishes them from the contract fixtures, so the path can be tried before the research agent is on `main`.

**Goal 6, results to the user (6.1–6.5).** Tested on fakes, including the whole path with the fake phone worker.
- **Explanation (6.1).** A finished fast pass gets one message: the explanation, the interview date and time, the checklist (who must come, what to bring, other deadlines), and "I'm checking that this letter is legitimate". The explanation and checklist are translated; the date line is a template with the date written in code ("miércoles 18 de noviembre de 2026, a las 8:30 a. m."). If translation fails, the user gets the templates and an offer to explain, never English. An unreadable photo gets a retake request with research's tip.
- **Verdict (6.2).** After the explanation, the orchestrator watches the user's events for `research.deep_done` on the case and reads R2 from that event's `job_id`. Verified and a call recommended: "it's genuine", then the consent request (`consent.requested` with `data.agency`). Verified, no call needed: says so. Suspicious: a warning with the red flags, and no call offer. Unknown: explains, no call offer, asks what the user wants.
- **Consent gate (6.3).** The consent request is a numbered template. The user's `1` (or "sí"/"yes") is answered in code, never by the model. At that moment the gate checks again: the case is verified, `official_dial_number` has a number, there's a brief, no call is running for the case, and the reply is the user's own inbound message sent after the request. Then it logs `consent.given`, queues `CallJob` with `consent_message_id` = that reply, and starts the call-status watcher with `since` from just before the enqueue. One YES is one call (C21). `2`/"no" logs `consent.declined`. Other text goes to the turn, which reminds the user to reply 1 or 2.
- **Summary (6.4).** When the call job finishes: the next steps (translated), the reference number and new deadlines (templates, dates in code). Resolved with no follow-up: a suggestion to close the letter by writing "cerrar" (the turn's `close_case`, C22). Failed (hold exceeded, or the job failed with no report) or unreachable: says why, then a new consent request (C21).
- **Memory (6.5).** After each turn reply, the orchestrator queues `memory_write` on the user's message (`source=user_said`, `source_ref` = the message ID, no proposed facts; the writer extracts them). The jobs wait in the queue until the memory writer exists (Goal 7).
- **The turn's `request_consent` tool** asks the user the same numbered question; there's no `start_call` tool (decision 9). `get_case_status` now includes the last call's outcome, reference number, next steps and deadlines.
- **Fake phone worker.** `POST /dev/fake-phone` claims the `call` jobs the orchestrator queues after a YES, plays the fake call's script on them (with a real ask_user question), and finishes each with the fixture's call report. It never dials, and it fails a job whose case has no verified number.

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
| R1 → explanation, retake request | `orchestrator/letter_result.py` |
| Noticing the deep pass, R2 → verdict | `orchestrator/verdicts.py` |
| Consent gate, call job, what to offer after the call | `orchestrator/consent.py` |
| Post-call summary | `orchestrator/call_summary.py` |
| Dates and times in the user's language | `orchestrator/dates.py` |
| The Claude turn, its tools, its prompt | `orchestrator/turn.py`, `tools.py`, `prompts.py` |
| Translation to and from English | `translation/translate.py` |
| Fake phone agent and `POST /dev/fake-call`; fake research and `POST /dev/fake-research`; fake phone worker and `POST /dev/fake-phone` (dev only) | `backend/app/dev/` |
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

**Call jobs (H2).** The orchestrator queues a `CallJob` only from the user's numbered YES, after checking that the case is verified and has an official number. `consent_message_id` is that YES. When the call is over:
- log `call.ended`, save the report on the call, then **finish the job with the `CallReport` as its result**. The post-call summary comes from the finished job.
- If the call couldn't happen, fail the job. The user is told and asked whether to try again, with fresh consent.
- Don't message the user after the call yourself; the summary is the orchestrator's.

### Dashboard (person 1)

What to expect in `messages`:
- `sender` is `relay` for templates and `orchestrator` for free text.
- Templated rows carry `template` and an English `body_en`.
- Incoming Spanish text has an English `body_en` (`MODEL_FAST`). It's `null` only if the translation failed, or for a reply to an open ask_user question that isn't a bare number. A bare number is logged as is.
- A user's reply to an ask_user question has `question_id` set.
- The letter explanation and the post-call summary are `orchestrator` rows with `case_id` set and no `template`. The verdict, consent question, retake request and the after-call offers are `relay` templates with `case_id`.
- The user's YES to a call is an ordinary inbound row; the call's `consent_message_id` points at it.

New events from the orchestrator: `consent.requested` (`data.agency`), `consent.given` and `consent.declined` (`data.consent_message_id`). The fake phone worker's calls log the same call events as the fake call.
- Before a user picks a language, incoming messages are logged as the detected language, or `en`. The bilingual language menu is logged as `es`.

The fake call (dev only) leaves rows like a real one: a case, a brief, a failed `call` job, a call, its events, and a `case.closed` event. It also adds one outbound note, `"[dev] Fake call started…"`, that was never sent to WhatsApp. That note is what the fake call's consent pointer references.

### Research (person 3)

- **H1 is live.** When a batch of photos closes, the orchestrator mints `case_id` and queues `ResearchFastJob` (one document, `user_language` set, `user_note_en` not yet). Create the `cases` row with that ID.
- **A fast job can run twice for one case.** When the user adds a page after you've claimed the job, the orchestrator queues another `research_fast` with the **same `case_id` and document**. Your second run must not fail on the existing `cases` row: the current `insert_case` on `research_agent` (and `writes.research.create_case`) is a plain insert. The orchestrator ignores the older job's result.
- **The orchestrator reacts to the fast job you finish,** so finish it after the `cases` row and R1 are saved and the deep job is queued (`research_agent` already does this).
- **The orchestrator finds R2 through your `research.deep_done` event.** Set `job_id` on it (the deep job's ID) and log it after the job is finished with R2, the verification and the brief saved. Without `job_id`, the user never hears the verdict.
- **Event types must be in `EventType`.** `research_agent` also logs `research.fast_slow`, `research.fast_failed`, `research.deep_failed`, `research.search`, `research.fetch` and `research.check`, which aren't in the contracts yet. `append_event` will refuse them. Adding types is a contract change (team decision). The orchestrator already sends "taking longer" itself at 45 s, so `research.fast_slow` isn't needed for that.
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
8. **The turn's tools.** `list_active_cases`, `get_case_status`, `get_profile`, `close_case`, `request_consent`, `set_language`. Research starts from photos, so there's no `start_research` tool. One turn is one tool-runner loop: up to 6 model calls, 30 s per call, 60 s overall. `effort: low`, and the system prompt is cached.
9. **No `start_call` tool (Plan.md lists one).** A call starts only from the user's numbered `1` (or "sí"/"yes") to a consent request, handled in code (`orchestrator/consent.py`), so rule 4 and C21 never depend on the model. The model can ask for consent (`request_consent`), not give it. A "yes" in a longer sentence goes to the turn, which asks the user to reply 1. The open request is held in memory, one per user; a restart forgets it.
10. **R2 is found through `research.deep_done`, not a new helper.** Research queues the deep job itself, so the orchestrator watches the user's events for `research.deep_done` on the case (from the fast job's creation, about once a second, up to 15 minutes) and reads R2 from the event's `job_id`. It starts after the explanation is sent, so the verdict never arrives first. This replaces the `reads.latest_job` proposal.
11. **Dates in messages are written in code, in templates.** The interview date, deadlines, and the post-call dates are formatted per language (`orchestrator/dates.py`) and sent in relay templates; only the explanation, checklist, red flags and next steps are translated. A language without month names in `dates.py` gets ISO dates.
12. **After the call.** Resolved with no follow-up: suggest closing, by text; the user closes it through the turn (C22). Failed, unreachable, or a failed job: say why, then send a new consent request at once (C21). Partial, or resolved with follow-up: the summary only.
13. **`memory_write` after each turn reply** carries the user's message ID as `source_ref` and no proposed facts; the memory writer reads the message and extracts the facts (Goal 7.1). Research and the phone agent queue their own with their facts (Plan.md → Jobs).
14. **"Same letter or new?" answers come before consent answers.** If both are open, a `1` answers the photo question. It never starts a call by mistake; the consent request stays open.

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
3. **Send a photo of a letter.** Expect "Recibido…", then in the uvicorn log `Research queued`, and about 5 s later `Fast pass done`. The dashboard should show the case with the fixture's I-797C, and about 10 s later the verdict. On WhatsApp you get the explanation, then the verdict and the consent question; for the call itself, see the next section.
4. **Also try:** a second photo a minute later (you get "same letter or new?").

## Try the whole path (fake research + fake phone)

1. **Set things up:** `DEV_ENDPOINTS=true` and `TWILIO_MOCK_AGENCY_NUMBER` in `.env` (without it the case has no official number, so no call is offered), restart uvicorn, and pick a language from your phone.
2. **Start both fakes** from the same machine: `POST /dev/fake-research` and `POST /dev/fake-phone` (PowerShell: `Invoke-RestMethod -Method Post -Uri http://localhost:8000/dev/fake-phone`). Don't run them while a real research worker or phone agent uses the same database.
3. **Send a photo of a letter.** Expect "Recibido…", then about 5 s later the explanation with the interview date and checklist, then about 10 s later "es auténtica" and the consent question.
4. **Reply `1`.** Expect "Gracias. Preparo la llamada…", "Estoy llamando a USCIS ahora", the menu question (reply `2`), one "Sigo en espera…", "Contestó una persona…", and then the summary with reference number R-55821.
5. **Also try:** `2` to the consent question (no call), and text instead of a number (a reminder to reply 1 or 2).

## Concerns

1. ~~"Same letter or new?" can't trigger yet.~~ Fixed in Goal 4.2: asked from the moment research is queued (decision 6). The fix uses in-memory state rather than `reads.list_documents`: a document with no `cases` row can also be an unreadable photo or a failed fast pass, and asking "same letter?" about those would join the retake to the blurry page.
2. **The pipe's actions don't show on the dashboard timeline.** Picking a language, creating a letter, and adding pages write no `events`, because no event types exist for them. Adding types is a contract change, so it's a team decision.
3. **Run the backend as one process.** Photo batches, ask_user waits, late-reply windows, and call-status watchers live in memory, so don't use `--workers`.
   - A restart drops open photo batches (the photos stay in `media`).
   - It also stops status messages for a call in progress.
   - Keep `--reload-dir backend`.
4. **The sandbox is slow.** Twilio takes 5–9 s to forward each message to us (photos are the slow end). Our reply goes out 1–2 s after that.
5. **The Spanish template text needs a native speaker's check**, using USCIS's official Spanish terms where they apply. That includes the new `research.slow`, `orchestrator.unavailable`, `letter.*`, `verification.*`, `consent.*` and `summary.*` templates, and a sample of translated replies, explanations and summaries.
6. **The sandbox delay eats into ask_user's timeout.** The user has about 30 s of real time out of 45 s. Don't go below 45.
7. ~~ask_user options are in English.~~ Fixed: the labels are translated as the question goes out (`MODEL_FAST`, 3 s cap). If that fails or is slow, they go out in English rather than delay the question. `body_en`, the `call.ask_user` event and the `questions` row keep the English labels. The late-reply message names the default as the user saw it.
8. ~~Goal 4 must not hold up ask_user replies.~~ Fixed: the orchestrator turn runs after the routing lock is released, under a separate per-number turn lock. Job reactions run in their watcher's task, outside both.
9. **Two registers in one demo (person 1).** The dashboard feed says *tú* ("Elegiste la opción"); Plan.md and every WhatsApp template use formal *usted*. Pick one, presumably *usted*.
10. **`.env.example` fix.** It used to pre-fill `DATABASE_URL_UNPOOLED` with localhost, which silently overrode `DATABASE_URL`. It's blank now. Delete that line from your own `.env` if you have it.

## Still open

- **ask_user wiring (person 4):** built per decision 1. Confirm it fits the call loop.
- **`job_id` on `research.deep_done` (person 3):** the orchestrator needs it to read R2 (decision 10). The fake research agent sets it.
- **A failed or missing deep pass (team, Goal 8):** no failure rule. Today it's logged, and the user hears nothing after "I'm checking…".
- **A failed fast pass (team, Goal 8):** Plan.md has no failure rule for it. Today it's logged and the user hears nothing. Proposal: a template asking them to send the photo again.
- **Retake after `needs_better_image`:** the retake request is built (6.1). Research writes no `cases` row then, so the retake becomes a new letter with a new `case_id`. Decide whether the retake should reuse the case.
- **`call_recommended` false with a verified letter:** the user hears "no need to call" and isn't offered a call. They can still ask for one, and the turn's `request_consent` works.
- **Plan.md wording:** Sean to check the wording of the language and photo decisions.
- **Plan.md's orchestrator tool list (Sean):** it names `start_call`; decision 9 replaces it with the consent gate in code. Proposal: list `request_consent` only and note that the user's YES starts the call.
