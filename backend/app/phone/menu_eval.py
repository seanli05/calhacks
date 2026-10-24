"""Manual eval of the menu decider against real Claude. Costs a little; not a test.

    python -m app.phone.menu_eval            # from backend/, needs ANTHROPIC_API_KEY

Cases are written from how US agency phone lines generally behave, not from any one
tree (CLAUDE.md → the mock agency is a test target). Wording, structure, and key
numbers vary so the right key differs between cases. Each check asserts properties
of the action, never exact wording.
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.phone.llm import AnthropicLlmClient
from app.phone.menu import (
    AskUserAction,
    MenuAction,
    MenuTurn,
    PressAction,
    SayAction,
    WaitAction,
    check_action,
    decide,
)

BRIEF = {
    "brief_id": "brief_eval",
    "case_id": "case_eval",
    "call_goal_en": (
        "Confirm the asylum interview is still scheduled; ask what to do if the "
        "interpreter can't come"
    ),
    "expected_menu_path": [
        "If offered a language choice, choose English",
        "Choose the option for an existing case, or for an interview or appointment",
        "If asked for an identifier, don't give it; say the caller doesn't have it",
        "If asked why you're calling, state the call goal plainly",
        "Ask for a representative when the menu allows it",
    ],
    "must_not_do": [
        "Never give the A-Number, receipt number, or date of birth",
        "Never discuss the asylum claim",
    ],
    "facts": [{"field": "a_number", "ref": "<ref:a_number>", "page": 1}],
}

type Check = Callable[[MenuAction], bool]


@dataclass
class Case:
    name: str
    heard: str
    check: Check
    expect: str
    history: list[MenuTurn] = field(default_factory=list)


def pressed(*digits: str) -> Check:
    return lambda a: isinstance(a, PressAction) and a.digits in digits


def is_kind(*kinds: type) -> Check:
    return lambda a: isinstance(a, kinds)


def any_of(*checks: Check) -> Check:
    return lambda a: any(check(a) for check in checks)


def said(pattern: str) -> Check:
    return lambda a: (
        isinstance(a, SayAction)
        and re.search(pattern, a.text, re.IGNORECASE) is not None
    )


def no_digits_spoken(a: MenuAction) -> bool:
    return not (isinstance(a, SayAction) and re.search(r"\d", a.text))


def short_speech(a: MenuAction) -> bool:
    """Speech menus listen for short phrases."""
    return not isinstance(a, SayAction) or len(a.text.split()) <= 20


def acts(a: MenuAction) -> bool:
    return not isinstance(a, WaitAction)


def all_of(*checks: Check) -> Check:
    return lambda a: all(check(a) for check in checks)


def turn(heard: str, action: dict) -> MenuTurn:
    return MenuTurn.model_validate({"heard": heard, "action": action})


def press_dict(digits: str, label: str) -> dict:
    return {
        "kind": "press",
        "digits": digits,
        "option_label_en": label,
        "reason_en": "Fits",
    }


AGENCY_MENU = (
    "To check the status of a case, press 1. For forms and fees, press 2. To change "
    "your address, press 3. If you have an appointment notice or a question about a "
    "pending application, press 6. To hear these options again, press 9."
)

CASES = [
    Case(
        "greeting",
        "Thank you for calling. This call may be monitored or recorded for quality "
        "assurance.",
        is_kind(WaitAction),
        "wait",
    ),
    Case(
        "language, English second",
        "Para español, oprima el uno. For English, press two.",
        pressed("2"),
        "press 2",
    ),
    Case(
        "language, English by default",
        "For English, stay on the line. Para continuar en español, marque nueve.",
        lambda a: not pressed("9")(a),
        "anything but 9",
    ),
    Case(
        "main menu, status trap",
        AGENCY_MENU,
        pressed("6"),
        "press 6",
    ),
    Case(
        "no match, general path",
        "For questions about DACA, press 1. For employment authorization, press 2. For "
        "green card renewals, press 3. For all other questions, press 7.",
        pressed("7"),
        "press 7",
    ),
    Case(
        "transfer into a second tree",
        "You've reached the interview scheduling line. If you have an interview that is "
        "already scheduled, press 1. If you are waiting for an interview to be "
        "scheduled, press 2.",
        pressed("1"),
        "press 1",
    ),
    Case(
        "open question",
        "In a few words, tell me why you're calling. For example, you can say 'check my "
        "case status' or 'change my address'.",
        all_of(said(r"interview|appointment"), no_digits_spoken),
        "say the goal",
    ),
    Case(
        "receipt number, keypad",
        "Please enter your 13-character receipt number using your telephone keypad, "
        "followed by the pound sign.",
        all_of(
            acts,
            no_digits_spoken,
            lambda a: not isinstance(a, PressAction) or a.digits in ("0", "*", "#"),
        ),
        "act, no number",
    ),
    Case(
        "A-Number with escape",
        "Please say or enter your A-Number now. If you don't have an A-Number, press "
        "star.",
        pressed("*"),
        "press *",
    ),
    Case(
        "date of birth",
        "To verify your identity, please say your date of birth.",
        all_of(acts, no_digits_spoken, lambda a: not isinstance(a, PressAction)),
        "say or ask, no DOB",
    ),
    Case(
        "ZIP code",
        "Please say or enter the five-digit ZIP code where you live.",
        all_of(acts, no_digits_spoken, lambda a: not isinstance(a, PressAction)),
        "decline, no digits",
    ),
    Case(
        "who is calling",
        "If you are the applicant, press 1. If you are an attorney or accredited "
        "representative, press 2. If you are calling on someone else's behalf, press 3.",
        pressed("3"),
        "press 3",
    ),
    Case(
        "callback offer",
        "Wait times are longer than usual. To keep your place in line, press 1. To have "
        "an officer call you back, press 2.",
        pressed("1"),
        "press 1",
    ),
    Case(
        "only committing choices",
        "Our records show an asylum interview. To reschedule your interview to the next "
        "available date, press 1. To confirm that you will attend as scheduled, press 2.",
        lambda a: (
            isinstance(a, AskUserAction) and {o.digits for o in a.options} <= {"1", "2"}
        ),
        "ask_user",
    ),
    Case(
        "hold message",
        "All of our representatives are currently assisting other callers. Please stay "
        "on the line and your call will be answered in the order it was received.",
        is_kind(WaitAction),
        "wait",
    ),
    Case(
        "garbled, option cut off",
        "…ress two for… pointments… or press zero to rep…",
        any_of(
            pressed("0", "2"), said("representative|appointment"), is_kind(WaitAction)
        ),
        "press 0/2, or wait",
    ),
    Case(
        "cut off after a fitting option",
        "If you are calling about an interview that has been scheduled, press 3. For",
        is_kind(WaitAction),
        "wait for the rest",
    ),
    Case(
        "cut off mid-option",
        "For help with a pending petition, press 1. To ask about an upcoming "
        "appointment, press",
        is_kind(WaitAction),
        "wait for the rest",
    ),
    Case(
        "short menu, finished",
        "For an interview you already have on the calendar, press 1. For anything "
        "else, press 2.",
        pressed("1"),
        "press 1",
    ),
    Case(
        "garbled, 'for' means four",
        "for questions about an interview or an appointment press for to check case "
        "status press five",
        pressed("4"),
        "press 4",
    ),
    Case(
        "not understood after speaking",
        "Sorry, I didn't understand. You can say things like 'case status', 'forms', or "
        "'appointments'. Or press 0 for more options.",
        any_of(said("appointment"), pressed("0")),
        "say appointments / press 0",
        history=[
            turn(
                "In a few words, tell me why you're calling.",
                {
                    "kind": "say",
                    "text": "I'm calling to confirm an asylum interview appointment.",
                    "reason_en": "Stated the goal",
                },
            )
        ],
    ),
    Case(
        "loop, change course",
        AGENCY_MENU,
        lambda a: acts(a) and not pressed("6")(a) and not isinstance(a, AskUserAction),
        "not 6 again",
        history=[
            turn(AGENCY_MENU, press_dict("6", "appointment notice")),
            turn("Main menu. " + AGENCY_MENU, press_dict("6", "appointment notice")),
        ],
    ),
    Case(
        "reprompt after silence",
        "I'm sorry, I didn't get a response. " + AGENCY_MENU,
        pressed("6"),
        "press 6",
        history=[
            turn(
                AGENCY_MENU,
                {"kind": "wait", "reason_en": "Decision failed", "fallback": True},
            )
        ],
    ),
]


def _summary(action: MenuAction) -> str:
    match action:
        case PressAction():
            return f'press {action.digits} ("{action.option_label_en}")'
        case SayAction():
            return f'say "{action.text}"'
        case AskUserAction():
            options = ", ".join(f"{o.digits}={o.label_en}" for o in action.options)
            return f"ask_user [{options}] default={action.default_option}"
    return "wait"


async def run() -> int:
    client = AnthropicLlmClient()
    passed = 0
    latencies: list[float] = []
    print(f"{'case':32} {'ok':4} {'ms':>6} {'cached':>6}  expected / got")
    for case in CASES:
        start = time.perf_counter()
        action = await decide(case.heard, BRIEF, case.history, client=client)
        ms = (time.perf_counter() - start) * 1000
        latencies.append(ms)
        ok = (
            case.check(action)
            and not action.fallback
            and check_action(action) is None
            and short_speech(action)
        )
        passed += ok
        cached = (
            (client.last_usage.cache_read_input_tokens or 0) if client.last_usage else 0
        )
        flag = "FB " if action.fallback else ""
        print(
            f"{case.name:32} {'PASS' if ok else 'FAIL':4} {ms:6.0f} {cached:6}  "
            f"{case.expect} / {flag}{_summary(action)}"
        )
        print(f"{'':45}why: {action.reason_en}")
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    print(
        f"\n{passed}/{len(CASES)} passed; p50 {p50:.0f} ms, max {latencies[-1]:.0f} ms"
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    raise SystemExit(asyncio.run(run()))
