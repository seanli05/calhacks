"""Menu decider: what to do when an automated phone menu speaks (Plan.md → Phone agent).

One Claude call per menu utterance returns a `MenuAction`. The decider only decides;
the runner logs it and the executor speaks or keys it (C37). Code, not the model,
owns three things:

- the guard: every model action is checked here before it leaves, and a failing one
  is replaced, never repaired (rule 3, C35);
- fallbacks: on any failure the answer is `wait` (menus reprompt), and a second
  failure in a row says "representative" so silence can't end the call;
- loops: code spots a repeated prompt and tells the model; past the ceiling it stops
  asking the model. Aborting the call is the runner's job (`Trigger.AGENT_ABORTED`).

The brief is read defensively (`CaseBrief` is still a dict) and only the goal, the
must-not-do list, and the menu hints reach the prompt. Refs are never resolved here.
"""

import asyncio
import logging
import re
from difflib import SequenceMatcher
from functools import cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.json_schema import SkipJsonSchema

from app.contracts import AskUserRequest, CallId, QuestionId
from app.phone.llm import AnthropicLlmClient, LlmClient, LlmError
from app.phone.menu_prompts import MENU_SYSTEM

logger = logging.getLogger(__name__)

DECIDE_TIMEOUT_S = 8.0
"""A ceiling; decisions usually take 1-1.5 s. Menus often reprompt within 5-7 s, so
a slow answer can land after the line moved on: the runner should drop a decision
once a newer utterance has arrived."""
ASK_USER_TIMEOUT_S = 45
"""P1's example value. Menus reprompt long before this; the runner decides again then."""
ASK_USER_TEMPLATE = "menu_choice"

HISTORY_IN_PROMPT = 6
LOOP_CEILING = 3
"""Earlier hearings of the same prompt after which code stops asking the model."""
REPEAT_SIMILARITY = 0.75
"""Speech-to-text never transcribes the same recording twice the same way."""
ESCAPE_PHRASE = "representative"
"""Widely accepted by speech menus, carries no data. Does nothing on keypad-only
menus; the runner's menu cap covers those."""

_HEARD_CHARS = 1000
_HISTORY_HEARD_CHARS = 300
_SAY_MAX_CHARS = 200
_LABEL_MAX_CHARS = 60
_DEFAULT_GOAL = "Reach a representative about the applicant's case"

_DIGITS = re.compile(r"^[0-9*#]{1,2}$")
_DIGIT_RUN = re.compile(r"\d(?:[\s./-]*\d){5,}")
"""Six or more digits, even split by spaces or dashes: an identifier or a date."""
_CLAIMS_APPLICANT = re.compile(
    r"\b(?:i\s+am|i'm|this\s+is)\s+(?:the\s+)?(?:applicant|beneficiary|petitioner)\b"
    r"|\bmy\s+(?:asylum\s+)?(?:interview|case|application|appointment|receipt|a-number)\b",
    re.IGNORECASE,
)
"""First person as the applicant (rule 3), including "my interview"."""
_REF = re.compile(r"<ref:[^>]*>")
_KEY_NUMBER = re.compile(
    r"\b(?:press|dial|push|oprima|marque)\s+(?:\d|zero|one|two|three|four|five|six"
    r"|seven|eight|nine|star|pound)\b",
    re.IGNORECASE,
)


def _kind(value: str) -> Any:
    """The SDK's schema transform drops `const`, so pin each kind with an enum the
    API enforces; otherwise the model could mix fields from two actions."""
    return Field(json_schema_extra={"enum": [value]})


class _Action(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason_en: str = Field(description="One short sentence for the call log.")
    fallback: SkipJsonSchema[bool] = False
    """Set by code when the model's answer was unusable. Hidden from the model."""


class PressAction(_Action):
    """Choose an option. The executor speaks the digit or label, or keys it (C37)."""

    kind: Literal["press"] = _kind("press")
    digits: str = Field(description='The key for the option, e.g. "2", "0", "*".')
    option_label_en: str = Field(description="The option's name as heard.")


class SayAction(_Action):
    kind: Literal["say"] = _kind("say")
    text: str = Field(description="A short sentence to speak, under 20 words.")


class WaitAction(_Action):
    kind: Literal["wait"] = _kind("wait")


class AskUserOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    label_en: str = Field(description="The choice in under 8 words.")
    digits: str = Field(description="The key for this choice.")


class AskUserAction(_Action):
    kind: Literal["ask_user"] = _kind("ask_user")
    question_en: str
    """For the log and dashboard. The relay's template supplies the user's wording."""
    options: list[AskUserOption] = Field(description="2-4 choices.")
    default_option: int = Field(
        description="1-based index of the safest option, used if the user doesn't answer."
    )


MenuAction = Annotated[
    PressAction | SayAction | WaitAction | AskUserAction, Field(discriminator="kind")
]


# The model's output; structured outputs need an object at the top.
class MenuDecision(BaseModel):
    action: MenuAction


class MenuTurn(BaseModel):
    """One earlier menu step, kept by the runner and passed back in."""

    model_config = ConfigDict(frozen=True)

    heard: str
    action: MenuAction


async def decide(
    heard: str,
    brief: dict[str, Any],
    history: list[MenuTurn],
    *,
    client: LlmClient | None = None,
    timeout_s: float = DECIDE_TIMEOUT_S,
    call_id: CallId | None = None,
) -> MenuAction:
    """Pick the next action for what the menu just said. Never raises for a model
    failure; returns a safe action instead."""
    context = _log_context(brief, call_id)
    if not heard.strip():
        return WaitAction(kind="wait", reason_en="Nothing was heard")

    repeats = find_repeats(heard, history)
    if len(repeats) >= LOOP_CEILING:
        logger.warning(
            "menu loop ceiling (%s): heard %d times", context, len(repeats) + 1
        )
        return SayAction(
            kind="say",
            text=ESCAPE_PHRASE,
            reason_en=f"Same prompt heard {len(repeats) + 1} times; asking for a person",
        )

    user = build_user_prompt(heard, brief, history, repeats)
    llm = client or _default_client()
    try:
        async with asyncio.timeout(timeout_s):
            decision = await llm.parse(
                system=MENU_SYSTEM,
                user=user,
                output_type=MenuDecision,
                timeout_s=timeout_s,
            )
    except (LlmError, TimeoutError) as exc:
        logger.warning(
            "menu decision failed (%s): %s", context, str(exc) or type(exc).__name__
        )
        return _fallback(history, "Menu decision failed")

    problem = check_action(decision.action)
    if problem is not None:
        logger.warning(
            "menu action rejected (%s): %s, %s", context, decision.action.kind, problem
        )
        return _fallback(history, "Menu decision failed the safety check")
    return decision.action


def check_action(action: MenuAction) -> str | None:
    """The deterministic guard. Returns what's wrong (a rule name, never the
    content), or None if the action may go out."""
    for text in _texts(action):
        if "<ref:" in text:
            return "contains a ref placeholder"
        if _DIGIT_RUN.search(text):
            return "contains a run of 6+ digits"
    for text in _spoken(action):
        if _CLAIMS_APPLICANT.search(text):
            return "claims to be the applicant"
    match action:
        case PressAction():
            if not _DIGITS.match(action.digits):
                return "press digits out of pattern"
            if not action.option_label_en.strip():
                return "press without a label"
        case SayAction():
            if not action.text.strip():
                return "empty say"
            if len(action.text) > _SAY_MAX_CHARS:
                return "say too long"
        case AskUserAction():
            if not 2 <= len(action.options) <= 4:
                return "ask_user needs 2-4 options"
            if any(not _DIGITS.match(option.digits) for option in action.options):
                return "ask_user option digits out of pattern"
            if any(
                not option.label_en.strip() or len(option.label_en) > _LABEL_MAX_CHARS
                for option in action.options
            ):
                return "ask_user label empty or too long"
            try:
                to_ask_user_request(
                    action, call_id="call_check", question_id="question_check"
                )
            except ValidationError:
                return "ask_user doesn't make a valid AskUserRequest"
    return None


def to_ask_user_request(
    action: AskUserAction,
    *,
    call_id: CallId,
    question_id: QuestionId,
    timeout_s: int = ASK_USER_TIMEOUT_S,
) -> AskUserRequest:
    """P1 for the relay. Options stay 1-based (C5)."""
    return AskUserRequest(
        question_id=question_id,
        call_id=call_id,
        template=ASK_USER_TEMPLATE,
        options_en=[option.label_en for option in action.options],
        default_option=action.default_option,
        timeout_s=timeout_s,
    )


def press_for_choice(action: AskUserAction, choice: int) -> PressAction:
    """Turn the user's 1-based reply (or the default on timeout) into the press."""
    option = action.options[choice - 1]
    return PressAction(
        kind="press",
        digits=option.digits,
        option_label_en=option.label_en,
        reason_en=f"The applicant chose option {choice}",
    )


def find_repeats(heard: str, history: list[MenuTurn]) -> list[MenuTurn]:
    """Earlier turns that heard the same prompt, by fuzzy match."""
    current = _normalize(heard)
    if len(current.split()) < 4:
        return []
    return [
        turn
        for turn in history
        if SequenceMatcher(
            None, current, _normalize(turn.heard), autojunk=False
        ).ratio()
        >= REPEAT_SIMILARITY
    ]


def build_user_prompt(
    heard: str,
    brief: dict[str, Any],
    history: list[MenuTurn],
    repeats: list[MenuTurn],
) -> str:
    goal = brief.get("call_goal_en")
    goal = _clean(goal) if isinstance(goal, str) and goal.strip() else _DEFAULT_GOAL
    must_not = _text_list(brief.get("must_not_do"))
    all_hints = _text_list(brief.get("expected_menu_path"))
    hints = [hint for hint in all_hints if not _KEY_NUMBER.search(hint)]
    if len(hints) < len(all_hints):
        # Real menus renumber; a hint that names keys came from one tree.
        logger.warning(
            "dropped %d menu hints that name keys", len(all_hints) - len(hints)
        )

    lines = [f"CALL GOAL: {goal}", "", "MUST NOT DO:"]
    lines += [f"- {item}" for item in must_not] or ["- (none listed)"]
    lines += [
        "",
        "MENU HINTS (by meaning; real menus vary, so never assume a key number):",
    ]
    lines += [f"- {hint}" for hint in hints] or ["- (none)"]

    recent = history[-HISTORY_IN_PROMPT:]
    if recent:
        lines += ["", "YOUR RECENT TURNS (oldest first):"]
        lines += [
            f'{i}. heard "{_clip(turn.heard, _HISTORY_HEARD_CHARS)}" -> {_describe(turn.action)}'
            for i, turn in enumerate(recent, 1)
        ]
    if repeats:
        chosen = "; ".join(_describe(turn.action) for turn in repeats)
        lines += [
            "",
            (
                f"LOOP NOTE: You've heard this prompt {len(repeats)} time(s) before. "
                f"You chose: {chosen}. It came back each time. Change course, unless the "
                "line just said it didn't understand you."
            ),
        ]
    lines += [
        "",
        "NOW HEARD (speech-to-text; may be garbled or cut off):",
        f'"{_clip(heard, _HEARD_CHARS)}"',
    ]
    return "\n".join(lines)


def _fallback(history: list[MenuTurn], why: str) -> MenuAction:
    if history and history[-1].action.fallback:
        return SayAction(
            kind="say",
            text=ESCAPE_PHRASE,
            reason_en=f"{why} twice in a row; asking for a person",
            fallback=True,
        )
    return WaitAction(
        kind="wait", reason_en=f"{why}; waiting for the menu to repeat", fallback=True
    )


@cache
def _default_client() -> AnthropicLlmClient:
    return AnthropicLlmClient()


def _texts(action: MenuAction) -> list[str]:
    texts = [action.reason_en, *_spoken(action)]
    if isinstance(action, AskUserAction):
        texts.append(action.question_en)
    return texts


def _spoken(action: MenuAction) -> list[str]:
    """Text the executor may speak on the line, or the relay may send."""
    match action:
        case PressAction():
            return [action.option_label_en]
        case SayAction():
            return [action.text]
        case AskUserAction():
            return [option.label_en for option in action.options]
    return []


def _describe(action: MenuAction) -> str:
    match action:
        case PressAction():
            return f'press {action.digits} ("{action.option_label_en}")'
        case SayAction():
            return f'said "{action.text}"'
        case AskUserAction():
            return f'asked the applicant: "{action.question_en}"'
    return "waited"


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value if isinstance(item, str) and item.strip()]


def _clean(text: str) -> str:
    """Brief text with any ref placeholder withheld, so the model can't echo one."""
    return _REF.sub("[withheld]", text.strip())


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def _log_context(brief: dict[str, Any], call_id: CallId | None) -> str:
    """IDs only; brief values never reach the logs."""
    case_id = brief.get("case_id") if isinstance(brief.get("case_id"), str) else None
    brief_id = brief.get("brief_id") if isinstance(brief.get("brief_id"), str) else None
    return f"call_id={call_id} case_id={case_id} brief_id={brief_id}"
