# Phone agent: ports and fakes

Owner: person 4. Implements Plan.md → Phone agent, H2, P1–P3; it doesn't change them. Code: `backend/app/phone/`.

The call runner talks to the outside world only through the Protocols in `ports.py`, bundled per call in `CallDeps`. Each has a real adapter and an in-memory fake, so a whole call runs (and tests) with no Twilio, Neon, or WhatsApp.

## Ports

| Port | What it is | Real adapter | Fake |
|---|---|---|---|
| `Telephony` | One call's line: `dial_agency`, `say`, `press_keys`, `ring_user`, `connect_user`, `hang_up`, plus `events()`, the stream of everything that happens (`line.py`) | Phase 2 (Twilio + Pipecat) | `FakeTelephony`: a script, plus an optional `responder` that reacts to actions (how the simulator plugs in a phone tree) |
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

- Wait only through `Clock` (`clock.sleep`, `with_timeout`), never `asyncio.sleep` or `asyncio.timeout`, or virtual time stops working.
- Don't await `ask_user` inline: run it as a task and keep reading `events()` (menus reprompt and hang up long before 45 s). `test_a_whole_call_runs_on_fakes` shows the pattern.
- The relay logs every `call.ask_user*` event; the phone agent logs none of them.
- Actions after the line ends raise `LineClosed`; a blocked identifier raises `BlockedIdentifier` and nothing is sent.

## Open, with person 2 (`relay/ask_user.py`)

- **Cancelling `ask`** (the agency hangs up while the user decides) leaves the `questions` row `open`, so the user's next "1" is taken as an answer to a dead call. Suggested: on `CancelledError`, call `time_out_question` and re-raise.
- **The reply doesn't say whether it timed out.** The runner can't tell "user chose 1" from "default 1". Fine for now (the events say so); raise it if the call report needs it.
