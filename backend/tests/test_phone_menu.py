"""Menu decider: the guard, fallbacks, loops, prompt contents, and ask_user → P1.
Fakes only; the real-Claude check is `python -m app.phone.menu_eval`."""

import asyncio
import logging

import pytest
from app.contracts import AskUserRequest
from app.phone.llm import LlmError
from app.phone.menu import (
    ESCAPE_PHRASE,
    AskUserAction,
    MenuDecision,
    MenuTurn,
    PressAction,
    SayAction,
    WaitAction,
    build_user_prompt,
    check_action,
    decide,
    find_repeats,
    press_for_choice,
    to_ask_user_request,
)
from pydantic import BaseModel

BRIEF = {
    "brief_id": "brief_1",
    "case_id": "case_1",
    "call_goal_en": "Confirm the asylum interview is still scheduled",
    "must_not_do": [
        "Never give the A-Number, receipt number, or date of birth",
        "Never discuss the asylum claim",
    ],
    "expected_menu_path": [
        "If offered a language choice, choose English",
        "Choose the option for an existing case",
    ],
    "questions_to_ask": ["Is the interview on November 12 still scheduled?"],
    "facts": [{"field": "a_number", "ref": "<ref:a_number>", "page": 1}],
    "likely_rep_questions": [{"question": "What is your date of birth?"}],
}

MAIN_MENU = (
    "To check a case status, press 1. For an appointment or a pending application, "
    "press 4. For all other questions, press 0."
)


class FakeLlm:
    """Returns a canned action, raises, or hangs; records what it was sent."""

    def __init__(
        self,
        action: object = None,
        *,
        error: Exception | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.action = action
        self.error = error
        self.delay_s = delay_s
        self.calls: list[dict[str, object]] = []

    async def parse[T: BaseModel](
        self, *, system: str, user: str, output_type: type[T], timeout_s: float
    ) -> T:
        self.calls.append({"system": system, "user": user, "timeout_s": timeout_s})
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return output_type.model_validate({"action": self.action})


def press(digits: str = "4", label: str = "appointment", reason: str = "Fits") -> dict:
    return {
        "kind": "press",
        "digits": digits,
        "option_label_en": label,
        "reason_en": reason,
    }


def say(text: str) -> dict:
    return {"kind": "say", "text": text, "reason_en": "Answering the prompt"}


def ask(default: int = 1, digits: tuple[str, str] = ("2", "1")) -> dict:
    return {
        "kind": "ask_user",
        "reason_en": "Both options commit the applicant",
        "question_en": "Keep the interview or reschedule it?",
        "options": [
            {"label_en": "Keep the current interview", "digits": digits[0]},
            {"label_en": "Reschedule the interview", "digits": digits[1]},
        ],
        "default_option": default,
    }


def turn(heard: str, action: object) -> MenuTurn:
    return MenuTurn.model_validate({"heard": heard, "action": action})


# Happy path


async def test_returns_model_action_and_sends_static_system_prompt() -> None:
    llm = FakeLlm(press())

    action = await decide(MAIN_MENU, BRIEF, [], client=llm)

    assert action == PressAction(
        kind="press", digits="4", option_label_en="appointment", reason_en="Fits"
    )
    assert not action.fallback
    assert len(llm.calls) == 1
    assert MAIN_MENU in llm.calls[0]["user"]
    assert "Confirm the asylum interview" not in llm.calls[0]["system"]


async def test_empty_heard_waits_without_calling_the_model() -> None:
    llm = FakeLlm(press())

    action = await decide("   ", BRIEF, [], client=llm)

    assert isinstance(action, WaitAction)
    assert llm.calls == []


# The guard


@pytest.mark.parametrize("digits", ["123", "", "a", "1a", "12#", " 1"])
async def test_press_digits_outside_pattern_are_rejected(digits: str) -> None:
    action = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(press(digits=digits)))

    assert isinstance(action, WaitAction) and action.fallback


@pytest.mark.parametrize("digits", ["0", "9", "*", "#", "12", "*9"])
async def test_press_digits_in_pattern_pass(digits: str) -> None:
    action = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(press(digits=digits)))

    assert isinstance(action, PressAction) and action.digits == digits


@pytest.mark.parametrize(
    "action",
    [
        say("My A-Number is <ref:a_number>"),
        say("The number is 212345678"),
        say("It's 2 1 2 3 4 5 6 7 8"),
        say("Born 1988-03-14"),
        press(reason="Entered ZLA2690012345"),
        press(label="<ref:receipt_number>"),
        {**ask(), "question_en": "Give receipt 2690012345?"},
    ],
)
async def test_text_with_refs_or_digit_runs_is_rejected(action: dict) -> None:
    result = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(action))

    assert isinstance(result, WaitAction) and result.fallback


@pytest.mark.parametrize(
    "text",
    ["Yes, I am the applicant", "This is the applicant", "I'm confirming my interview"],
)
async def test_speaking_as_the_applicant_is_rejected(text: str) -> None:
    result = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(say(text)))

    assert isinstance(result, WaitAction) and result.fallback


async def test_short_numbers_in_text_pass() -> None:
    result = await decide(
        MAIN_MENU,
        BRIEF,
        [],
        client=FakeLlm(say("I'm calling about an interview at 8:30")),
    )

    assert isinstance(result, SayAction)


@pytest.mark.parametrize(
    "bad",
    [
        ask(default=0),
        ask(default=3),
        ask(digits=("2", "x")),
        {**ask(), "options": [{"label_en": "Keep it", "digits": "1"}]},
        {**ask(), "options": [{"label_en": "x" * 61, "digits": "1"}] * 2},
    ],
)
async def test_invalid_ask_user_is_rejected(bad: dict) -> None:
    result = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(bad))

    assert isinstance(result, WaitAction) and result.fallback


def test_guard_names_the_rule_not_the_content() -> None:
    problem = check_action(SayAction(kind="say", text="212345678", reason_en="x"))

    assert problem is not None and "212345678" not in problem


# ask_user → P1


async def test_ask_user_becomes_a_valid_ask_user_request() -> None:
    action = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(ask(default=1)))
    assert isinstance(action, AskUserAction)

    request = to_ask_user_request(action, call_id="call_5", question_id="question_3")

    assert isinstance(request, AskUserRequest)
    assert request.template == "menu_choice"
    assert request.options_en == [
        "Keep the current interview",
        "Reschedule the interview",
    ]
    assert request.default_option == 1
    assert request.timeout_s > 0


def test_reply_choice_is_one_based() -> None:
    action = AskUserAction.model_validate(ask(digits=("2", "1")))

    assert press_for_choice(action, 1).digits == "2"
    assert press_for_choice(action, 2).digits == "1"


# Failures and fallbacks


async def test_timeout_falls_back_to_wait_in_time() -> None:
    llm = FakeLlm(press(), delay_s=5)

    action = await asyncio.wait_for(
        decide(MAIN_MENU, BRIEF, [], client=llm, timeout_s=0.05), timeout=1
    )

    assert isinstance(action, WaitAction) and action.fallback


async def test_api_error_falls_back_to_wait() -> None:
    action = await decide(
        MAIN_MENU, BRIEF, [], client=FakeLlm(error=LlmError("API error"))
    )

    assert isinstance(action, WaitAction) and action.fallback


async def test_second_failure_in_a_row_asks_for_a_person() -> None:
    first = await decide(MAIN_MENU, BRIEF, [], client=FakeLlm(error=LlmError("x")))
    history = [turn("Please enter your receipt number.", first)]

    second = await decide(
        "Please enter your receipt number now.",
        BRIEF,
        history,
        client=FakeLlm(error=LlmError("x")),
    )

    assert isinstance(second, SayAction) and second.fallback
    assert second.text == ESCAPE_PHRASE


async def test_failure_logs_ids_but_no_brief_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="app.phone.menu")

    await decide(
        MAIN_MENU, BRIEF, [], client=FakeLlm(say("212345678")), call_id="call_9"
    )

    assert "call_9" in caplog.text and "case_1" in caplog.text
    assert "212345678" not in caplog.text
    assert "asylum" not in caplog.text.lower()


# Loops

GARBLED_MAIN_MENU = [
    (
        "to check case status press one for an appointment or pending application press four "
        "for all other questions press zero"
    ),
    (
        "Sorry, I didn't get that. To check a case status, press 1. For an appointment or a "
        "pending application, press 4. For all other questions press 0."
    ),
    (
        "check a case status press 1 for an appointment or pending application press for "
        "for all other questions press 0"
    ),
]


def test_garbled_versions_of_one_prompt_count_as_repeats() -> None:
    history = [turn(heard, press()) for heard in GARBLED_MAIN_MENU]

    assert len(find_repeats(MAIN_MENU, history)) == 3


def test_different_prompts_are_not_repeats() -> None:
    history = [
        turn("For English, press 1. Para español, oprima 2.", press("1", "English")),
        turn(
            "Please say or enter your 13-character receipt number.",
            say("I don't have it"),
        ),
    ]

    assert find_repeats(MAIN_MENU, history) == []


async def test_repeats_are_described_to_the_model() -> None:
    llm = FakeLlm(press("0", "all other questions"))
    history = [turn(heard, press()) for heard in GARBLED_MAIN_MENU[:2]]

    await decide(MAIN_MENU, BRIEF, history, client=llm)

    assert (
        "LOOP NOTE: You've heard this prompt 2 time(s) before" in llm.calls[0]["user"]
    )


async def test_loop_ceiling_skips_the_model() -> None:
    llm = FakeLlm(press())
    history = [turn(heard, press()) for heard in GARBLED_MAIN_MENU]

    action = await decide(MAIN_MENU, BRIEF, history, client=llm)

    assert isinstance(action, SayAction) and action.text == ESCAPE_PHRASE
    assert llm.calls == []


# Prompt contents


def test_prompt_has_goal_rules_and_hints_but_no_refs_or_extra_fields() -> None:
    prompt = build_user_prompt(MAIN_MENU, BRIEF, [], [])

    assert "Confirm the asylum interview is still scheduled" in prompt
    assert "Never give the A-Number, receipt number, or date of birth" in prompt
    assert "choose English" in prompt
    assert "<ref:" not in prompt
    assert "November 12" not in prompt  # questions_to_ask stays out
    assert "date of birth?" not in prompt  # likely_rep_questions stay out


def test_prompt_withholds_refs_inside_included_fields() -> None:
    brief = {**BRIEF, "call_goal_en": "Ask about <ref:interview_location>"}

    assert "<ref:" not in build_user_prompt(MAIN_MENU, brief, [], [])


def test_hints_naming_keys_are_dropped() -> None:
    brief = {
        **BRIEF,
        "expected_menu_path": ["Press 2 for English", "Choose existing case"],
    }

    prompt = build_user_prompt(MAIN_MENU, brief, [], [])

    assert "Press 2" not in prompt and "Choose existing case" in prompt


@pytest.mark.parametrize(
    "brief",
    [
        {},
        {"call_goal_en": None, "must_not_do": "oops", "expected_menu_path": [1, None]},
    ],
)
def test_malformed_brief_still_builds_a_prompt(brief: dict) -> None:
    prompt = build_user_prompt(MAIN_MENU, brief, [], [])

    assert "CALL GOAL: Reach a representative" in prompt
    assert MAIN_MENU in prompt


def test_history_in_prompt_is_capped() -> None:
    history = [
        turn(f"Prompt number {chr(97 + i)} here today", press()) for i in range(10)
    ]

    prompt = build_user_prompt(MAIN_MENU, BRIEF, history, [])

    assert "Prompt number a" not in prompt and "Prompt number j" in prompt


def test_model_schema_hides_the_fallback_flag() -> None:
    assert "fallback" not in str(MenuDecision.model_json_schema())
