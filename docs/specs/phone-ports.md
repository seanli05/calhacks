# Phone agent: ports and fakes

Owner: person 4. Implements Plan.md → Phone agent, H2, P1–P3; it doesn't change them. Code: `backend/app/phone/`.

The call runner talks to the outside world only through the Protocols in `ports.py`, bundled per call in `CallDeps`. Each has a real adapter and an in-memory fake, so a whole call runs (and tests) with no Twilio, Neon, or WhatsApp.

## Ports

| Port | What it is | Real adapter | Fake |
|---|---|---|---|
| `Telephony` | One call's line: `dial_agency`, `say`, `press_keys`, `ring_user`, `connect_user`, `listen_in`, `hang_up`, plus `events()`, the stream of everything that happens (`line.py`) | `TwilioTelephony` (`twilio_line.py`: the agency leg, and the applicant's leg bridged into it) | `FakeTelephony`: a script, plus an optional `responder` that reacts to actions (how the simulator plugs in a phone tree) |
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
| C6. User's number stays out | Only the adapters of `ring_user` and `listen_in` read it |

## Conventions for the runner

- Wait only through `Clock` (`clock.sleep`, `with_timeout`), never `asyncio.sleep` or `asyncio.timeout`, or virtual time stops working. (Model calls in 1b and 1c time themselves in real time; that's measured, not waited on.)
- Don't await `ask_user` inline: run it as a task and keep reading `events()` (menus reprompt and hang up long before 45 s).
- The relay logs every `call.ask_user*` event; the phone agent logs none of them.
- Actions after the line ends raise `LineClosed`; a blocked identifier raises `BlockedIdentifier` and nothing is sent.

## The runner (1e)

`run_call(job_id, job, deps, *, llm, observer, config, report_builder) -> CallReport` runs one call and returns its saved report. It raises only if the call can't be created or the report can't be saved. The worker (`worker.py`) wraps it: `claim_next`, build `CallDeps` (with `load_blocked_values` → `GuardedTelephony`), `run_call` with an `LlmReportBuilder`, then `finish` or `fail` (see The call report and the worker, below). The runner refuses a `telephony` that isn't a `GuardedTelephony`, so C35 holds by construction and identifier values never reach it.

Files: `runner.py` (lifecycle, dispatch, hold, the person, the bridge), `runner_menu.py` (menu and ask_user), `runner_base.py` (shared state, logging, classify, transcript, observer), `runner_parts.py` (config, inbox inputs, timers), `executor.py` (C37), `call_lines.py` (the fixed lines to the rep), `report.py` (the P3 builder; below), `observe.py` (`StepRecord`).

**Shape.** One inbox, one handler at a time. A pump task reads `events()` and stamps each event on arrival; the ask_user task and the timers (hold limit, user-answer backstop, menu budget, menu quiet, turn backstop) only post to the inbox. Model calls are awaited inside a handler, and whatever arrives meanwhile waits. While `bridging` or `connected`, each new transcript line also saves the transcript in the background, so the dashboard's live call view can follow it: one save at a time (lines that arrive during a save go into the next one), and a failed save is logged and dropped. Wrap-up is a `finally`: every exit (hang-up, timeout, crash) cancels the background work, hangs up, lets a live transcript save finish, saves the transcript and the report, and fires `REPORT_SAVED`.

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
| Bridging | The intro and holding lines play in the background, so the applicant joining (or not) is acted on at once and cuts them short. Rep speech gets one fixed holding line, at most twice, ≥ 8 s apart, never over a line still playing. `UserUnreachable` (or the 75 s backstop: 30 s ringing plus the join gate) → the call-back line, then hang up |
| Connected | `Overheard` lines from the forks go into the transcript as `agency` / `user`, saved as they arrive; nothing else is decided |
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
| Turns (`listener.py`) | VAD start 0.5 s (so breaths and clicks don't open a turn; watch for a missed bare "Hello?"), VAD stop 0.5 s; fragments join until 1 s of quiet (plus up to 0.5 s for speech-to-text's last fragment, which a wordless turn waits out in full); cut at 25 s. Every `SpeechStarted` is closed by one `Heard`, or `NonSpeech` if it had no words |
| `NonSpeech` | Between turns, every 5 s, `seconds` = the stretch so far; `music` if most 20 ms frames were above `LOUD_RMS`, else `silence`. Text is never dropped as music: a rep's lone "Hello?" after hold music must reach the classifier |
| `say` | Queues the speech and a Twilio `mark` after it; returns when Twilio echoes the mark (the audio played). No mark within the spoken length + 5 s: logs and carries on. Cancelling it sends Twilio `clear` |
| `press_keys` (C37) | REST update to `<Play digits="w…">` + a new stream; returns once that stream is up. None within 8 s: the agency hung up (`AgencyHungUp`), or we hang up; either way `LineClosed` |
| `hang_up` | REST `completed`, closes the stream, unregisters, ends `events()`. Safe twice |
| A stream that ends unasked | `completed` should follow; if it hasn't in 5 s, `AgencyHungUp` |
| Not stored | No recording, no audio buffers (C29). Logs carry IDs and statuses, never numbers or speech |

Settings: `CARTESIA_AGENT_VOICE_ID` (required for speech), `CARTESIA_STT_MODEL`, `CARTESIA_TTS_MODEL`, and `PUBLIC_BASE_URL` for Twilio to reach us. The Pipecat worker's idle timeout is off; its default would cancel the stream after 5 minutes on hold.

Live smoke test: `python -m app.phone.smoke` (steps in the README). It dials only the mock line (`MockLineOnly` refuses any other number a case resolves to) or, with `--own-number`, `PHONE_SMOKE_DIAL_NUMBER` through `SmokeNumberSource`, which only `smoke.py` has (a test checks nothing in `app` imports it). It rings only `PHONE_SMOKE_USER_NUMBER` as the applicant, and only with `--bridge`. Smoke calls are dev calls to our own lines, so they use a fake job and fake stores and write nothing.

## The bridge (Phase 3)

When a person is detected, the runner says the intro (in the background) and calls `ring_user`; the applicant joins a conference, and `connect_user` moves the agency leg in after them. Proven live in [spikes/bridge/README.md](../../spikes/bridge/README.md), rebuilt here.

| Route | What arrives | Becomes |
|---|---|---|
| `POST /phone/calls/{call_id}/user/status` | The applicant leg's status callbacks | Before a key: `busy`/`no-answer`/`failed`/`canceled` → `UserUnreachable` with that reason, `completed` (picked up, put down) → `UserUnreachable("no_key_press")`. After joining: ended → `UserLeft` |
| `POST /phone/calls/{call_id}/user/joined` | The join gate's `<Gather>` action: any key | `UserAnswered`, and TwiML that puts the applicant in `bridge-{call_id}`. Too late (the agency left, the runner gave up, we hung up) → `<Hangup/>` |
| `POST /phone/calls/{call_id}/user/missed` | The gate's fall-through: no key in time | `UserUnreachable("no_key_press")`, `<Hangup/>` |
| `WS /phone/calls/{call_id}/fork/{speaker}` | A listen-only `<Start><Stream>` of one joined leg (`agency` or `user`) | VAD → Ink → `LineListener` → `Overheard(speaker, text)` per finished turn. Only that leg's own SID may open it |

| Piece | What it does |
|---|---|
| Join gate | Carrier voicemail picks up declined and unanswered calls, and Twilio reports it as answered, so the applicant's leg says `call_lines.JOIN_PROMPTS[user_language]` twice and waits 15 s for **any** key; voicemail can't press one, so the rep never hears it. The orchestrator's "Someone picked up, I'm calling you now" WhatsApp (C36) has already told them it's coming |
| No gate (`PHONE_JOIN_GATE=false`, the demo) | The applicant's leg runs the conference TwiML itself, so picking up joins at once. The first sign of it, the `in-progress` status callback or the leg's fork attaching, emits `UserAnswered` (once). `busy`/`no-answer`/`failed` are still `UserUnreachable`. Voicemail that picks up joins too: accepted for the demo phone only. The listen leg keeps its gate |
| Gate language | `CallJob.user_language` (from `users.language`, the language the user writes to us in), passed to `TwilioTelephony(user_language=…)`; spoken by Twilio `<Say>` with a native voice per language (`en`, `es`). A language with no prompt yet gets English, logged |
| Ringing | `ring_user` reads the number from `NumberSource.user_number` (C6) and rings 30 s. A failed REST call is `UserUnreachable("failed")`, not a crash, so the rep still hears the call-back line |
| `connect_user` | REST update of the agency leg to the conference. That ends its media stream, which is expected, not a hang-up; from then on `say` and `press_keys` raise `LineClosed`: the agent is silent (rule 3) |
| Conference | No beep, no hold music, either side leaving ends it. Key presses still reach the agency through it |
| Forks | One per leg, of that leg's own `inbound_track`, so each carries one speaker (Pipecat's serializer ignores `track`, and an `outbound_track` fork never opened in the spike). They only feed the transcript; status callbacks say when the call ends |
| `hang_up` | Also ends the applicant's leg (`canceled` while ringing, `completed` once answered) |
| Not stored | No `record` anywhere (C29). The applicant's number is never logged |

Manual checks on real phones, and their results: [phone-live-checks.md](phone-live-checks.md).

## Listening in (sitting in on the call)

The user can ask over WhatsApp ("sit in", "dial me in") to hear the call while it runs: the menus, the agent's choices, the hold music. They're muted. The orchestrator's `listen_to_call(case_id)` tool checks the case is theirs, finds its live call, and calls `app.phone.control.request_listen_in(call_id)`. That's in process, like `ask_user` going the other way. It returns `ringing`, `already_listening`, `rep_on_line` (the bridge will ring them), or `call_over`.

The flow: `request_listen_in` → the line emits `ListenRequested` → the runner calls `telephony.listen_in(call_id, user_id)` → their own number (C6) rings on a **separate call** with a listen gate (`call_lines.LISTEN_PROMPTS`, any key) → `ListenStarted`, and the leg goes on a media stream we only write to. The runner only logs `ListenStarted`/`ListenEnded`. No call state changes, so nothing a listener does can end or steer the agency call.

| Route | What arrives | Becomes |
|---|---|---|
| `POST /phone/calls/{call_id}/listen/status` | The listen leg's status callbacks | Before a key: unreached → `ListenEnded(busy/no_answer/failed)`, `completed` → `ListenEnded("no_key_press")`. Listening: ended → `ListenEnded("hung_up")`. Once the leg has joined the bridge, they go to the applicant's handling (`UserLeft`) |
| `POST /phone/calls/{call_id}/listen/joined` | The listen gate's key press | `ListenStarted`, and `<Connect><Stream>` to the listen stream. Too late → `<Hangup/>` |
| `POST /phone/calls/{call_id}/listen/missed` | No key in time | `ListenEnded("no_key_press")`, `<Hangup/>` |
| `WS /phone/calls/{call_id}/listen/stream` | The listen leg's stream | `listen_audio.run_listener`: we write the call into it. What the user says is read only to notice the end, never kept or forwarded |

| Piece | What it does |
|---|---|
| Audio | Two `ListenTap`s on the agency stream feed a `ListenMixer` on the line: the agency's frames as they arrive, and the agent's TTS buffered and laid over them. The agency's real-time frames set the pace, so TTS that comes faster than it plays doesn't run ahead. A `ListenSink` writes μ-law `media` messages from its own task and drops audio rather than slow the agency pipeline. About 2 s of silence during each `press_keys` stream swap |
| Hanging up | Ends only the listen leg (a separate call). The agent keeps its line, and the user can ask again |
| A person picks up | `ring_user` sees a listening leg and moves it into the conference (with its user fork) instead of ringing: `UserAnswered` follows at once, with no second ring and no gate, and the rest of the bridge is unchanged. They hear the intro live. A leg still at its gate is ended and the user is rung as usual. A failed move ends the leg and rings |
| Gate | Voicemail would otherwise record the agency (C29) |
| `hang_up` | Also ends a listen leg that's ringing or listening |

## Hanging up on request

The user can tell the WhatsApp agent "hang up now". The orchestrator's `hang_up_call(case_id)` tool checks the case is theirs, finds its live call, and calls `app.phone.control.request_hang_up(call_id)`, which returns `ending` or `call_over`. The line emits `HangUpRequested`, and the runner fires `Trigger.USER_ENDED`, so the call ends through wrap-up with a saved report like any other.

| State | What happens |
|---|---|
| `dialing`, `menu`, `hold` | Wrap-up hangs up. Outcome `cancelled` |
| `human_detected`, `bridging` | The agent cuts off what it's saying and tells the rep `call_lines.USER_ENDED` (fixed text: the applicant asked to end the call and will call back), then hangs up every leg, the applicant's ringing one included. Outcome `cancelled` |
| `connected` | The agent stays silent (rule 3); wrap-up hangs up both legs. No outcome from the state machine: the report reads the conversation |

`call.ended` carries `cause: "user_ended"`. A `cancelled` report gets `summary.cancelled` on WhatsApp ("I ended the call, as you asked") and no automatic retry offer.

**Open, for the team:** no `call.listen_in_*` event types yet (a shared-contract change, plus feed templates), so the dashboard doesn't show listening; it's in the logs and the runner's steps. The user's own WhatsApp request is what consents to the ring (rule 4).

**Open, for the team:**
- **The any-key gate is the current choice, not a team decision yet.** It means "answered" in the Plan.md failure rules is "pressed a key", and the worst case before the call-back line is about 55 s (30 s ringing, the prompt twice, 15 s). Alternatives if the team objects: answering-machine detection, or detecting voicemail after bridging.
- Dari (or any language past `en`/`es`) needs a `JOIN_PROMPTS` entry; Twilio may have no Dari voice, so it will likely be a pre-recorded clip played with `<Play>`.
- Not yet run live: the agency hanging up first after the bridge (spike row 5).
- No `bridging → hold`: a "person" who transfers after the ring can't be undone (state.py).

## The call report and the worker (Phase 4)

**Report** (`report.py`, prompt in `report_prompts.py`, client in `report_llm.py`). Calls that never reached a person (no answer, hold timeout, hang-up, abort, applicant unreachable) get the deterministic `build_report`, with no model call; it's still the runner's default. A connected call gets `LlmReportBuilder`: one Claude call (`settings.model_default`) over the brief's goal and dates, the call date, and the transcript (repeated hold lines collapsed; a very long call keeps its start and end). The model drafts; code owns the rest:

| Field | Who decides |
|---|---|
| `outcome` | The state machine for unconnected calls; the model picks `resolved`, `partial`, or `failed` for connected ones |
| `reference_number`, `rep_name` | The model, kept only if found in what the agency side said (digits read out one by one, "oh" as zero, count) |
| `next_steps_en`, `proposed_facts` | The model, at most five each; an item that looks like a receipt number or A-Number, or carries one of the case's identifier values, is dropped (C34, C35) |
| `new_deadlines` | The model; kept if it parses as a date between the call date and two years after |
| fact `source`, `sensitivity` | Code: `from_call`, always `sensitive` (an immigration fact, C15, C25) |
| `followup_needed` | The model's answer, forced true for anything short of `resolved` |
| `summary_en` | The model (two or three sentences for the orchestrator to translate and send); dropped if it carries an identifier. None on the deterministic report |

Any failure (timeout, API error, bad output, a bug) logs with the call and case IDs and falls back to `build_report`, so a report is always saved. Asylum claim details (C34) are kept out by the prompt only; code can't spot them. Manual eval against real Claude: `python -m app.phone.report_eval` (from `backend/`, costs a little).

**Worker** (`worker.py`). `PhoneWorker` polls `claim_next(JobType.CALL)` about once a second and runs each call in its own task. `handle_call_job` builds `CallDeps` from `PhoneDeps` (the real DB and relay adapters by default; the line from a `LineFactory`), runs the call, then `jobs.finish(job_id, report)` and, if the report proposes facts, enqueues a `MemoryWriteJob` (`from_call`, `source_ref` = the call ID). The runner creates the `calls` row (C7) through `DbCallStore`, so the only table writes are `writes.phone` plus `jobs`. A call that ended badly is still `done`, with that outcome in its report; the job is `failed` (error: the exception's type name only) only when there's no report: a bad payload, or the call couldn't be created or its report saved. A failed `memory_write` enqueue is logged and leaves the job `done`. `main.py` starts it when `PHONE_WORKER=true` (default false) and every live-call setting is set (`missing_settings`: the Anthropic, Twilio and Cartesia keys, the agent number and voice, `PUBLIC_BASE_URL`); otherwise it logs what's missing and starts nothing. `real_deps(settings)` makes a new `TwilioTelephony` per job (`twilio_lines`), with the job's `user_language` for the join gate. Only the deployed backend sets `PHONE_WORKER=true` on the shared database, and never alongside the dev fake phone (`POST /dev/fake-phone`), which claims the same `call` jobs.

## Open, with person 2 (`relay/ask_user.py`)

- **Cancelling `ask`** (the agency hangs up while the user decides) leaves the `questions` row `open`, so the user's next "1" is taken as an answer to a dead call. Suggested: on `CancelledError`, call `time_out_question` and re-raise.
- **The reply doesn't say whether it timed out.** The runner can't tell "user chose 1" from "default 1". Fine for now (the events say so); raise it if the call report needs it.
