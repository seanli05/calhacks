# Spike: key presses on the mock agency line

Throwaway experiment for the "Open technical risk" in [Plan.md](../../Plan.md). The question: can the backend place a Twilio call to the mock agency, hear it through Pipecat, and get past the main menu with "2"?

It tries three ways of pressing 2 at the main menu, then checks whether the appointment menu follows.

| Mode | How "2" is sent |
|---|---|
| `dtmf` | Pipecat `OutputDTMFUrgentFrame` |
| `speak` | Cartesia TTS says "two" |
| `rest` | REST call update: `<Play digits="w2"/>`, then a new `<Connect><Stream>` (leg 2) to hear the result |

## What the source says (Pipecat 1.14.0, twilio 9.12.0)

- **Twilio Media Streams can't carry outbound DTMF.** The only messages a server can send to Twilio are `media`, `mark` and `clear`. `dtmf` exists only from Twilio to us ([docs](https://www.twilio.com/docs/voice/media-streams/websocket-messages)).
- **So Pipecat plays DTMF as tones.** `TwilioFrameSerializer.serialize()` (`pipecat/serializers/twilio.py`) has no DTMF branch. `FastAPIWebsocketOutputTransport` doesn't override `_supports_native_dtmf()` (only Daily does). `BaseOutputTransport.write_dtmf` therefore falls back to `_write_dtmf_audio`, which plays the bundled `pipecat/audio/dtmf/dtmf-*.wav` tones as ordinary μ-law audio. `dtmf` mode tests whether those in-band tones survive Twilio → PSTN → Cartesia Line and reach the line as a key press (`UserDtmfSent`).
- **IVR helper:** `pipecat/extensions/ivr/ivr_navigator.py` (`IVRNavigator`) is an LLM-driven navigator that emits `<dtmf>N</dtmf>`. Those become `OutputDTMFUrgentFrame`, so it uses the same in-band path. It's a candidate for the real phone agent and isn't used here.
- **Hang-up:** `TwilioFrameSerializer` needs `call_sid`, `account_sid` and `auth_token` for `auto_hang_up`. On End/Cancel it POSTs `Status=completed` to the Calls API. Rest leg 1 turns this off, because otherwise our own redirect would end the call.
- **REST mode** ends the stream: Twilio drops the websocket when the TwiML changes. The TwiML reconnects right after the digits, so we lose about 1–2 s of audio, and the pipeline is a new one.

## Run

Needs, in the repo-root `.env`:
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_AGENT_NUMBER`, `TWILIO_MOCK_AGENCY_NUMBER`, `CARTESIA_API_KEY`, `PUBLIC_BASE_URL`
- `DTMF_SPIKE_VOICE_ID` (any Cartesia voice ID), for `speak` mode only

Anything missing is named on startup. A Twilio trial account can only dial verified numbers.

```bash
ngrok http 8000                                              # put the https URL in PUBLIC_BASE_URL
PYTHONPATH=backend uvicorn spikes.dtmf.server:app --port 8000
PYTHONPATH=backend python -m spikes.dtmf.place_call --mode dtmf    # then speak, then rest
```

The server logs each transcribed utterance with a timestamp, then `acting mode=...` and one `RESULT PASS|FAIL ...` line.

How a run is scored:
- **Pass:** the appointment menu is heard ("biometrics", "asylum interview" or "naturalization interview").
- **Fail:** the line repeats the main menu, says "not a valid option", gives its no-input reprompt, or nothing arrives within 20 s.

On the mock line's side, the call's logs in the Cartesia dashboard (play.cartesia.ai) show whether it got `UserDtmfSent` or a spoken turn.

## Findings

Calls on 2026-10-23, Twilio (upgraded account) → Cartesia Line mock agency. The "latency" column is the time from acting to the first transcribed line of the appointment menu.

| Mode | Result | Latency | Notes |
|---|---|---|---|
| dtmf | **FAIL** | n/a | About 13 s after the tone, the line said "Sorry, I didn't get a response." That's its 12 s no-input timer, so no key press reached it at all. |
| speak | **PASS** | 4.9 s | TTS said "two" about 1 s after the menu ended, and the line moved to the appointment menu. |
| rest | **PASS** | about 5 s | Leg 1 dropped as expected. Leg 2 connected about 2 s later and still heard the appointment menu's first line. |

What this shows:
- **In-band DTMF over Media Streams doesn't reach Cartesia Line.** `rest` passing rules out the mock line: it handles real key presses fine. The tone audio Pipecat sends is lost somewhere in Twilio → PSTN → Cartesia, or Cartesia only detects out-of-band (RFC 2833) digits.
- **Speaking works with no stream interruption**, at about the same latency as REST.
- **The STT splits prompts unpredictably.** The last menu line was once heard as "To hear these options again," + "9." with "press" dropped. Any menu matching must allow for missing words, not only exact phrases.
- **Twilio account requirements:** trial accounts can't use inline TwiML or `<Stream>`, and calling +1 numbers needs an approved Trust Hub Primary Compliance Profile. The demo account needs both sorted.

Recommendation for the phone agent:
1. **Primary: speak the choice** (digit or option name) through TTS on the live stream, once the prompt has finished. That's VAD silence plus about 1 s, well inside the line's 12 s timer. This keeps one continuous stream for hold detection and the bridge. It works on the mock line, which accepts spoken digits.
2. **Fallback for keypad-only steps:** a REST call update with `<Play digits>`, then `<Connect><Stream>` again. Batch digits (e.g. a whole receipt number + `#`) to keep reconnects to a minimum. Agent state has to survive the new stream.
3. **Don't rely on `OutputDTMFUrgentFrame`** over Twilio Media Streams, which includes Pipecat's `IVRNavigator` as-is.
