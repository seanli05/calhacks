# Phone agent: ports and fakes

Owner: person 4. Implements Plan.md → Phone agent, H2, P1–P3; it doesn't change them. Code: `backend/app/phone/`.

The call runner talks to the outside world only through the Protocols in `ports.py`, bundled per call in `CallDeps`. Each has a real adapter and an in-memory fake, so a whole call runs (and tests) with no Twilio, Neon, or WhatsApp.

## Ports

| Port | What it is | Real adapter | Fake |
|---|---|---|---|
| `Telephony` | One call's line: `dial_agency`, `say`, `press_keys`, `ring_user`, `connect_user`, `hang_up`, plus `events()`, the stream of everything that happens (`line.py`) | `TwilioTelephony` (`twilio_line.py`; agency leg only until Phase 3) | `FakeTelephony`: a script, plus an optional `responder` that reacts to actions (how the simulator plugs in a phone tree) |
| `Relay` | `ask_user` (P1) | `RelayAskUser` → `app.relay.ask_user` | `FakeRelay`: scripted `Answer` / `NoAnswer` |
| `CaseReader` | The brief | `DbCaseReader` | `FakeCaseReader` |
| `CallStore` | `calls`, `transcripts` (only the phone agent writes them) | `DbCallStore` → `writes.phone` | `FakeCallStore` |
| `EventLog` | `events` | `DbEventLog`; `CallEvents` fills the envelope | `FakeEventLog` |
| `Clock` | `now`, `sleep`; `clock.with_timeout` for timeouts | `SystemClock` | `FakeClock`: virtual time (`advance`, `run`) |

`NumberSource` (the verified official number, the user's number) feeds `Telephony` adapters only. It isn't in `CallDeps`.

## Rules enforced by construction

| Rule | How |
|---|---|
| 2. Only the verified number | No `Telephony` method takes a number (a test checks). Adapters read `official_dial_number` at dial time; `UnverifiedNumber` propagates, with no fallback |
| 4. Recorded consent | `dial_agency` needs a `call_id`, which only `create_call` mints, from the `CallJob` and its `consent_message_id` |
| C35. No identifiers on the line | The runner can't resolve refs. `GuardedTelephony` checks every `say` and `press_keys` against the case's real receipt number, A-Number, and date of birth (`adapters.load_blocked_values`), across the whole call |
| C6. User's number stays out | Only `ring_user`'s adapter reads it |

## Conventions for the runner

- Wait only through `Clock` (`clock.sleep`, `with_timeout`), never `asyncio.sleep` or `asyncio.timeout`, or virtual time stops working. (Model calls in 1b and 1c time themselves in real time; that's measured, not waited on.)
- Don't await `ask_user` inline: run it as a task and keep reading `events()` (menus reprompt and hang up long before 45 s).
- The relay logs every `call.ask_user*` event; the phone agent logs none of them.
- Actions after the line ends raise `LineClosed`; a blocked identifier raises `BlockedIdentifier` and nothing is sent.

## The runner (1e)

`run_call(job_id, job, deps, *, llm, observer, config, report_builder) -> CallReport` runs one call and returns its saved report. It raises only if the call can't be created or the report can't be saved. The Phase 4 worker wraps it: `claim_next`, build `CallDeps` (with `load_blocked_values` → `GuardedTelephony`), `run_call`, then `finish` or `fail`. The runner refuses a `telephony` that isn't a `GuardedTelephony`, so C35 holds by construction and identifier values never reach it.

Files: `runner.py` (lifecycle, dispatch, hold, the person, the bridge), `runner_menu.py` (menu and ask_user), `runner_base.py` (shared state, logging, classify, transcript, observer), `runner_parts.py` (config, inbox inputs, timers), `executor.py` (C37), `call_lines.py` (the fixed lines to the rep), `report.py` (stand-in P3 builder), `observe.py` (`StepRecord`).

**Shape.** One inbox, one handler at a time. A pump task reads `events()` and stamps each event on arrival; the ask_user task and the timers (hold limit, user-answer backstop, menu budget, menu quiet, turn backstop) only post to the inbox. Model calls are awaited inside a handler, and whatever arrives meanwhile waits. Wrap-up is a `finally`: every exit (hang-up, timeout, crash) cancels the background work, hangs up, saves the transcript and the report, and fires `REPORT_SAVED`.

**Policies** (numbers in `RunnerConfig`; first guesses, to tune on real lines):

| Moment | What the runner does |
|---|---|
| Dial | `create_call`, read the brief, `dial_agency`, then log `call.dialing`, only once the dial went out, so the user never hears "Calling now" for a call that didn't happen. `UnverifiedNumber` → `AGENT_ABORTED` |
| Menu utterance | 1c and 1b in parallel; 1b's answer is dropped if 1c leaves the menu or newer speech arrived. 1b gets all menu speech since the last answer sent, so a split prompt is decided whole. `call.menu_heard` carries the reading and the action kind, logged when the answer goes out (`stale` if it was dropped) |
| Every option first | **Never answer a menu before hearing all of it.** Every menu output (press, say, starting ask_user, the applicant's choice, the early default) is held until the line has been quiet `menu_quiet_s` (1 s) after the turn closed; with the audio line's ~1 s turn gap, that's ~2 s of quiet. `SpeechStarted` pauses it. More text drops a held decision and the menu so far is decided again; a turn with no text (`NonSpeech`, or the 30 s backstop) lets it out. The applicant's choice survives a reprompt of its prompt. Limit: a line that pauses > 2 s mid-list can still fool it; 1b's prompt also waits on a prompt cut off mid-option |
| Back in a menu | The utterance that fired `MENU_RETURNED` is decided at once |
| Press (C37) | Speak the digit word ("two"). Keys instead when the prompt names the keypad, or when a spoken press was answered with a no-match/no-input reprompt or the same prompt; then keys for the rest of that menu tree, until the next hold |
| ask_user | Asked with a 30 s timeout. Reprompts of the asked prompt aren't decided again; the second one takes the default early (menus hang up after 2–3 no-inputs). A new prompt, hold, or a person drops the question (the task is cancelled) |
| Music in a menu | ≥ 5 s → `HOLD_STARTED` with no model call |
| Hold limit | From the first hold, never reset. If it passes in a menu or with a person, it fires on the next hold |
| Menu gives up | Over 8 min in menus, or "representative" a 4th time in one menu stretch → `AGENT_ABORTED` |
| Person | Ring the applicant at once (< 5 s) and say the intro meanwhile; `USER_DIALED` once ringing. So `FALSE_HUMAN` almost never fires: 1c's thresholds are the defense, and after the ring a transfer just means the applicant waits on hold too |
| Bridging | Rep speech gets one fixed holding line, at most twice, ≥ 8 s apart. `UserUnreachable` (or the 45 s backstop) → the call-back line, then hang up |
| Blocked identifier | Nothing sent, flagged; a second in a row says "representative" instead |
| Unexpected error | `AGENT_ABORTED` and wrap-up. With the applicant on (no abort from `connected`), the bridge stays up and the runner only watches for the end |
| `events()` ends unannounced | As a hang-up (`CALL_FINISHED` when connected) |

`call.ended` data: `minutes`, `outcome`, `cause` (the trigger into wrap-up), and `error` (an exception's type name) when there was one.

**Observer.** One `StepRecord` per handled input (plus the dial and the wrap-up): what was heard, the reading, the action, what went out, transitions, events logged, model latencies, and flags. It carries transcript text, so it stays local (simulator, playground, debugging). Never log it.

**Simulator.** `python -m app.phone.simulate --tree NAME` (from `backend/`) runs a call against a text tree in `sim_trees.py` with real Claude on `SystemClock`. `FakeClock` can't wait for a real request: `run` either jumps virtual time past it or stops as "stuck". `heldout_consular` is held out; don't tune to it.

## The real line (Phase 2)

`TwilioTelephony` is one call's agency leg. Everything runs in the one backend process, and `twilio_line.LINES` maps each `call_id` to its line so Twilio's two ways in can find it (`routes.py`, both signature-checked with `relay/signature.py`):

| Route | What arrives | Becomes |
|---|---|---|
| `POST /phone/calls/{call_id}/status` | Twilio's call status callbacks | `in-progress` → `AgencyAnswered`; `busy`/`no-answer`/`failed`/`canceled` before an answer → `AgencyUnreachable`; `completed` → `AgencyHungUp` (unless we hung up) |
| `WS /phone/calls/{call_id}/stream` | The media stream (`<Connect><Stream>`) | A Pipecat pipeline (`audio_pipeline.py`): Silero VAD → Cartesia Ink → `LineListener` → Cartesia Sonic. Its start also means answered |

| Piece | What it does |
|---|---|
| Order | Callbacks and streams arrive in any order. The line only moves forward: answered once, gone once. Streams are numbered; a close counts only for the current one |
| Turns (`listener.py`) | VAD stop 0.5 s; fragments join until 1 s of quiet (plus up to 1 s for speech-to-text's last fragment); cut at 25 s. Every `SpeechStarted` is closed by one `Heard`, or `NonSpeech` if it had no words |
| `NonSpeech` | Between turns, every 5 s, `seconds` = the stretch so far; `music` if most 20 ms frames were above `LOUD_RMS`, else `silence`. Text is never dropped as music: a rep's lone "Hello?" after hold music must reach the classifier |
| `say` | Queues the speech and a Twilio `mark` after it; returns when Twilio echoes the mark (the audio played). No mark within the spoken length + 5 s: logs and carries on. Cancelling it sends Twilio `clear` |
| `press_keys` (C37) | REST update to `<Play digits="w…">` + a new stream; returns once that stream is up. None within 8 s: the agency hung up (`AgencyHungUp`), or we hang up; either way `LineClosed` |
| `hang_up` | REST `completed`, closes the stream, unregisters, ends `events()`. Safe twice |
| A stream that ends unasked | `completed` should follow; if it hasn't in 5 s, `AgencyHungUp` |
| Not stored | No recording, no audio buffers (C29). Logs carry IDs and statuses, never numbers or speech |

Settings: `CARTESIA_AGENT_VOICE_ID` (required for speech), `CARTESIA_STT_MODEL`, `CARTESIA_TTS_MODEL`, and `PUBLIC_BASE_URL` for Twilio to reach us. The Pipecat worker's idle timeout is off; its default would cancel the stream after 5 minutes on hold.

**Open, for Phase 2 and the team:**
- Live smoke test: `python -m app.phone.smoke` (steps in the README). It dials only the mock line (`MockLineOnly` refuses any other number a case resolves to) or, with `--own-number`, `PHONE_SMOKE_DIAL_NUMBER` through `SmokeNumberSource`, which only `smoke.py` has (a test checks nothing in `app` imports it). Smoke calls are dev calls to our own lines, so they use a fake job and fake stores and write nothing. Not yet checked on a live call: which URL Twilio signs on the websocket handshake (both `https` and `wss` forms are accepted), the mark round trip, the reconnect time, and `LOUD_RMS` against real hold music.
- `ring_user` and `connect_user` raise `NotImplementedError` (Phase 3), so a full call on the real line aborts and hangs up once a person is detected.
- No `bridging → hold`: a "person" who transfers after the ring can't be undone (state.py).

## Open, with person 2 (`relay/ask_user.py`)

- **Cancelling `ask`** (the agency hangs up while the user decides) leaves the `questions` row `open`, so the user's next "1" is taken as an answer to a dead call. Suggested: on `CancelledError`, call `time_out_question` and re-raise.
- **The reply doesn't say whether it timed out.** The runner can't tell "user chose 1" from "default 1". Fine for now (the events say so); raise it if the call report needs it.
