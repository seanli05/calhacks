# Spike: bridging the user into the agency call

Throwaway experiment for the bridge sequence that the phone agent's `Telephony` port assumes ([ports.py](../../backend/app/phone/ports.py): `ring_user`, `connect_user`). Two questions:

1. **Transcript after the bridge.** Moving the agency leg into a conference ends its `<Connect><Stream>`. Does a `<Start><Stream>` fork in the conference TwiML still give us both sides as text, labelled by speaker? The reference number and next steps are spoken after the user joins, and P3 needs them.
2. **The gap.** How long is it between the user answering and the agency leg joining the conference, and what does the agency side hear during it?

No audio is stored (C29). Nothing here sets `record`.

## How it works

| Step | What happens |
|---|---|
| `place_call` | The agent number dials the agency (the mock line, or `--agency-number`). The call runs `<Connect><Stream>` to `/ws`, a two-way pipeline (VAD → Cartesia STT → log → TTS). |
| `POST /bridge` | Stand-in for "human detected". It says the intro on `/ws` and REST-creates the user leg (`timeout=30`) to `BRIDGE_SPIKE_USER_NUMBER`. |
| User answers | Twilio fetches `/twiml/user`, which plays "Press 1 to join" (voicemail also counts as answered, and it can't press a key). On a key press, `/twiml/user/joined` puts the user in `bridge-{agency_sid}`. In the background, the agency call is updated to `<Start>` two forks and then the same `<Conference>`. |
| After the bridge | `/ws-fork` runs a receive-only STT pipeline per fork. `inbound_track` is the agency and `outbound_track` (what the conference plays to the agency leg) is the user. We use two one-track forks because Pipecat's Twilio serializer ignores the `track` field. |
| User doesn't answer | `/status/user` sees `busy` / `no-answer` / `failed`. It says the "account holder will call back" line on `/ws`, then hangs up the agency leg (Plan.md failure rule). |

Every serializer has `auto_hang_up=False`. `/ws` ends because we move the call, and the default would hang the call up.

## Run

Needs, in the repo-root `.env`:
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_AGENT_NUMBER`, `TWILIO_MOCK_AGENCY_NUMBER`, `CARTESIA_API_KEY`, `PUBLIC_BASE_URL`
- `BRIDGE_SPIKE_USER_NUMBER`: your phone. Only in your own `.env`, never in `.env.example`.
- `BRIDGE_SPIKE_VOICE_ID`: any Cartesia voice ID.

Anything missing is named on startup.

```bash
ngrok http 8000                                                 # put the https URL in PUBLIC_BASE_URL
PYTHONPATH=backend uvicorn spikes.bridge.server:app --port 8000   # no --workers: state is in-process
PYTHONPATH=backend python -m spikes.bridge.place_call             # or --agency-number <second phone>
curl -X POST localhost:8000/bridge                                # once the agency greeting is logged
```

The server logs:
- `MARK t=+X.Xs ...` for each step, timed from `/bridge`.
- `HEARD stream=... t=+X.Xs {TranscriptLine JSON}` for each final transcript.

**Default take (about 1 minute):**
1. Bridge as soon as the mock's greeting shows up on `stream=pre`, and answer your phone.
2. Stay quiet a few seconds. The mock's menu should show up on `fork-agency`.
3. Say a sentence. It should show up on `fork-user`.
4. Hang up.

You don't need to navigate the mock's tree. To test a spoken reference number, use `--agency-number` with a second phone, answer it as the "officer", and read one out after the bridge.

## Test matrix

| # | Run | Check |
|---|---|---|
| 1 | Happy path | Ring < 5 s after `/bridge`. The gap from user answer to agency join, and what the agency hears in it. `/ws` ends without hanging up the call. Both forks connect and label lines correctly. A reference number (two-phone setup) lands on `fork-agency`. STT delay on the forks. |
| 2 | Decline the call | `busy`/`failed` arrives. The call-back line plays, and the agency leg ends. |
| 3 | Let it ring | `no-answer` at about 30 s, **or** the carrier's voicemail answers first and Twilio reports it as answered. |
| 4 | User hangs up first | The agency leg ends (`endConferenceOnExit`), and the forks close. |
| 5 | Agency hangs up first | The user leg ends, and nothing is left running. |
| 6 | Keypad after the bridge | Expected: no effect, because conferences don't relay DTMF. |

## Findings

Take 1 on 2026-10-24: Twilio → mock agency line, user leg to a personal phone. Timings are from `/bridge`.

| # | Result | Timing | Notes |
|---|---|---|---|
| 1 | **Partial** | Ringing at 3.7 s. Intro played 0.2–6.4 s. User answered at 7.8 s; both sides joined the conference at 8.3 s. `fork-agency` connected at 8.5 s and `stream=pre` ended at 9.0 s. Fork STT came about 0.4 s after speech ended. | There was no dead air at the join. The user heard the mock finishing its menu prompt right away. `stream=pre` closed without hanging up the call. `fork-agency` transcribed correctly, labelled `agency`. **`fork-user` (the agency leg's `outbound_track`) never connected.** Changed to fork the user leg's own `inbound_track`; needs a re-run. The agency hears silence from the end of the intro until the user joins (about 2 s here): judged acceptable. |
| 1 | **Pass** (take 2, user fork on the user leg's `inbound_track`) | Ringing at 2.4 s. User answered at 6.0 s; both sides joined at 6.5 s. `fork-agency` connected at 6.6 s, `fork-user` at 6.7 s, and `stream=pre` ended at 7.2 s. | Both forks transcribed with clean speaker separation, even when the user talked over the menu. The agency reacted to the user's speech, so the user→agency audio path works. STT slips were minor ("Once hear these options again"). |
| 2 + 3 | **Fail → fixed** (take 3) | Declined at about 4 s. The carrier's voicemail picked up at 6.0 s. | The carrier forwards both declined and unanswered calls to voicemail, and Twilio reports that as `in-progress`, so the agency got bridged into the user's voicemail (`fork-user` heard the voicemail greeting) and the call-back line never ran. **Fix:** a key-press gate on the user leg (`/twiml/user` → `<Gather>` "Press 1 to join" → `/twiml/user/joined`). No key within 15 s → `/twiml/user/missed` → unreachable path. |
| 2 + 3 | **Pass** (take 4, with the gate) | Voicemail picked up at 8.1 s. `no_key_press` at 32.3 s (prompt twice + 15 s). Call-back line played 32.5–38.0 s. Agency leg hung up at 39.9 s. | The agency never joined a conference and no forks opened, so the officer never heard the voicemail. The user's voicemail holds only our gate prompt. |
| 4 | **Pass** (takes 1 and 2) | Teardown about 1 s | The user hung up. Conference end, agency leave, and both forks closed. Nothing was left running. |
| 5 | | | |
| 6 | **Pass, unexpected** | Agency responded about 4 s after the key press | The user pressed 1 on the keypad (no speech on `fork-user`), and the mock moved to that branch. Key presses do reach the agency through the conference, so the user can use the keypad if a rep's system asks. |

**Open: how the user joins the call.** The "Press 1 to join" gate is a stopgap that keeps voicemail out of the bridge, not a settled design. A bot asking the user to press a key may be the wrong experience for this product. Alternatives to weigh later:
- a WhatsApp heads-up just before ringing, so the user expects the call
- Twilio answering-machine detection (no user step, but it guesses and does badly on a silent pickup)
- bridging right away and detecting voicemail afterwards

Whatever replaces it must still keep the rep away from voicemail, and any prompt must be in the user's language (rule 6).

Recommendation for the `Telephony` adapter: _to fill in after the runs_. Either keep the port as is, or name what must change (e.g. `<Start><Transcription>` if forks fail, `machine_detection` or a "press any key" step if voicemail answers). The real adapter should also validate Twilio webhook signatures; this spike doesn't.
