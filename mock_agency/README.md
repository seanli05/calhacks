# Mock agency line (USCIS asylum office)

A demo-only phone line, hosted on [Cartesia Line](https://docs.cartesia.ai/line/introduction), that our phone agent calls instead of a real agency. It plays a U.S. Citizenship and Immigration Services contact line for the demo case: an **I-797C asylum interview notice** (Form I-589). The greeting says it's a demonstration line.

It is deliberately **English only**, because that's the barrier the project is about. There's no language menu and no interpreter option, the open steps need spoken English answers, and the timeouts are short. The officer speaks only English, but is otherwise easy to work with, so a test call can reach a full resolution.

In the default `demo` mode it has three phases:

1. **Phone tree.** Deterministic, so every demo take behaves the same. It mixes keypad menus with open questions that need a spoken answer.
2. **Hold.** Timed hold announcements. Caller audio is ignored, so nothing cuts the hold short.
3. **Live officer.** Claude plays "Officer Daniel Reyes", who resolves the caller's question from the notice.

## Modes

One per deploy, set with `MOCK_AGENCY_MODE`:

| Mode | The call | Use it for |
|---|---|---|
| `demo` (default) | Full phone tree, hold, then the officer | The demo, and testing the menu and hold |
| `quick` | A short greeting, then the officer picks up at once (no menu, no hold) | Testing live calling: human detection, the bridge, and what happens after the call is resolved |

To keep both handy, deploy the folder as two Cartesia agents on two numbers, and point the backend's `DEMO_DIAL_NUMBER` at the one you want.

## The call

```
Greeting ─► MAIN MENU        1 case status · 2 interview/appointment notice · 3 address · 4 work permit · 9 repeat
         2 ─► APPOINTMENT    1 biometrics · 2 asylum interview · 3 naturalization · * main menu
                2 ─► REASON (open)     "In a few words, tell me why you're calling" (speech only)
                     ─► ATTENDANCE        1 attending as scheduled · 2 need a new date   ◄── the ask_user moment
                     ─► HOLD ─► OFFICER
```

What each step tests in the phone agent:

| Step | Kind | What it tests |
|---|---|---|
| Main menu, appointment | Closed (key or spoken number/option name) | Menu choices from the case brief |
| Wrong branches (1, 3, 4) | Dead end, back to main menu | Recovering from a wrong press |
| Reason for calling | Open, **speech only** (keys get "please say your answer out loud") | Saying the call goal in plain words |
| Attendance | Closed, but depends on what the user wants | The agent can't know this, so it should ask the user on WhatsApp |
| Hold | Recorded announcements | Hold vs. human detection |
| Officer | Live LLM | Intro, bringing in the user, getting the call goal resolved |

Other behaviors:

- Pressing 0 or asking for a "representative" gets: choose a menu option first.
- After 12 s of silence the line reprompts. After 3 silent prompts in a row it hangs up.
- The menu never asks for an identifier (receipt number, A-Number, date of birth). The phone agent may not give one (Plan.md C35), and the officer doesn't ask either.
- Saying "reschedule" at the reason step skips the attendance menu.

The fictional case data (receipt number, A-number, name, date of birth, interview date and place) is in [agency/case_record.py](agency/case_record.py). The line knows one case per deploy, chosen with `MOCK_AGENCY_CASE`:

| `MOCK_AGENCY_CASE` | Case | Letter to photograph |
|---|---|---|
| `demo` (default) | `DEMO_CASE`: Ana Morales, Los Angeles Asylum Office, November 12. The backend's database seed and tests depend on it | `backend/tests/fixtures/research/letters/i797c_asylum_interview/page_1.png` (a research fixture; its name, office and dates differ from this case) |
| `sf_demo` | `SF_DEMO_CASE`: Mariam Namuna, San Francisco Asylum Office, November 25 | `demo/letters/i797c_mariam_namuna.png`, which matches it value for value (the demo video) |

**The officer** never asks for a name, date of birth, or case number, takes answers at face value, and asks only simple questions one at a time. It keeps each turn to a sentence or two and works the call to a resolution: it confirms the interview, and for a reschedule (or an interpreter who can't come) it moves the interview on the call into one of the case's two fixed openings (`reschedule_slots` in [agency/case_record.py](agency/case_record.py)), with no written request. Then it gives a reference number and ends the call.

## Layout

| File | Role |
|---|---|
| [main.py](main.py) | Line entry point: phases, no-input timer, hold, officer handoff |
| [agency/ivr.py](agency/ivr.py) | The phone tree as a pure state machine (no SDK imports) |
| [agency/speech.py](agency/speech.py) | Transcript parsing: menu digits, requests for a person, reason topics |
| [agency/prompts.py](agency/prompts.py) | Every line the menu says, plus the officer's system prompt |
| [agency/case_record.py](agency/case_record.py) | The fictional demo cases |
| [agency/config.py](agency/config.py) | Settings from env vars |

This folder deploys to Cartesia as its own project, with its own [pyproject.toml](pyproject.toml) and [cartesia.toml](cartesia.toml). It imports nothing from the rest of the repo.

## Environment

| Var | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | | For the officer |
| `MOCK_AGENCY_OFFICER_MODEL` | yes | | LiteLLM string, e.g. `anthropic/claude-haiku-5-5` (fast model; it's a live voice turn) |
| `MOCK_AGENCY_MODE` | no | `demo` | `demo` or `quick` (see [Modes](#modes)). Anything else fails at startup |
| `MOCK_AGENCY_CASE` | no | `demo` | Which case the line knows: `demo` (Ana Morales, Los Angeles) or `sf_demo` (Mariam Namuna, San Francisco; the demo video). The officer's intro and case record follow it. Anything else fails at startup |
| `MOCK_AGENCY_HOLD_SECONDS` | no | `45` | Total hold time. Keep it short for the video. |
| `MOCK_AGENCY_HOLD_ANNOUNCE_EVERY_S` | no | `15` | Gap between hold announcements |
| `MOCK_AGENCY_NO_INPUT_SECONDS` | no | `12` | Silence before a reprompt, counted only once the line stops talking |
| `MOCK_AGENCY_OFFICER_NAME` | no | `Daniel Reyes` | |
| `MOCK_AGENCY_IVR_VOICE_ID` | no | Skylar - Friendly Guide (`db6b0ed5-d5d3-463d-ae85-518a07d3c2b4`) | Cartesia voice for the menu and hold announcements |
| `MOCK_AGENCY_OFFICER_VOICE_ID` | no | Jameson - Easygoing Support (`a5136bf9-224c-4d76-b823-52bd5efcffcc`) | A different voice, so the officer picking up sounds like a new person, as on a real line |

## Run locally

```bash
cd mock_agency
uv venv --python 3.12 && source .venv/bin/activate   # separate from the backend venv
uv pip install -e .
ANTHROPIC_API_KEY=... MOCK_AGENCY_OFFICER_MODEL=anthropic/claude-haiku-5-5 \
  MOCK_AGENCY_HOLD_SECONDS=10 python main.py   # add MOCK_AGENCY_MODE=quick to go straight to the officer
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

The menu and the officer use two different voices by default (Environment, above). If `MOCK_AGENCY_IVR_VOICE_ID` or `MOCK_AGENCY_OFFICER_VOICE_ID` was set on Cartesia earlier, it still wins: `cartesia env rm <name>` to use the defaults, then deploy again. The line refuses to start if both are set to the same voice.

Then attach a phone number to the agent in the [Cartesia dashboard](https://play.cartesia.ai). That number is the mock agency's number (`MOCK_AGENCY_NUMBER` in the backend `.env`). Test it by calling it from your own phone.

## Known limits

- No hold music. Line speaks text only, so hold is announcements with silence in between.
- Like a real line, the caller can't talk over recorded prompts, but can interrupt the officer. Menu and hold prompts always play to the end, and speech that ends mid-prompt is dropped (logged as `ignored_speech_during_prompt`). Key presses register mid-prompt and take effect once the prompt finishes. The officer stops talking when interrupted and responds to what was said.
- One case per deploy (`MOCK_AGENCY_CASE`). To offer both, deploy twice, as with the modes.
