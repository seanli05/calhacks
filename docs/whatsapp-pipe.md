# WhatsApp side: status, interfaces, and decisions

Owner: person 2 (Lauren). Last updated 2026-10-24, branch `lauren/agentic-routing`.

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
  - **Cancelled** (the phone agent moved on): the question is closed quietly, and the next reply goes to normal routing.
  - **Words while the question is open** ("why are you asking?", "the first one", "hang up"): they go to the orchestrator turn, which sees the question and can answer it (`answer_call_question`), hang up, or just reply (Agentic routing, below). Only without `ANTHROPIC_API_KEY` is the user asked again for a number.
  - **Priority:** an open question gets the user's bare number before anything else, answered in code, never through a model.
- **Call status (P2, C36).** The orchestrator watches a call's events and sends five kinds of message: dialing, on hold (at most every 10 minutes), human detected (always, at once), a second ring of the applicant (`call.user_dialed` after a missed ring: "USCIS is still waiting for you. I'm calling you again"; the first ring is covered by human detected), and unreachable. A call that follows the user's YES gets no "dialing": `consent.given` already says we're calling.
- **Fake phone agent.** `POST /dev/fake-call` plays a scripted call, so all of the above can be seen on a phone before the real phone agent exists.

**Goal 4, letter to research (4.2–4.4).** Tested on fakes.
- **Research starts.** When a batch of photos closes, the orchestrator mints a `case_id` and queues `research_fast` for the new document.
- **"Same letter or new?"** It's asked from the moment research is queued, not only once a case exists (concern 1 fixed). Answering "same letter" re-runs the fast pass in the same case. If the last fast job is still queued, research reads the new pages anyway, so nothing more is queued.
- **Finished jobs.** One watcher per queued job polls `get_job` until it's done or failed. After 45 s on the fast pass, the user gets "taking longer" (Plan.md failure rules). A finished fast pass goes on to the explanation (Goal 6, below).
- **Turns outside the lock.** The orchestrator turn runs after the per-number routing lock is released, so an ask_user reply never waits behind it (concern 8 fixed). It runs under the user's conversation lock instead (Pacing, below).
- **The Claude turn (4.1, 4.5).** Free text gets a reply from `MODEL_DEFAULT` with seven tools (decision 8; `ask_official_source` added Oct 24, below). It answers questions about a letter from the stored R1 (explanation, appointment, checklist) and the verdict. It refuses legal advice and interview interpreting per C33. It never sees a resolved ref. Text that isn't `1`/`2` while "same letter or new?" is open goes to the turn, which can answer it in words (`answer_same_or_new`) or answer the message and remind the user to pick.
- **Translation at the edges (5.1).** Inbound text is translated to English for `messages.body_en` (`MODEL_FAST`), except a bare number, which never waits on a model call. The turn thinks and writes in English, and its reply is translated into the user's language (Spanish register: warm, simple, *usted*; Dari: below). If the model or the translation fails, the user gets the `orchestrator.unavailable` template, never untranslated English. ask_user option labels are translated too (concern 7).
- **Glossary grounding (5.3).** Every translation prompt (inbound, replies, ask_user labels) lists the glossary terms the text uses, read with `get_glossary(lang)` and cached 10 minutes per language, so replies say "entrevista de asilo" and "oficial de asilo" the way USCIS does. Matching ignores case, accents and a plural ending ("interpretes" finds "intérprete"); English terms also match their verb forms ("dismissed" brings in "dismissal", so the Dari never drifts into the word for a denial); Dari text matches across ي/ی, ك/ک, the zero-width non-joiner and the plurals ها/ان. A `<ref:...>` placeholder never matches. If the glossary read fails or takes over 2 s, the text is translated without it, and the read is retried after 30 s. The glossary must be loaded on the database (`python -m app.glossary.load`, again after a reset); an empty table means no grounding, not an error.
- **Faithful or not used (5.4).** A translation must keep every number's value (in any digits: "18" and "۱۸" agree), add no number (a year added to "Nov 18" is caught; "ten days" may come back as "۱۰ روز"), and keep every `-`/`•` list item. If not, it's retried once with a reminder, then dropped, and the caller falls back to its template, as for a failed call. Applies both ways and to ask_user labels (no retry there; they fall back to English labels).
- **Dari (`fa`), the demo language (1.1–1.7).** Every template has Afghan Dari text (`relay/templates.py`), in the polite شما, with the glossary's words and USCIS's Dari page's (ادارهٔ USCIS, معلومات, دوسیه, مشورهٔ حقوقی, نمایندهٔ معتبر) and Persian digits. The language menu lists it as `3 دری` (English stays `2`). Detection maps Dari and Farsi to `fa` (also `prs`/`fas`), and the one-tap confirm names دری. Dates read "چهارشنبه ۱۸ نومبر ۲۰۲۶" and times "۸:۳۰ صبح" / "۴:۳۰ بعد از ظهر" / "۸:۰۰ شب" (`orchestrator/dates.py`; month names from USCIS's Dari page and UNAMA's Dari reports, times from USCIS's Dari page and Da Afghanistan Bank). Replies accept Persian digits (`۱`, `۲`) and the yes/no words بلی, بله, آری, آره / نخیر, نه, نی. The translator's Dari register asks for Afghan words over Iranian ones (بلی, تشکر, حالا, معلومات, تیلفون, دوسیه, مشوره, محکمه, ضرورت; سند هویت for ID, not تذکره), Afghan month names, and never a solar-calendar date. Right-to-left text gets Unicode direction isolates (U+2068 … U+2069) around every Latin run (USCIS, I-797C, links, phone numbers), added by `render` and by the translator (`translation/script.py`); without them a phone shows "I-797C" as "797C-I". Not yet read by a Dari checker (concern 11).
- **Fake research agent.** `POST /dev/fake-research` claims research jobs and finishes them from the contract fixtures, so the path can be tried before the research agent is on `main`.

**Goal 6, results to the user (6.1–6.5).** Tested on fakes, including the whole path with the fake phone worker.
- **Explanation (6.1, C46).** A letter whose R1 is `suspicious` (research's instant checks) gets `letter.looks_like_scam` and nothing more: no explanation, no call offer, no second warning from the verdict. Otherwise a finished fast pass gets `letter.double_checking` and "typing…", and the explanation (the summary, the interview date and time, the checklist) is held by the verdict watcher (`Verdicts.watch(..., explain=...)`) and sent with the verdict, as the `lead` of its template (`send_template(..., lead=)`), so the user gets one message. The explanation and checklist are translated; the date line is a template with the date written in code ("miércoles 18 de noviembre de 2026, a las 8:30 a. m."). If translation fails, the user gets the templates and an offer to explain, never English. An unreadable photo gets a retake request with research's tip.
- **Verdict (6.2, C46).** Once the letter is read, the orchestrator watches the user's events for `research.deep_done` on the case and reads R2 from that event's `job_id`. Verified: the explanation and "it's genuine", with no call offer (C44); the turn offers a call later, only if the user asks or shows a need for one. Verified with no number to call (`call_recommended` false): the explanation, and that no call is needed. Suspicious: a warning with the red flags, never the explanation or a call offer. Unknown, or a failed deep pass: the explanation with a gentle caution (`verification.unknown`). No verdict within 60 s (`EXPLAIN_AFTER_S`): the explanation with `letter.still_checking`, and the verdict goes alone when it comes.
- **Consent gate (6.3, C43).** The consent request is a numbered template, or the turn's own question when the user asked for the call (below). The user's `1` (or "sí"/"yes") is answered in code, with no model call. A yes or no in words ("sí, llámelos") goes to the turn, which may pass it on with `answer_call_consent(case_id, answer, user_words)`; the gate refuses unless a request is open for that case, the user's latest message is their own and came after the request, and `user_words` appear in that message (its English or as written). The prompt asks for a clear yes in the latest message itself: a hedge or a question ("maybe, what will you ask?") is answered and the question asked again. At that moment the gate checks again: the case is verified, `official_dial_number` has a number, there's a brief, no call is running for the case. Then it logs `consent.given` (`data.consent_message_id`, plus `data.via = "words"` for an answer in words), queues `CallJob` with `consent_message_id` = that reply, and starts the call-status watcher with `since` from just before the enqueue. One YES is one call (C21). A no logs `consent.declined`.
- **Summary (6.4).** When the call job finishes, one message: the next steps (translated), the reference number and new deadlines (templates, dates in code). Resolved with no follow-up: it ends with a suggestion to close the letter by writing "cerrar" (the turn's `close_case`, C22). Failed (hold exceeded, or the job failed with no report): why, and a new consent request (C21), in one template (`summary.call_failed_retry`). Unreachable: the new consent request alone, since `call.user_unreachable` already said why. If another numbered question is open, the retry isn't offered and the summary goes alone.
- **Memory (6.5).** After each turn reply, the orchestrator queues `memory_write` on the user's message (`source=user_said`, `source_ref` = the message ID, no proposed facts; the writer extracts them). The memory writer (Goal 7, below) drains them.
- **The turn's `request_consent` tool** opens the same request without sending the template (`ConsentGate.request(..., send=False)`), and the turn's reply asks it in the model's own words: the goal, holding and ringing them, never sharing their case numbers, "shall I go ahead?". `ConsentGate.asked` then marks when that reply went out, so only a later message answers it; with no reply (or a failed translation) the `consent.request` template goes out instead (`send_question`). Since Oct 24: "Can you call USCIS again?" got the rigid "1 Yes, call / 2 No, thanks" template. Offers the agent makes itself (the verdict, a retry after a failed call) keep the template. There's no `start_call` tool (decision 9). The `answer_*` tools answer an open question in words (Agentic routing, below). `get_case_status` now includes the last call's outcome, reference number, next steps and deadlines.
- **Research's question (C39, added overnight Oct 24 by person 1's session).** An R1 with `needs_user_input` (the photos look like different letters) gets research's `question_en`, translated, instead of an explanation; the verdict isn't watched yet. The user's next text, in English, re-runs the fast pass on the same case as `user_note_en`, and research reads it as data. `letter_result.py` (`LetterQuestion`), `letters.py` (`answer_question`), the pipe's routing (after "same letter or new?", before consent).
- **Official-source questions (C38, same).** The turn's `ask_official_source` tool queues a `research_question` job and tells the user it's looking. When the job finishes, `orchestrator/research_questions.py` sends the answer translated with up to three source URLs. Declines (legal advice, the asylum claim, not found) and failures get fixed templates, so they never depend on a model or a translation.
- **Fake phone worker.** `POST /dev/fake-phone` claims the `call` jobs the orchestrator queues after a YES, plays the fake call's script on them (with a real ask_user question), and finishes each with the fixture's call report. It never dials, and it fails a job whose case has no verified number.

**Agentic routing (Oct 24, evening): hear → decide → act.** Before this, whichever numbered question was open captured the user's message: "what is this about?" mid-call got "reply 1 or 2", and "yes, call them" didn't count. Now:
- **Code answers what's instant and certain:** the language pick, photos, a bare number or yes/no word to the one open numbered question (an ask_user reply stays under 3 s and never goes through a model), and research's question about the letter (C39, any text).
- **Everything else reaches the turn**, including while ask_user, consent, "same letter or new?" or "may I save this?" is open. The turn's context has an `<open_questions>` block (kind, question or case ID, English options), built by `InboundPipe.open_questions` from the same sources as `question_open` (`orchestrator/open_questions.py`).
- **Guarded answer tools** (`tools.py`), each refusing with the reason when the move isn't legal now: `answer_call_question(question_id, choice)` (the question is open and the user's; `AskUser.answer`, which `handle_reply` also uses), `answer_call_consent` (Consent gate, above), `answer_same_or_new(choice)`, `answer_save_facts(answer)`.
- **Answer and act in one message.** "Yes, and do I bring my kids?" records the consent and answers the question. An answer tool sends no confirmation of its own (`confirm=False` on `ConsentGate.answer`, `FactConsent.answer`, the pipe's `_settle_same_or_new`): its result tells the model what happened, the reply says it, and the confirming template (`consent.given`, `memory.saved`, …) goes out only if the turn ends with no reply to send. Before, the template went out and the model often confirmed again ("Done, I saved it." then "I've saved that.").
- **Letters not read yet.** Research creates the `cases` row only when the fast pass finishes, so the turn's context has a `<letters_in_progress>` block: photos still arriving (`PhotoBatcher.is_open`), or the case being read (`Letters.reading_case`). The prompt says the letter is in hand and its explanation is coming. Before, "No other pages" right after a photo got "I don't see your letter… please send it again".
- **Mid-call requests** ("hang up", "let me listen") reach `hang_up_call` and `listen_to_call` even while ask_user is open.
- **"May I save this?"** left unanswered by the turn stays open for one more message, then closes (decision 16).
- **Voice (Oct 24, after a phone run).** The turn's prompt casts it as a caring, patient helper for anxious families: warm and plain, usually two to four sentences, acknowledging worry briefly, never form-like wording ("Reply yes or no", "the question had already closed").

**Pacing (Oct 24, after the first phone test).** The first real run sent the explanation, a turn reply, "may I save this?", the verdict and the call question within a minute, with two 1/2 questions open at once. `orchestrator/conversation.py` keeps that from happening. Tested on fakes.
- **One speaker at a time.** A turn and each proactive message (explanation, verdict, post-call summary, an official-source answer) hold the user's conversation lock while they're built and sent. A turn's reply never crosses, or repeats, a message that went out meanwhile. Call-status messages and ask_user don't take it: they can't wait.
- **One numbered question at a time.** `InboundPipe.question_open` is the one check (consent, "may I save this?", "same letter or new?", research's question, ask_user). The turn's `request_consent` refuses while another question is open. This fixes a real bug: the verdict's consent request could go out while "may I save this?" was open, and a "1" meant for "save it" started a call. (The verdict no longer asks at all: C44.)
- **"May I save this?" waits for a quiet moment.** Still only after a turn (C15), and now also not while research is reading or checking the user's letter, a call is running, or a consent request is waiting.
- **Shorter messages.** `letter.received` no longer asks "are there more pages?" (it invited a "no, that's it" that cost a turn). The consent request dropped about half its words. The turn's prompt asks for one to three sentences, no repeats of what was already sent, and a few words for an acknowledgement.
- **"Typing…" while the user waits (Oct 24).** During a turn, the fast pass on their letter (until the result, or 45 s when "taking longer" goes out), and an official-source lookup (until the answer, at most 90 s), the user sees WhatsApp's typing indicator on their latest message, which also marks it read. It's Twilio's typing indicator (public beta, `POST messaging.twilio.com/v3/Indicators/Typing.json`, account SID and auth token). It sends no message and writes no row. WhatsApp clears it after 25 s or when our reply arrives, so `Conversation` re-sends it every 20 s while the work runs. It's best effort: a failure is logged once as a warning (then at debug) and never holds up a reply. Not shown during the deep pass (1–3 minutes, and the user was already told "I'll write in a few minutes") or a call (call-status messages cover it). **Not yet tried on a real phone or the sandbox.**
- **No bursts (Oct 24, evening).** `test_whatsapp_pipe.py` drives the demo path on the fakes at their real pacing (letter → explanation → verdict + consent → YES → the fake call → summary; per outcome; and a question after the call) and fails if two messages go out less than 5 s apart with nothing from the user between (human detected and ask_user excepted: they can't wait). It found four, now fixed: `consent.given` then `call.dialing` 0.6 s later (no dialing message after a YES; `consent.given` now says "I'm calling USCIS now"); the summary then the close suggestion, and the failed-call summary then the new consent request (each one message now); and a turn's reply then "may I save this?" (the question now ends the reply, decision 16).
- **Still open: the explanation itself.** It's research's `explanation_en` plus the checklist, and they overlap. [handoff-shorter-messages.md](handoff-shorter-messages.md) asks person 3 for a short `summary_en` (the dashboard keeps the full explanation) and a short R2 call goal.

**Goal 7, the memory writer (7.1–7.6).** Tested on fakes.
- **Worker (7.1).** Starts with the app when `MEMORY_WORKER=true` (the default) and `ANTHROPIC_API_KEY` is set. It claims `memory_write` jobs one at a time, oldest first, so the backlog queued since Goal 6 drains on first start. A `user_said` job reads its message (`source_ref`) and the assistant message before it, and one `MODEL_FAST` structured-output call proposes facts, a category each, and profile fields (decision 13). Research and phone jobs carry `proposed_facts`; they need no model call. Every job ends `done` (with saved and held fact IDs, and counts of dropped and duplicate facts) or `failed`. A message with no words ("1"), no English text, or deleted since is finished as skipped.
- **Filter (7.2, `memory/filters.py`).** Runs on every fact, whoever proposed it. Asylum claim details (origin, nationality, what happened, why they left) and identifiers (A-Number, receipt number, SSN, phone, email, date of birth, any `<ref:…>`) are dropped, by the model's category and by markers in code. Immigration, income and health facts are `sensitive` and `pending_consent` (C15, C25); anything that mentions the immigration case is filed as immigration whatever its proposed category. Facts already stored (active or pending) are skipped by normalized text; supersede stays out (C28).
- **Profile (7.3).** `county` (without "County"), `household_size`, `contact_preference`: short keys, plain values, only when the user says them.
- **Events (7.4).** `memory.fact_saved` or `memory.fact_pending_consent`, `data` = `{"fact_id"}` only, `source` = `memory_writer`. Logs carry IDs and counts, never fact text.
- **Asking before saving (7.5).** At the end of a turn's plain reply, at a quiet moment (no other numbered question open, research and calls done), the same message asks `memory.ask_save`: the pending facts (up to 5) as a translated bullet list, "1 yes / 2 no". A 1/2 or yes/no is handled in code; a clear answer in words goes through the turn's `answer_save_facts`. Yes: `memory.consent.confirm_facts` marks them active and logs `memory.fact_saved`. No: `decline_facts` deletes them, with no event. See decisions 15–17.

**Stored results are read through the contract models.** The turn's tools, the consent gate and the letter question read R1, the verification, the brief, the call report and job payloads with `FastResult`, `Verification`, `CaseBrief`, `CallReport` and `jobs.payload_of`. A row that no longer validates (written before a contract change) is logged with its IDs and treated as missing: the tool says "not available", the consent request is the generic one to USCIS, the letter question keeps no documents.

`pytest` covers every routing path on fakes, with no network.

| Piece | File |
|---|---|
| Webhook: Twilio signature check, queues the work, empty TwiML in ~5 ms | `backend/app/relay/webhook.py` |
| The pipe: user row → media saved → message logged → routed | `backend/app/orchestrator/pipe.py` |
| Language pick (detection uses `MODEL_FAST`) | `orchestrator/language.py`, `translation/detect.py` |
| Grouping photos into letters (C20) | `orchestrator/photos.py` |
| Sending and logging: `send_template`, `send_text` | `relay/outbound.py` |
| Twilio wrapper: REST send, split over 1,600 chars, media download | `relay/whatsapp.py` |
| Message templates, `es` + `en` + `fa` (Dari) | `relay/templates.py` |
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
| What's open for the turn to answer (`<open_questions>`) | `orchestrator/open_questions.py` |
| Official-source answers to the user's questions (C38) | `orchestrator/research_questions.py` |
| Memory writer: job worker, extraction, the C25/C34 filter, profile, events | `memory/worker.py`, `writer.py`, `extract.py`, `filters.py` |
| Asking before saving (C15): the question and its answer | `orchestrator/fact_consent.py`, `memory/consent.py` |
| Translation to and from English; glossary terms in the prompts | `translation/translate.py`, `glossary.py` |
| Digits, direction isolates, the numbers-kept check | `translation/script.py` |
| Preset glossary (person 2 owns it): `terms.csv`, loaded with `python -m app.glossary.load` | `glossary/` |
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
- **To stop waiting, cancel the task awaiting `ask_user`** (a new menu prompt, hold, a person picked up, a hang-up). The relay closes the question and re-raises `CancelledError`, even if the close fails (it logs that). The user gets no message, no `call.ask_user_timeout` is logged, and no late-reply window opens, so their next reply (e.g. a `1` to a retry consent request) goes to normal routing.
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
- Incoming Spanish text has an English `body_en` (`MODEL_FAST`). It's `null` only if the translation failed. A bare number is logged as is.
- A user's bare-number reply to an ask_user question has `question_id` set. Words answered through the turn don't; the `call.ask_user_answered` event records the choice.
- The letter explanation and the post-call summary are `orchestrator` rows with `case_id` set and no `template` (a close suggestion is at the end of the summary). The verdict, consent question, retake request and a failed call's summary with its retry offer (`summary.call_failed_retry`) are `relay` templates with `case_id`. "May I save this?" is at the end of a turn's reply, an `orchestrator` row.
- The user's YES to a call is an ordinary inbound row, a `1` or words (C43); the call's `consent_message_id` points at it, and `consent.given` has `data.via = "words"` for words.

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
7. **The fake research agent lives in `dev/`, behind the same guard as the fake call.** `POST /dev/fake-research` claims `research_fast` and `research_deep` for 30 minutes (or `{"minutes": n}`), finishing each from `tests/fixtures/contracts/` after 5 s and 10 s. It saves the verification with **our mock agency line** (`TWILIO_MOCK_AGENCY_NUMBER`), never the fixture's real USCIS number. With that unset, the phone is empty and `official_dial_number` refuses the case. It claims from the shared queue, so don't run it while a real research worker uses the same database. It queues no `memory_write`.
8. **The turn's tools.** `list_active_cases`, `get_case_status`, `get_profile`, `close_case`, `request_consent`, `set_language`; later `ask_official_source`, `listen_to_call`, `hang_up_call`, and the four `answer_*` tools (Agentic routing). Research starts from photos, so there's no `start_research` tool. One turn is one tool-runner loop: up to 6 model calls, 30 s per call, 60 s overall. `effort: low`, and the system prompt is cached.
9. **No `start_call` tool (Plan.md lists one).** A call starts only from the user's own YES to a consent request: a `1`/`۱` (or "sí"/"yes"/"بلی") handled in code, or, since Oct 24 (C43), a yes in words the turn relays with `answer_call_consent`, which code checks against the user's latest message (`orchestrator/consent.py`). The model can ask for consent (`request_consent`) and pass on the user's answer, never give it. The open request is held in memory, one per user; a restart forgets it.
10. **R2 is found through `research.deep_done`, not a new helper.** Research queues the deep job itself, so the orchestrator watches the user's events for `research.deep_done` on the case (from the fast job's creation, about once a second, up to 15 minutes) and reads R2 from the event's `job_id`. It starts after the explanation is sent, so the verdict never arrives first. This replaces the `reads.latest_job` proposal.
11. **Dates in messages are written in code, in templates.** The interview date, deadlines, and the post-call dates are formatted per language (`orchestrator/dates.py`) and sent in relay templates; only the explanation, checklist, red flags and next steps are translated. A language without month names in `dates.py` gets ISO dates; every language in `LANGUAGES` has them (a test checks), so no ISO date lands inside Dari.
12. **After the call.** Resolved with no follow-up: suggest closing, by text; the user closes it through the turn (C22). Failed, unreachable, or a failed job: say why, then send a new consent request at once (C21). Partial, or resolved with follow-up: the summary only.
13. **`memory_write` after each turn reply** carries the user's message ID as `source_ref` and no proposed facts; the memory writer reads the message and extracts the facts (Goal 7.1). Research and the phone agent queue their own with their facts (Plan.md → Jobs).
14. **"Same letter or new?" answers come before consent answers.** If both are open, a `1` answers the photo question. It never starts a call by mistake; the consent request stays open.
15. **The orchestrator asks about pending facts; the memory writer acts on the answer.** The orchestrator never writes `facts`: the pipe passes the user's 1 or 2 to `app.memory.consent` (`confirm_facts`, `decline_facts`), the memory writer's public entry point. Both run in the one process. No job is involved, because `MemoryWriteJob` can't say "confirm these facts" without a contract change.
16. **One question for all pending facts, asked once.** It goes at the end of a turn's reply (since Oct 24, so it isn't a second message right after it) and only if no other numbered question is open (ask_user, consent, "same letter or new?", research's question), so a `1` is never read as the wrong answer. Since Oct 24 it also waits while research or a call is still going to message the user (Pacing, above). Each fact is asked about once per process. A reply that isn't 1/2 or yes/no goes to the turn, which may answer it (`answer_save_facts`); if it doesn't, the question stays open for one more message (the user may have asked what it means), then closes; the facts stay pending and show as "waiting for your OK" on the dashboard. If the translation fails, nothing is asked (rule 6); the next turn tries again. The open question lives in memory, and a restart forgets it.
17. **A declined fact is deleted with `writes.memory.delete_fact`, which logs no event.** `deletes.delete_fact` logs `fact.deleted` ("User deleted a fact"), which misreads a declined save (person 1's open decision 6). The fact's `memory.fact_pending_consent` line then falls back to the feed's generic text ("We'll ask you before saving a fact"), with no deleted date. **The helper is drafted in person 1's `db/writes/memory.py` and needs their OK before merge.**
18. **The memory worker handles one job at a time.** Each job checks new facts against stored ones, and two jobs for the same user running together could both save the same fact.
19. **The consent request's goal is translated as the call's task.** Alone, "Confirm the interview is still scheduled" came back in Dari as "تأیید کنید…" ("please confirm…"), a request to the user, inside the message the user consents to (rule 4). `ConsentGate` passes `GOAL_CONTEXT` to the translator, and the goal now reads "تأیید اینکه…" ("confirming that…").
20. **Dari is option 3 on the language menu**, after Español and English, so the English Test Protocol's "reply 2 for English" still holds. The demo phone is pre-staged with Dari picked (3.1), so the menu position doesn't show in the demo.

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
4. **Also try:** words instead of a number ("why are you asking?", then "the first one"): the turn answers, then picks the option; "hang up" ends the call. A number after the 45 s timeout gets the late-reply message.
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
4. **Reply `1`.** Expect "Gracias. Estoy llamando a USCIS ahora…", the menu question (reply `2`), one "Sigo en espera…", "Contestó una persona…", and then the summary with reference number R-55821.
5. **Also try:** `2` to the consent question (no call); "maybe, what will you ask them?" (an answer, and the question again, no call), then "yes please call" (the call starts).

## Concerns

1. ~~"Same letter or new?" can't trigger yet.~~ Fixed in Goal 4.2: asked from the moment research is queued (decision 6). The fix uses in-memory state rather than `reads.list_documents`: a document with no `cases` row can also be an unreadable photo or a failed fast pass, and asking "same letter?" about those would join the retake to the blurry page.
2. **The pipe's actions don't show on the dashboard timeline.** Picking a language, creating a letter, and adding pages write no `events`, because no event types exist for them. Adding types is a contract change, so it's a team decision.
3. **Run the backend as one process.** Photo batches, ask_user waits, late-reply windows, and call-status watchers live in memory, so don't use `--workers`.
   - A restart drops open photo batches (the photos stay in `media`).
   - It also stops status messages for a call in progress.
   - Keep `--reload-dir backend`.
4. **The sandbox is slow.** Twilio takes 5–9 s to forward each message to us (photos are the slow end). Our reply goes out 1–2 s after that.
5. **The Spanish template text needs a native speaker's check**, using USCIS's official Spanish terms where they apply. That includes the new `research.slow`, `orchestrator.unavailable`, `letter.*`, `verification.*`, `consent.*`, `summary.*` and `memory.*` templates, and a sample of translated replies, explanations and summaries.
6. **The sandbox delay eats into ask_user's timeout.** The user has about 30 s of real time out of 45 s. Don't go below 45.
7. ~~ask_user options are in English.~~ Fixed: the labels are translated as the question goes out (`MODEL_FAST`, 3 s cap). If that fails or is slow, they go out in English rather than delay the question. `body_en`, the `call.ask_user` event and the `questions` row keep the English labels. The late-reply message names the default as the user saw it.
8. ~~Goal 4 must not hold up ask_user replies.~~ Fixed: the orchestrator turn runs after the routing lock is released, under a separate per-number turn lock. Job reactions run in their watcher's task, outside both.
9. **Two registers in one demo (person 1).** The dashboard feed says *tú* ("Elegiste la opción"); Plan.md and every WhatsApp template use formal *usted*. Pick one, presumably *usted*.
10. **`.env.example` fix.** It used to pre-fill `DATABASE_URL_UNPOOLED` with localhost, which silently overrode `DATABASE_URL`. It's blank now. Delete that line from your own `.env` if you have it.
11. **The Dari text needs a fluent checker's read on a real phone (1.9)**: every template, right-to-left rendering included, and the sample translations. The review sheet is [docs/dari-review.md](dari-review.md), with the open wording questions first (نومبر, the times of day, ترجمان, the legal-help line).
12. **One phone test fails with Dari until person 4 lands their side.** `test_every_language_users_write_in_has_a_join_prompt[fa]` needs a Dari join prompt in `phone/call_lines.JOIN_PROMPTS` (ask 2.3); until then a Dari user hears the English prompt. (`test_phone_smoke.py` now reads files as UTF-8, so it no longer fails on Windows over the Persian text.)
13. **The glossary is loaded on the shared database** (257 rows, Oct 24, `python -m app.glossary.load`). A `python -m app.db.reset` drops it; re-run the loader after any reset until person 1 calls it from the reset (ask 2.4).

## Still open

- **`writes.memory.delete_fact` (person 1):** drafted for decision 17; needs person 1's OK.
- **Profile label (person 1):** the dashboard has no label for the new `contact_preference` key, so it shows the raw key. Add one to `profileFields` (en, es).
- **Phone facts (person 4):** the call report's `proposed_facts` reach memory only if someone queues `memory_write` with `source=from_call`, `source_ref` = the call ID (Plan.md → Jobs). The stand-in report proposes none; the LLM report should, and the phone agent queues the job.
- **ask_user wiring (person 4):** built per decision 1. Confirm it fits the call loop.
- **`job_id` on `research.deep_done` (person 3):** the orchestrator needs it to read R2 (decision 10). The fake research agent sets it.
- **A failed or missing deep pass (team, Goal 8):** no failure rule. Today it's logged, and the user hears nothing after "I'm checking…".
- **A failed fast pass (team, Goal 8):** Plan.md has no failure rule for it. Today it's logged and the user hears nothing. Proposal: a template asking them to send the photo again.
- **Retake after `needs_better_image`:** the retake request is built (6.1). Research writes no `cases` row then, so the retake becomes a new letter with a new `case_id`. Decide whether the retake should reuse the case.
- **`call_recommended` false with a verified letter:** the user hears "no need to call" and isn't offered a call. They can still ask for one, and the turn's `request_consent` works.
- **Plan.md wording:** Sean to check the wording of the language and photo decisions.
- **Plan.md's orchestrator tool list (Sean):** it names `start_call`; decision 9 replaces it with the consent gate in code. Proposal: list `request_consent` only and note that the user's YES starts the call.
