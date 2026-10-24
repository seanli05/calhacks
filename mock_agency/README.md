# Mock agency line (USCIS asylum office)

A demo-only phone line, hosted on [Cartesia Line](https://docs.cartesia.ai/line/introduction), that our phone agent calls instead of a real agency. It plays a U.S. Citizenship and Immigration Services contact line for the demo case: an **I-797C asylum interview notice** (Form I-589). The greeting says it's a demonstration line.

It is deliberately **English only**, because that's the barrier the project is about. There's no language menu and no interpreter option, the open steps need spoken English answers, the timeouts are short, and the officer is a brisk English-only rep who uses official terms and doesn't simplify. The officer stays polite: the barrier is the system, not the person.

It has three phases:

1. **Phone tree.** Deterministic, so every demo take behaves the same. It mixes keypad menus with open questions that need a spoken answer.
2. **Hold.** Timed hold announcements. Caller audio is ignored, so nothing cuts the hold short.
3. **Live officer.** Claude plays "Officer Daniel Reyes", who verifies identity with the applicant directly and answers questions from the notice.

## The call

```
Greeting ─► MAIN MENU        1 case status · 2 interview/appointment notice · 3 address · 4 work permit · 9 repeat
         2 ─► APPOINTMENT    1 biometrics · 2 asylum interview · 3 naturalization · * main menu
                2 ─► RECEIPT (open)       say "ZLA2690012345", or key 2690012345 then #
                       └─► CONFIRM        "I heard Z L A 2 6 9 ... say yes or press 1"
                     ─► REASON (open)     "In a few words, tell me why you're calling" (speech only)
                     ─► ATTENDANCE        1 attending as scheduled · 2 need a new date   ◄── the ask_user moment
                     ─► HOLD ─► OFFICER
```

What each step tests in the phone agent:

| Step | Kind | What it tests |
|---|---|---|
| Main menu, appointment | Closed (key or spoken number/option name) | Menu choices from the case brief |
| Wrong branches (1, 3, 4) | Dead end, back to main menu | Recovering from a wrong press |
| Receipt number | Open, spoken or keypad | Reading a `<ref:receipt_number>` aloud; a confirmation loop |
| Reason for calling | Open, **speech only** (keys get "please say your answer out loud") | Saying the call goal in plain words |
| Attendance | Closed, but depends on what the user wants | The agent can't know this, so it should ask the user on WhatsApp |
| Hold | Recorded announcements | Hold vs. human detection |
| Officer | Live LLM | Intro, bringing in the user, never answering identity questions (rule 3) |

Other behaviors:

- Pressing 0 or asking for a "representative" gets: choose a menu option first.
- After 12 s of silence the line reprompts. After 3 silent prompts in a row it hangs up.
- The receipt is matched on its 10 digits, because speech-to-text mishears letters far more often than digits. After 3 failed tries the line moves on anyway.
- Saying "reschedule" at the reason step skips the attendance menu.

The fictional case data (receipt number, A-number, name, date of birth, interview date and place) is in [agency/case_record.py](agency/case_record.py). The demo letter must use the same values.

**Officer identity check:** the officer asks for the applicant's full name and date of birth. The demo user should answer "Ana Morales, March 14, 1988". If the AI tries to answer for them, the officer refuses.

## Layout

| File | Role |
|---|---|
| [main.py](main.py) | Line entry point: phases, no-input timer, hold, officer handoff |
| [agency/ivr.py](agency/ivr.py) | The phone tree as a pure state machine (no SDK imports) |
| [agency/speech.py](agency/speech.py) | Transcript parsing: menu digits, yes/no, receipt numbers, reason topics |
| [agency/prompts.py](agency/prompts.py) | Every line the menu says, plus the officer's system prompt |
| [agency/case_record.py](agency/case_record.py) | The fictional demo case |
| [agency/config.py](agency/config.py) | Settings from env vars |

This folder deploys to Cartesia as its own project, with its own [pyproject.toml](pyproject.toml) and [cartesia.toml](cartesia.toml). It imports nothing from the rest of the repo.

## Environment

| Var | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | | For the officer |
| `MOCK_AGENCY_OFFICER_MODEL` | yes | | LiteLLM string, e.g. `anthropic/claude-haiku-5-5` (fast model; it's a live voice turn) |
| `MOCK_AGENCY_HOLD_SECONDS` | no | `45` | Total hold time. Keep it short for the video. |
| `MOCK_AGENCY_HOLD_ANNOUNCE_EVERY_S` | no | `15` | Gap between hold announcements |
| `MOCK_AGENCY_NO_INPUT_SECONDS` | no | `12` | Silence before a reprompt, counted only once the line stops talking |
| `MOCK_AGENCY_OFFICER_NAME` | no | `Daniel Reyes` | |
| `MOCK_AGENCY_IVR_VOICE_ID` | no | agent's default voice | Cartesia voice for the menu |
| `MOCK_AGENCY_OFFICER_VOICE_ID` | no | agent's default voice | Use a different, warmer voice so the human pickup is obvious on video |

## Run locally

```bash
cd mock_agency
uv venv --python 3.12 && source .venv/bin/activate   # separate from the backend venv
uv pip install -e .
ANTHROPIC_API_KEY=... MOCK_AGENCY_OFFICER_MODEL=anthropic/claude-haiku-5-5 \
  MOCK_AGENCY_HOLD_SECONDS=10 python main.py
cartesia chat 8000   # in another terminal: text chat; type "1", "two", "ZLA2690012345", ...
```

Text chat can't send key presses; the phone tree takes spoken digits too, so type them. The keypad paths are covered by the tests:

```bash
pytest mock_agency   # from the repo root, in the backend venv; tests don't need the Line SDK
```

## Deploy and get a number

```bash
curl -fsSL https://cartesia.sh | sh        # Cartesia CLI
cartesia auth login
cd mock_agency
cartesia init                               # link to a new agent (first time only)
cartesia env set ANTHROPIC_API_KEY=... MOCK_AGENCY_OFFICER_MODEL=anthropic/claude-haiku-5-5
cartesia deploy && cartesia status
```

Then attach a phone number to the agent in the [Cartesia dashboard](https://play.cartesia.ai). That number is the mock agency's number (`MOCK_AGENCY_NUMBER` in the backend `.env`). Test it by calling it from your own phone.

## Known limits

- No hold music. Line speaks text only, so hold is announcements with silence in between.
- Like a real line, the caller can't talk over recorded prompts, but can interrupt the officer. Menu and hold prompts always play to the end, and speech that ends mid-prompt is dropped (logged as `ignored_speech_during_prompt`). Key presses register mid-prompt and take effect once the prompt finishes. The officer stops talking when interrupted and responds to what was said.
- One fixed case. Any other receipt number gets "couldn't find a case".
