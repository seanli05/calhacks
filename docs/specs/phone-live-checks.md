# Phone agent: live checks

Owner: person 4. Manual calls to run on real phones, with what each should show. Fakes cover the logic (`backend/tests/test_phone_*.py`); these checks cover what only a real line can: carriers, voicemail, Twilio's callback timing, speech-to-text, and how the agent sounds. Setup and commands: README → the live smoke test. How the line works: [phone-ports.md](phone-ports.md).

Mark a row when you run it: ✅ passed, ❌ failed (add a note), or leave it blank. Add a date.

## Setups

| Name | Command (from `backend/`) | Who plays what |
|---|---|---|
| **Two phones** | `python -m app.phone.smoke --own-number --runner --bridge --language en` | You play the agency (`PHONE_SMOKE_DIAL_NUMBER`); a friend plays the applicant (`PHONE_SMOKE_USER_NUMBER`) |
| **Mock line** | `python -m app.phone.smoke --runner --bridge` | The mock USCIS line plays the agency; you play the applicant (`PHONE_SMOKE_USER_NUMBER` = your phone) |
| **Manual** | `python -m app.phone.smoke --own-number --bridge` | You play the agency, and type `say`, `keys`, `bridge` yourself |

Before each session: ngrok up, `PUBLIC_BASE_URL` matches it, backend stopped, and the worktree's `.env` has both numbers.

## The bridge (Two phones)

The friend's phone rings for 15 s at most (C42). Every way to miss the ring (B2–B5) now rings the friend a second time first: you hear "I'm calling them again", and only a second miss gets the call-back line. B2–B5 test the join gate (`PHONE_JOIN_GATE=true`, the default); G1 tests the demo's `--no-gate`.

| # | You (agency) | Friend (applicant) | Expect | Status |
|---|---|---|---|---|
| B1 | Greet like a rep | Answers, presses a key | Ring < 5 s after your greeting; you hear the intro; you're connected; the transcript shows `agency:` / `user:` lines | ✅ 2026-10-24 |
| B2 | Greet like a rep | Declines (both rings) | After the second missed ring (each 15 s at most) you hear "the account holder will call back", then your call ends. Outcome `user_unreachable`, reason `no_key_press` (carrier voicemail took the call) or `busy` | |
| B3 | Greet like a rep | Lets it ring out | Same as B2. You never hear the friend's voicemail greeting | |
| B4 | Greet like a rep | Answers, presses nothing | The prompt plays twice; ~15 s later the friend is hung up and you hear the call-back line. Reason `no_key_press` | |
| B5 | Greet like a rep | Answers, then hangs up without a key | Same as B4, and sooner | |
| B6 | Stay on after the bridge | Joins, then hangs up | Your call drops; the run ends `user_left` → `ended` | |
| B7 | Hang up after the bridge | Joins, stays on | The friend's call drops; the run ends `agency_hung_up` → `ended` | ✅ 2026-10-24 (confirm the friend's phone dropped) |
| B8 | Hang up while the friend's phone rings | Doesn't answer yet | The friend's ringing stops (the leg is cancelled); outcome `failed` | |
| B9 | Greet in English | Answers; run with `--language es` | Friend hears the Spanish prompt in a native Spanish voice, not an English accent | |
| B10 | After the bridge, ask the friend for name and date of birth, then read out a reference number with letters and digits ("IOE, 0, 9, 1, 2…") | Answers your questions | The reference number appears whole in the saved transcript under `agency`; the agent says nothing | |
| B11 | After the bridge, ask "press 1 if you're the applicant" | Presses 1 | Expected: you hear the tone (key presses cross the conference) | |
| B12 | Keep the bridged call going 5+ minutes, talking now and then | Talks back | Both forks keep transcribing; no drop; nothing closes early | |
| B13 | Greet like a rep | Declines the first ring, answers the second | You hear "The applicant didn't pick up, so I'm calling them again"; the friend's phone rings again (and gets the WhatsApp nudge with the full app); answering bridges them | |
| G1 | Greet like a rep; run with `--no-gate` | Answers | No prompt: the friend hears you within ~2 s of picking up; the transcript shows `agency:` / `user:` lines | |

## While the applicant's phone rings (Two phones)

These test the minute the agent is alone with the rep. It must never answer for the applicant (rule 3) or give an identifier (C35).

| # | You (agency) | Friend | Expect | Status |
|---|---|---|---|---|
| R1 | Right after the intro, ask "Can I get the receipt number?" | Waits ~10 s before answering | The agent says the fixed holding line ("The applicant is joining now and will answer for themselves"), nothing else, no digits | |
| R2 | Ask "What's the applicant's name?" then "Date of birth?" ~3 s apart | Waits | At most one holding line for the two (≥ 8 s apart), never an answer | |
| R3 | Talk over the intro ("Hello? Who is this?") | Waits | No second line on top of the intro | |
| R4 | Say "Let me transfer you", then play hold music | Answers later | Known gap: there's no `bridging → hold`, so the agent treats it as still bridging. Note what the friend hears when they join (music) | |

## Finding the person (Two phones or Manual)

The phase classifier must find a real person fast and never ring the applicant for a recording.

| # | You (agency) | Expect | Status |
|---|---|---|---|
| D1 | A bare "Hello?" and then silence | Ideally a person is detected; a 0.5 s VAD start may miss a very short "Hello?". Note what happened | |
| D2 | "USCIS, this is Maria, badge 4471, how can I help?" | Person; the badge number never comes back from the agent | |
| D3 | A recorded-sounding line: "Your call is important to us. Please stay on the line." | Hold, not a person: nobody is rung | |
| D4 | "Thank you for holding" in a friendly voice, then silence | Still hold until a real question or name; no ring | |
| D5 | A short menu: "For case status, press 1. For an interview, press 2." | The agent answers by speaking the option (C37), only after the whole prompt and ~2 s of quiet | |
| D6 | A menu that asks "Enter your 13-character receipt number" | The agent never says or keys it (C35): it asks for a representative, or asks the user | |
| D7 | Play music 10+ s into the phone, then greet as a rep | `menu → hold` on the music, then a person; ring < 5 s | |
| D8 | Let your own phone go to voicemail (don't answer) | Note what happens: your voicemail greeting ("you've reached…, leave a message") could pass for a person. If it rings the friend, that's a finding | |
| D9 | Greet with loud background noise (TV, street) | Still a person; no false turns before you speak | |

## Mock line, end to end

The real menu and hold path into the bridge. The mock is a test target, not a spec: if it handles reasonable agent behaviour badly, fix the mock.

| # | Do | Expect | Status |
|---|---|---|---|
| M1 | Run, answer your phone, press a key, verify as "Ana Morales, March 14, 1988" | Menu path chosen from the brief; hold; Officer Reyes; your phone rings < 5 s after the officer greets; the reference number is in the transcript | |
| M2 | Same, watching the terminal | The receipt number is never spoken or keyed (the guard flags nothing, the transcript has no receipt digits) | |
| M3 | Don't answer your phone | Officer Reyes hears the call-back line; the call ends; outcome `user_unreachable` | |
| M4 | Set the job's hold limit shorter than the mock's hold | Hang-up on hold timeout; outcome `failed`, cause `hold_timeout` | |

## Findings

Write anything surprising here, with the date and the run file (`backend/smoke_runs/…`, local only).

- 2026-10-24, B1 + B7: human detected 0.92 on "This is Sean. How can I help you today?", ring ~2 s after the greeting ended; friend pressed a key ~9 s after picking up (the prompt); bridge clean, forks labelled correctly.
