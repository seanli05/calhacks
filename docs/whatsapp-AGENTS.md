# AGENTS.md: reviewing the WhatsApp side (person 2)

For an agent (or human) reviewing person 2's work: the WhatsApp pipe, the relay, ask_user, and call-status messages. It lists every file person 2 built or changed, what each does, which choices were deliberate, and what's worth checking. It's a map, not a spec: Plan.md is the source of truth, and [whatsapp-pipe.md](whatsapp-pipe.md) holds the status, interfaces, and decisions.

## Read first

1. [CLAUDE.md](../CLAUDE.md): the six non-negotiable product rules and the team conventions.
2. [Plan.md](../Plan.md): especially R1, R2, H2, P1 (ask_user), P2 (call status), P3 (call report), C5, C8, C10, C20, C21, C22, C24, C31, C33, C36, and the failure rules.
3. [whatsapp-pipe.md](whatsapp-pipe.md): what works, the interfaces other components use, **the numbered decisions** (read them before flagging anything as a bug), and the known concerns.

## Where the code is

| Work | Plan goals | Where |
|---|---|---|
| WhatsApp pipe: webhook, language pick, photo grouping, sending and logging | Goal 2 | Merged to `main` in PR #6 |
| ask_user, call-status messages, fake phone agent | Goals 3.1–3.6 | Merged to `main` in PR #7 |
| Letter to research, job watcher, fake research agent, turn outside the lock | Goals 4.2–4.4 | Merged to `main` in PR #9 |
| Claude turn and tools, translation at the edges | Goals 4.1, 4.5, 5.1 | Branch `lauren-goal4-claude-turn` |
| ask_user option labels translated | Goal 5 (concern 7) | Branch `lauren-goal5-option-labels` (built on the one above) |
| Explanation, verdict, consent gate, call, summary, memory job, fake phone worker | Goals 6.1–6.5 | Branch `lauren-goal6-consent-call` (built on the one above) |

If the branch isn't on GitHub yet, ask person 2 to push it.

## Files

Paths are under `backend/` unless noted. "New" means person 2 created the file; "changed" means person 2 edited someone else's.

### Relay (`app/relay/`): WhatsApp in and out, owned by person 2

| File | What it does |
|---|---|
| `webhook.py` | `POST /whatsapp`. Checks Twilio's signature, parses the form, queues `InboundPipe.handle` as a background task, and returns empty TwiML at once. Replies never go in the TwiML. |
| `signature.py` | Validates `X-Twilio-Signature`, rebuilding the URL from `PUBLIC_BASE_URL` because ngrok rewrites the host. Predates Goal 2. |
| `inbound.py` | `InboundMessage.from_form`: parses every `MediaUrl{i}`/`MediaContentType{i}`, not just the first. `whatsapp_number` strips the `whatsapp:` prefix to E.164. Numbers, text and URLs are kept out of the repr so they can't reach logs. |
| `media.py` | Downloads media with Twilio credentials. Auth isn't forwarded to the CDN redirect, and the URL is kept out of error messages. |
| `whatsapp.py` | The thin Twilio wrapper. `WhatsApp` is a Protocol so tests can swap in a fake. `TwilioWhatsApp.send` uses the REST SDK in a worker thread (the SDK is synchronous), splits bodies over 1,600 chars with `split_body`, and raises `WhatsAppSendError` with Twilio's error code but no message text, which can contain numbers. |
| `templates.py` | Every user-facing template, `template_id → {es, en, fa}`: Spanish in formal *usted*, Dari (`fa`, Oct 24) in Afghan Dari with the polite شما, glossary terms and Persian digits. Language pick, letters, ask_user, call status, and (Goal 6) `letter.*`, `verification.*`, `consent.*`, `summary.*`. `render` writes int values in the language's digits and adds direction isolates around Latin runs in right-to-left text (`translation/script.py`); `render(id, None)` returns all supported languages, for before the user has picked one. Tests fail if any language is missing, if a translation's placeholders differ from the English, or if a Dari text has Latin digits or an Iranian-only word. |
| `outbound.py` | `send_template`, usable by anyone: sends, then logs to `messages` with `sender=relay`, `template`, the English `body_en`, and the Twilio SID. `values_en=` logs English values when a value was translated (option labels, a call goal, red flags). `send_text`: orchestrator free text only (rule 1). |
| `replies.py` | `parse_choice(text, n)`: reads replies like "2", "2.", " 2 " or "۲" as 1-based choices (C5). `parse_yes_no`: `1`/"sí"/"si"/"yes"/بلی/بله/آری/آره or `2`/"no"/نخیر/نه/نی, for two-option questions (consent, the language confirm, "may I save this?"); Arabic letter forms (ي, ك) read as Persian ones. |
| `ask_user.py` | **New (Goal 3).** `ask_user(request)` is what the phone agent awaits (P1). It creates the `questions` row, sends the numbered question, and waits on an in-memory future. On timeout it calls `time_out_question` and returns the default. It logs all four `call.ask_user*` events. `question_for_reply` / `handle_reply` serve the inbound pipe: they answer a bare number, or send the late reply (C24, 10-minute window, once per question); words go on to the turn (re-prompted only with no turn). `answer(user, question, choice)` is the shared answer path, also used by the turn's `answer_call_question`. |

### Orchestrator (`app/orchestrator/`): owned by person 2

| File | What it does |
|---|---|
| `pipe.py` | `InboundPipe.handle` runs per webhook. Each WhatsApp number's messages are handled one at a time, in arrival order (a per-number `asyncio.Lock`). The sequence: user row → media downloaded and saved → inbound logged (with `question_id` if it answers one) → routed. **Routing (Oct 24, agentic routing):** code answers a bare number to an open ask_user question, the language pick, letter photos, a bare 1/2 to "same letter or new?", research's question (C39), and a 1/2 or yes/no word to consent or "may I save this?"; everything else goes to the orchestrator turn with `open_questions(user_id)`, which answers in words through guarded tools. **The turn runs after the routing lock is released** (`_handle` returns it), under the user's conversation lock (`conversation.py`, shared with proactive messages), so an ask_user reply never waits behind it. `question_open` is the one check for an open numbered question. The turn is `OrchestratorTurn.run`, injected as `turn=`; with no Anthropic key it falls back to an echo. Inbound text gets `body_en` through the injected `to_english`, except a bare number. A closed photo batch calls `Letters.start`; "same letter" calls `Letters.pages_added`. `get_pipe()` wires in the real Twilio client, Claude detection (only if `ANTHROPIC_API_KEY` is set), the shared `AskUser`, and `Letters` with the shared `JobWatcher`. |
| `language.py` | First-contact language pick (C45): a clear message sets the language (`guessed`, so the turn confirms it in passing); an unclear one gets the multilingual question with no numbers, answered by a name or number (`picked`) or a clear sentence. The pending prompt is read back from `messages`, so it survives a restart. The decision functions are pure. |
| `photos.py` | `PhotoBatcher`: photos with gaps under 6 s become one letter. Batches are held while the language is unknown. "Same letter or new?" answers wait here. All in memory. |
| `letters.py` | **New (Goal 4.2).** `Letters.start` mints `case_id` and queues `research_fast`; `pages_added` re-runs it in the same case unless the last fast job is still queued. `active_letter` answers "has research started on a letter?" for "same letter or new?": the letter being read (in memory, because research creates the `cases` row only at the end of the fast pass), else the newest active case's newest document. Reacts to the fast job: "taking longer" at 45 s, ignores a stale job's result, logs the rest until Goal 6.1. |
| `letter_result.py` | **New (Goal 6.1).** `LetterResults.fast_done(job)`: R1 → one `send_text` with the translated explanation and checklist, the date line and the closing as templates; a failed translation sends templates only. `needs_better_image` → `letter.retake_tip` / `letter.retake`. Starts the verdict watcher after sending. |
| `verdicts.py` | **New (Goal 6.2).** `Verdicts.watch(user_id, case_id, since)`: polls `reads.list_events` for `research.deep_done` on the case, reads R2 from the event's `job_id`, and `react`s under the conversation lock: verified ("it's genuine" alone, never a call offer: C44; or "no need to call" with no number), suspicious (warning with translated red flags, no call), unknown (explain, ask). |
| `consent.py` | **New (Goals 6.3, 6.4).** `ConsentGate`: `request` (refuses unless verified, an official number, a brief, no call running, and no other numbered question open; sends `consent.request` with the translated goal; logs `consent.requested`), `can_call` (for `get_case_status`'s `call_available`), `asked`/`send_question` (when the turn asks in its own words), `answer` (from the pipe, on the user's 1/2), `answer_in_words` (C43: the turn's `answer_call_consent`, checked against the user's latest message), the re-check and `CallJob` enqueue, and `_call_finished` (one message: the summary with the retry consent or the close suggestion at its end). |
| `conversation.py` | **New (Oct 24, pacing).** `Conversation`: a per-user lock that turns and proactive messages hold while they're built and sent (`speaking`), the pipe's open-question check (`bind`, `question_open`), and "typing…" per user (`heard` records the latest inbound SID; `typing`/`done_typing`/`typing_while` with a reason and a cap; re-sent every 20 s through `WhatsApp.typing`). In memory. |
| `call_summary.py` | **New (Goal 6.4).** `send_call_summary`: next steps translated; reference number and dates in templates; failed and unreachable get their own templates. |
| `dates.py` | **New (Goal 5.4).** `format_date` / `format_time` for `es`, `en` and `fa` ("چهارشنبه ۱۸ نومبر ۲۰۲۶", "۸:۳۰ صبح"; sources in the docstring); ISO for anything else, which no supported language gets. |
| `job_watch.py` | **New (Goal 4.3).** `JobWatcher.watch(job_id, on_finished, slow_after_s=, on_slow=)`: one task per job polls `reads.get_job` about once a second until done or failed. A DB error skips one poll; a missing job stops the watcher; a reaction's DB error is logged with the job's IDs. |
| `turn.py` | **New (Goal 4.1).** `OrchestratorTurn.run(user, message_id)` builds an English context from stored rows (last 20 messages via `body_en`, open cases, an `<open_questions>` block), runs `client.beta.messages.tool_runner` (`MODEL_DEFAULT`, cached system prompt, `max_iterations=6`, 30 s per call, 60 s overall), translates the English reply with `from_english`, and sends it with `send_text(..., body_en=...)`, ending with "may I save this?" at a quiet moment. The context also has `<letters_in_progress>` (photos arriving, or the case being read, which has no row yet). An answer tool's confirmation and a consent question the user asked for are part of the reply. With no reply to send (API error, timeout, refusal, empty reply, failed translation), those go out as their templates; otherwise the `orchestrator.unavailable` template, never English. Then queues `memory_write` on the user's message (Goal 6.5). |
| `tools.py` | **New (Goals 4.1, 4.5).** `CaseTools` (testable without a model) plus `build_tools` (wraps it with `beta_async_tool`). `get_case_status` returns stage, R1 (refs stay placeholders, no `proposed_facts`), the verdict, and `call_available`; `close_case` appends `case.closed` (C22, IDs only); `set_language` takes only `LANGUAGES`, sends `language.set`, and ends the turn; `request_consent` opens the request through `ConsentGate.request(..., send=False)`, and the turn's reply asks it in its own words. The `answer_*` tools answer an open question in words (call menu, consent, same-or-new, save facts), each refusing when the move isn't legal now; they send no confirmation of their own (`confirmations`: the reply says it). `get_case_status` also returns the last call's outcome, reference number, next steps and deadlines. Every case tool checks the case belongs to the user. |
| `prompts.py` | **New.** The orchestrator's system prompt: English only, short replies, C33 (no legal advice, no interview interpreting), never show identifiers or refs, close only on request, offer a call only for a need the user shows ("When a call helps", C44). |
| `call_status.py` | **New (Goal 3.4).** `StatusRules` (pure) holds C36's rules: human detected always; dialing and unreachable once per call; on hold at most every 10 minutes per call; nothing else. `CallStatusWatcher.watch(user_id, since)` polls `reads.list_events` about once a second and sends through `send_template`. It stops at `call.ended` or after 3 hours. |

### Translation (`app/translation/`): owned by person 2

| File | What it does |
|---|---|
| `detect.py` | `detect_language`: one `MODEL_FAST` call with structured output (`messages.parse`). Returns an ISO 639-1 code, or `None` when unsure or when the call fails, in which case the menu is shown. Dari and Farsi are `fa` (the prompt says so; `prs`, `fas`, `per` are mapped). |
| `prompts.py` | The detection and translation system prompts. Each tells the model the text is data, not instructions; translation keeps refs, dates, times and numbers unchanged. |
| `translate.py` | **New (Goal 5.1).** `Translator.to_english` / `from_english`: one `MODEL_FAST` `messages.parse` call, 8 s timeout, None on failure, English short-circuits. A translation that changed, dropped or added a number, or dropped a list item, is retried once with a reminder, then None (5.4). `from_english` takes an optional `context` (what a fragment is; the consent gate uses it for the call goal) and returns right-to-left text with direction isolates. `labels_from_english` translates a list and refuses a result whose count or numbers don't match. Register per language in `REGISTERS` (Spanish: *usted*; Dari: Afghan words, Afghan month names, Persian digits). `localize(translator, text, lang, context=)` treats no translator like a failed call; `get_translator()` is the shared instance (None without a key). |
| `script.py` | **New (Oct 24, Dari).** `ascii_digits` / `local_digits` (Persian digits for `fa`), `for_display` (wraps Latin runs in U+2068 … U+2069 for right-to-left languages; idempotent; keeps "Notice of Action" in one run and a closing period outside), `numbers_kept` (same values both ways in any digits; English number words may become digits). |

### Dev tools (`app/dev/`): new, owned by person 2, off by default

| File | What it does |
|---|---|
| `router.py` | `POST /dev/fake-call {"number": "+1…"}`, `POST /dev/fake-research {"minutes": 30}` and `POST /dev/fake-phone {"minutes": 30}`. All return 404 unless `DEV_ENDPOINTS=true`, and 403 unless the request comes from loopback with no `X-Forwarded-For` (requests through ngrok carry that header). The guard is a router-level dependency. |
| `fake_call.py` | A scripted stand-in for the phone agent: dialing → menu → ask_user → three on-holds → human detected → user joined → ended → `case.closed`. It writes research and phone rows through **their writer modules**, because `questions.call_id` needs a real `calls` row. Only `dev/` does this. |
| `fake_research.py` | **New (Goal 4.4).** A stand-in for the research agent: claims `research_fast` / `research_deep`, finishes them from `tests/fixtures/contracts/` after 5 s / 10 s, writing the case, refs (`[dev] fake …` values), R1, verification, and a brief with `call_goal_en` and `questions_to_ask` through `writes.research`, plus the research events. |

| `fake_phone.py` | **New (Goal 6).** A stand-in for the phone agent's job loop: claims `call` jobs, checks `official_dial_number` (fails the job without one), creates the call with the job's real `consent_message_id`, plays `fake_call.play_call`, saves a transcript and the fixture's report, and finishes the job. Never dials. |

The fake research agent's safety (please check): the verification's phone is `TWILIO_MOCK_AGENCY_NUMBER` or empty, never the fixture's real USCIS number (rule 2); a test checks the fixture number never appears in R2.

The fake call's safety (please check these):
- Its `call` job is failed the moment it's created.
- Its case is new and unverified, so `official_dial_number` refuses it (rule 2).
- Its consent pointer references a labelled `[dev]` note, never a made-up "YES" (rule 4).

### Tests (`backend/tests/`)

All on fakes: no Twilio, no Anthropic, no database.

| File | What it covers |
|---|---|
| `whatsapp_fakes.py` | New. `FakeDB`, an in-memory stand-in for every DB helper the pipe and relay call. Question reads return copies, so a stale "open" row can be simulated. Also `FakeWhatsApp` (records sends, can fail on demand) and the `inbound()` message builder. |
| `conftest.py` | New. The fixtures `db`, `whatsapp`, `detected`, `ask_user` and `pipe`, which install the fakes with `monkeypatch`. No name collisions with other test files. |
| `test_whatsapp_webhook.py` | Signature, form parsing, every media item, the empty-TwiML ack, and media auth not going to the CDN. |
| `test_whatsapp_pipe.py` | Language pick, photo batching, "same letter or new?", download failure, splitting, template completeness, detection mapping. |
| `test_ask_user.py` | New. Answer, timeout, both race directions, late reply (once, window expiry), re-prompt, routing priority over "same or new", unsent question, unknown question kind, and the event `data` fields the dashboard feed reads. |
| `test_orchestrator_letters.py` | New (Goal 4). Letter → `research_fast` with a minted case, "same letter or new?" before any case row, re-run rules, a photo after an unreadable letter, "taking longer" once, stale results ignored, the watcher on failed and missing jobs, and an ask_user reply not waiting behind a slow turn. |
| `test_orchestrator_turn.py` | New (Goals 4.1, 4.5). Each tool on `FakeDB` (refs kept, ownership, close once, language switch, active facts only), the turn on a fake tool runner (reply translated with `body_en`, refs never resolved, every failure path sends the template), and the pipe wiring. |
| `test_translate.py` | New (Goal 5.1). English short-circuit, register and pass-through rules in the prompt, failures return None; glossary grounding (Spanish accents and plurals, Dari letter forms and plurals, English verb forms); the Dari register; numbers in Persian digits, a changed/dropped/made-up date retried then refused, a dropped list item, the context note; isolates on Dari output only. |
| `test_orchestrator_results.py` | New (Goal 6). Dates; R1 message (date line from a template, checklist, closing, English fallback); retake; the three verdict branches; the consent gate (one YES one call, yes words, decline, re-prompt, a verdict changed before the YES, no request without a verified number, no second request mid-call, the tool only asks); the summary and what follows each outcome. |
| `test_fake_phone.py` | New (Goal 6). YES → fake phone → ask_user → status messages → summary through the real pipe, and the fake's rule 2 refusal. |
| `test_fake_research.py` | New (Goal 4.4). Both fake passes from a real pipe letter, the mock line (never the fixture's number), no phone when unset, and the endpoint guards. |
| `test_call_status.py` | New. Each C36 rule, the watcher end to end (including events sharing a timestamp), the dev endpoint's guards, and a full fake call run on fakes, checking that no runnable job is left behind. |

### Edits outside person 2's packages

All small. Please confirm with their owners that they're acceptable.

| File (owner) | Change |
|---|---|
| `app/main.py` (1) | Registers `app.dev.router` (which 404s unless enabled). |
| `app/settings.py` (1) | Adds `dev_endpoints: bool = False`. |
| `.env.example` (1) | `DATABASE_URL_UNPOOLED` is now blank: the localhost default silently overrode `DATABASE_URL`. Adds `DEV_ENDPOINTS=false`. |
| `backend/AGENTS.md` (team) | Person 2's rows, the `dev/` row, and the run command (`--reload-dir backend`). |
| `README.md` (team) | WhatsApp setup and Twilio gotchas, the run command, and pointers to the WhatsApp docs. |
| `CLAUDE.md` (team) | One rule: run the backend as a single process (in-memory state), with `--reload-dir backend`. |
| `Plan.md` (Sean) | The language and photo decisions recorded in Decisions; C36 marked as agreed by person 2. |

## Deliberate choices, not bugs

Each is explained in whatsapp-pipe.md → Decisions and Concerns.

- **State lives in memory, so the backend runs as one process.** That covers photo batches, ask_user waits, late-reply windows, call-status watchers and per-number locks. A restart loses them, but never user data.
- **ask_user waits in memory** (P1's "asyncio future"); the `questions` row decides races.
- **There's no "call ended" message.** Exactly four status events message the user (P2, `USER_MESSAGING_EVENTS`).
- **The call-status watcher follows the user, not a call ID**, because the phone agent mints the call ID only when it picks up the job (C7).
- **There's no `start_call` tool** (decision 9). Only the user's own YES starts a call: a `1` in code, or words the consent gate checks against their latest message (C43).
- **R2 is found through `research.deep_done` events** (decision 10), not a jobs helper.
- **Dates go in templates, written in code** (decision 11), not through translation.
- **Which letter is being read, the open consent request, and the verdict watchers live in memory** (decisions 6, 9, 10). A restart forgets them.

## Worth checking

- **Rule 1:** `send_text` is called only from `orchestrator/` (`pipe.py` echo fallback, `turn.py`, `letter_result.py`, `call_summary.py`); everything else uses `send_template`.
- **Rule 4 and C21:** `CallJob` is enqueued only in `ConsentGate._start_call`, reached only from `answer` with choice 1, which the pipe calls only on a parsed reply to an open request. Check the re-check there and that the request is popped before the call starts.
- **Rule 6:** the turn's context and reply are English; the only non-English text a user gets from the turn has gone through `from_english`.
- **Rules 2 and 4:** nothing in person 2's code dials, and the fake call can't produce a runnable call job (see its tests).
- **Rule 5:** `relay/` writes only `questions` (through `writes.relay`) plus the append-only `messages` and `events`. `orchestrator/` writes only `users`, `media` and `documents` (through `writes.orchestrator`). `dev/` is the documented exception (fake call, fake research, fake phone). The orchestrator also queues `research_fast`, `call` and `memory_write` through `jobs.enqueue`.
- **C27:** event `data` carries IDs, option numbers, and menu option labels. Option labels aren't user facts, but say so if you disagree.
- **Races in `ask_user.py`:** `ask` losing to an answer (`_time_out` waits up to 5 s for the future), and `handle_reply` losing to the timeout (late reply, deduplicated through `_late_replied`).
- **`call_status.py` timestamps:** reads from `since - 1 µs` and skips seen event IDs, so events sharing a timestamp aren't lost.
- **The dev endpoint guard** relies on ngrok always adding `X-Forwarded-For`, and on uvicorn reporting loopback for local requests.
- **Blocking I/O:** the Twilio SDK is synchronous and runs in `asyncio.to_thread`; everything else is async. External calls have timeouts: Twilio 10 s, media 10 s, detection 5 s, translation 8 s, ask_user option labels 3 s (then English), a turn 30 s per call and 60 s overall.
- **Logging:** no phone numbers, message text, or media URLs in log lines.

## How to verify

```bash
ruff format --check . && ruff check . && pytest
```

The WhatsApp tests run offline in about 6 s. `test_ask_user.py` and `test_call_status.py` use short real timeouts (about 1 s); they've been stable over repeated runs. DB tests skip unless `TEST_DATABASE_URL` points at the separate test branch.

**Please don't:**
- **send real WhatsApp messages.** The Twilio account in use is paid personally by a teammate's friend. The tests never need it.
- **enable `DEV_ENDPOINTS` or run the fake call against the shared database.** It writes rows and sends WhatsApp messages.
- **run `python -m app.db.reset`.** It wipes the shared database for everyone.
