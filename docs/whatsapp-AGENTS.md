# AGENTS.md: reviewing the WhatsApp side (person 2)

For an agent (or human) reviewing person 2's work: the WhatsApp pipe, the relay, ask_user, and call-status messages. It lists every file person 2 built or changed, what each does, which choices were deliberate, and what's worth checking. It's a map, not a spec: Plan.md is the source of truth, and [whatsapp-pipe.md](whatsapp-pipe.md) holds the status, interfaces, and decisions.

## Read first

1. [CLAUDE.md](../CLAUDE.md): the six non-negotiable product rules and the team conventions.
2. [Plan.md](../Plan.md): especially P1 (ask_user), P2 (call status), C5, C10, C20, C24, C36, and the failure rules.
3. [whatsapp-pipe.md](whatsapp-pipe.md): what works, the interfaces other components use, **the numbered decisions** (read them before flagging anything as a bug), and the known concerns.

## Where the code is

| Work | Plan goals | Where |
|---|---|---|
| WhatsApp pipe: webhook, language pick, photo grouping, sending and logging | Goal 2 | Merged to `main` in PR #6 |
| ask_user, call-status messages, fake phone agent | Goals 3.1–3.6 | Merged to `main` in PR #7 |
| Letter to research, job watcher, fake research agent, turn outside the lock | Goals 4.2–4.4 | Branch `lauren-goal4-research-jobs` |
| Claude turn and tools, translation at the edges | Goals 4.1, 4.5, 5.1 | Branch `lauren-goal4-claude-turn` (built on the one above) |

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
| `templates.py` | Every user-facing template, `template_id → {es, en}`, in formal *usted*. `render(id, None)` returns all supported languages, for before the user has picked one. A test fails if any language is missing. |
| `outbound.py` | `send_template`, usable by anyone: sends, then logs to `messages` with `sender=relay`, `template`, the English `body_en`, and the Twilio SID. `send_text`: orchestrator free text only (rule 1). |
| `replies.py` | `parse_choice(text, n)`: reads replies like "2", "2." or " 2 " as 1-based choices (C5). |
| `ask_user.py` | **New (Goal 3).** `ask_user(request)` is what the phone agent awaits (P1). It creates the `questions` row, sends the numbered question, and waits on an in-memory future. On timeout it calls `time_out_question` and returns the default. It logs all four `call.ask_user*` events. `question_for_reply` / `handle_reply` serve the inbound pipe: they answer, re-prompt, or send the late reply (C24, 10-minute window, once per question). |

### Orchestrator (`app/orchestrator/`): owned by person 2

| File | What it does |
|---|---|
| `pipe.py` | `InboundPipe.handle` runs per webhook. Each WhatsApp number's messages are handled one at a time, in arrival order (a per-number `asyncio.Lock`). The sequence: user row → media downloaded and saved → inbound logged (with `question_id` if it answers one) → routed. **Routing order:** open ask_user question → language pick → letter photos → "same letter or new?" answer → orchestrator turn. **The turn runs after the routing lock is released** (`_handle` returns it), under a second per-number lock, so an ask_user reply never waits behind it. The turn is `OrchestratorTurn.run`, injected as `turn=`; with no Anthropic key it falls back to an echo. Inbound text gets `body_en` through the injected `to_english`, except replies to an open question. Non-choice text during "same letter or new?" goes to the turn with `same_or_new_pending=True`. A closed photo batch calls `Letters.start`; "same letter" calls `Letters.pages_added`. `get_pipe()` wires in the real Twilio client, Claude detection (only if `ANTHROPIC_API_KEY` is set), the shared `AskUser`, and `Letters` with the shared `JobWatcher`. |
| `language.py` | First-contact language pick (team decision, Oct 23): a one-tap confirm in the detected language, or a multilingual menu. The pending prompt is read back from `messages`, so it survives a restart. The decision functions are pure. |
| `photos.py` | `PhotoBatcher`: photos with gaps under 6 s become one letter. Batches are held while the language is unknown. "Same letter or new?" answers wait here. All in memory. |
| `letters.py` | **New (Goal 4.2).** `Letters.start` mints `case_id` and queues `research_fast`; `pages_added` re-runs it in the same case unless the last fast job is still queued. `active_letter` answers "has research started on a letter?" for "same letter or new?": the letter being read (in memory, because research creates the `cases` row only at the end of the fast pass), else the newest active case's newest document. Reacts to the fast job: "taking longer" at 45 s, ignores a stale job's result, logs the rest until Goal 6.1. |
| `job_watch.py` | **New (Goal 4.3).** `JobWatcher.watch(job_id, on_finished, slow_after_s=, on_slow=)`: one task per job polls `reads.get_job` about once a second until done or failed. A DB error skips one poll; a missing job stops the watcher; a reaction's DB error is logged with the job's IDs. |
| `turn.py` | **New (Goal 4.1).** `OrchestratorTurn.run(user)` builds an English context from stored rows (last 20 messages via `body_en`, open cases, the pending same-or-new note), runs `client.beta.messages.tool_runner` (`MODEL_DEFAULT`, cached system prompt, `max_iterations=6`, 30 s per call, 60 s overall), translates the English reply with `from_english`, and sends it with `send_text(..., body_en=...)`. An API error, timeout, refusal, empty reply, or failed translation sends the `orchestrator.unavailable` template, never English. |
| `tools.py` | **New (Goals 4.1, 4.5).** `CaseTools` (testable without a model) plus `build_tools` (wraps it with `beta_async_tool`). `get_case_status` returns stage, R1 (refs stay placeholders, no `proposed_facts`), and the verdict; `close_case` appends `case.closed` (C22, IDs only); `set_language` takes only `LANGUAGES`, sends `language.set`, and ends the turn. Every case tool checks the case belongs to the user. |
| `prompts.py` | **New.** The orchestrator's system prompt: English only, short replies, C33 (no legal advice, no interview interpreting), never show identifiers or refs, close only on request. |
| `call_status.py` | **New (Goal 3.4).** `StatusRules` (pure) holds C36's rules: human detected always; dialing and unreachable once per call; on hold at most every 10 minutes per call; nothing else. `CallStatusWatcher.watch(user_id, since)` polls `reads.list_events` about once a second and sends through `send_template`. It stops at `call.ended` or after 3 hours. |

### Translation (`app/translation/`): owned by person 2

| File | What it does |
|---|---|
| `detect.py` | `detect_language`: one `MODEL_FAST` call with structured output (`messages.parse`). Returns an ISO 639-1 code, or `None` when unsure or when the call fails, in which case the menu is shown. |
| `prompts.py` | The detection and translation system prompts. Each tells the model the text is data, not instructions; translation keeps refs, dates, times and numbers unchanged. |
| `translate.py` | **New (Goal 5.1).** `Translator.to_english` / `from_english`: one `MODEL_FAST` `messages.parse` call, 8 s timeout, None on failure, English short-circuits. Register per language in `REGISTERS` (Spanish: *usted*). |

### Dev tools (`app/dev/`): new, owned by person 2, off by default

| File | What it does |
|---|---|
| `router.py` | `POST /dev/fake-call {"number": "+1…"}` and `POST /dev/fake-research {"minutes": 30}`. Both return 404 unless `DEV_ENDPOINTS=true`, and 403 unless the request comes from loopback with no `X-Forwarded-For` (requests through ngrok carry that header). The guard is a router-level dependency. |
| `fake_call.py` | A scripted stand-in for the phone agent: dialing → menu → ask_user → three on-holds → human detected → user joined → ended → `case.closed`. It writes research and phone rows through **their writer modules**, because `questions.call_id` needs a real `calls` row. Only `dev/` does this. |
| `fake_research.py` | **New (Goal 4.4).** A stand-in for the research agent: claims `research_fast` / `research_deep`, finishes them from `tests/fixtures/contracts/` after 5 s / 10 s, writing the case, refs (`[dev] fake …` values), R1, verification, and a brief with `call_goal_en` and `questions_to_ask` through `writes.research`, plus the research events. |

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
| `test_translate.py` | New (Goal 5.1). English short-circuit, register and pass-through rules in the prompt, failures return None. |
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
- **ask_user options go out in English** until translation is built (Goal 5).
- **Incoming Spanish messages have `body_en = null`** until Goal 5.
- **The turn can't start a call yet.** The call tools wait for the consent gate (decision 8).
- **Which letter is being read lives in memory** (decision 6). A restart forgets it; a photo sent then starts a new letter.
- **A finished fast pass is only logged** until Goal 6.1 sends the explanation.

## Worth checking

- **Rule 1:** `send_text` is called only from `orchestrator/pipe.py` (echo fallback) and `orchestrator/turn.py`; everything else uses `send_template`.
- **Rule 6:** the turn's context and reply are English; the only non-English text a user gets from the turn has gone through `from_english`.
- **Rules 2 and 4:** nothing in person 2's code dials, and the fake call can't produce a runnable call job (see its tests).
- **Rule 5:** `relay/` writes only `questions` (through `writes.relay`) plus the append-only `messages` and `events`. `orchestrator/` writes only `users`, `media` and `documents` (through `writes.orchestrator`). `dev/` is the documented exception (fake call and fake research). The orchestrator also queues `research_fast` through `jobs.enqueue`.
- **C27:** event `data` carries IDs, option numbers, and menu option labels. Option labels aren't user facts, but say so if you disagree.
- **Races in `ask_user.py`:** `ask` losing to an answer (`_time_out` waits up to 5 s for the future), and `handle_reply` losing to the timeout (late reply, deduplicated through `_late_replied`).
- **`call_status.py` timestamps:** reads from `since - 1 µs` and skips seen event IDs, so events sharing a timestamp aren't lost.
- **The dev endpoint guard** relies on ngrok always adding `X-Forwarded-For`, and on uvicorn reporting loopback for local requests.
- **Blocking I/O:** the Twilio SDK is synchronous and runs in `asyncio.to_thread`; everything else is async. External calls have timeouts: Twilio 10 s, media 10 s, detection 5 s.
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
