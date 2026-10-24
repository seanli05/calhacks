"""Line-phase classifier: is the line playing a menu, hold, or a live person?
(Plan.md → Phone agent: hold vs. human detection.)

Perception only. `classify` turns one finished utterance into a `PhaseReading`;
`to_trigger` maps the reading to a 1a trigger the runner fires, or None. Deciding
what to do at a menu is 1b's job (`menu.py`), and logging is the runner's: the
reading's fields go in the `data` of the event its trigger logs.

A cascade, cheapest first:

1. a near-verbatim repeat of an earlier menu or hold utterance reuses that phase
   with no model call (recordings repeat; people don't);
2. anything new goes to Claude with code-computed cues as hints;
3. if Claude fails or is too slow, the cues alone give a fallback reading. It calls
   a person only on strong combined cues, so an API outage on hold can't lose the
   call, and a recording can't ring the applicant through it.

The cues are general conversational structure (a self-introduction, a question to
the caller, a voice that says it's automated, keypad options), not phrase lists
from any one line. They are hints, and wrong sometimes; the thresholds in
`to_trigger` decide what fires. Utterance text never reaches the logs.

Known gaps, to tune once the 1e simulator can replay calls (not by tuning to the
eval's own cases):

- A rep's "let me transfer you, please hold" swings between `hold` (0.75-0.8) and
  `human` (0.6) across eval runs, so FALSE_HUMAN fires only sometimes. The prompt
  says it's `hold`; the model sometimes goes by who is speaking.
- `reason_en` sometimes names the rep despite the prompt. Agency staff, not user
  data, but `_scrub` only drops quotes and number runs.
- `CLASSIFY_TIMEOUT_S` and the `RULES` thresholds come from three eval runs.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts import CallId, CallState
from app.phone.llm import AnthropicLlmClient, LlmClient, LlmError
from app.phone.phase_prompts import PHASE_SYSTEM
from app.phone.state import Trigger

logger = logging.getLogger(__name__)

CLASSIFY_TIMEOUT_S = 3.0
"""On the path from a human answering to the applicant's phone ringing (< 5 s):
typical readings take 0.9-1.5 s and fit. A reading that runs to the limit, plus
0.5 s of speech-to-text and 2-3 s of dialing, can miss it; at 2.5 s, about 1 in 7
eval calls hit the limit and fell back, which costs more than a slow ring."""

LISTENING_STATES = frozenset({CallState.MENU, CallState.HOLD, CallState.HUMAN_DETECTED})
"""States where the line's phase can change the call state. Elsewhere the
applicant is joining or on the call, and `classify` makes no model call."""

HISTORY_IN_PROMPT = 6
REPEAT_SIMILARITY = 0.75
"""Speech-to-text never transcribes the same recording twice the same way."""
REPEAT_MIN_WORDS = 4
REPEAT_MIN_AGE_S = 20.0
"""A person says "Hello? ... Hello?" seconds apart; a recording loops after longer."""
REPEAT_CONFIDENCE = 0.9

_HEARD_CHARS = 1000
_HISTORY_HEARD_CHARS = 300
_REASON_CHARS = 200

_NUMBER_WORD = (
    r"(?:\d|zero|one|two|three|four|five|six|seven|eight|nine|star|pound|hash"
    r"|for|to|too|won)"
)
_OPTIONS = re.compile(
    rf"\b(?:press|oprima|marque|dial|push)\s+(?:the\s+)?(?:number\s+)?{_NUMBER_WORD}\b"
    r"|\byou\s+can\s+say\b|\bsay\s+(?:yes|no)\b",
    re.IGNORECASE,
)
"""Keypad or spoken options, a menu's shape. "for"/"to" are speech-to-text's digits."""
_AUTOMATED = re.compile(
    r"\b(?:virtual|automated|digital|electronic)\s+"
    r"(?:assistant|agent|attendant|system|representative)\b"
    r"|\b(?:this|that)\s+(?:is|was)\s+a\s+recording\b",
    re.IGNORECASE,
)
_INTRO = re.compile(
    r"\bmy\s+name(?:'s|\s+is)\s+[a-z]+"
    r"|\b(?:this\s+is|you'?ve\s+reached|you'?re\s+(?:speaking|talking)\s+(?:with|to))\s+"
    r"(?:(?:mr|mrs|ms|miss|dr|officer|agent)\.?\s+)?"
    r"(?!(?:the|a|an|our|your|not|it|to|for|being|now)\b)[a-z]+(?:\s+[a-z]+)?[,.]?\s+"
    r"(?:speaking|with|from|at|here|how|what|who|can|may|thanks|thank)\b",
    re.IGNORECASE,
)
"""A person naming themself: "my name is X", "this is X, how can I help"."""
_ASKS_FRAME = re.compile(
    r"\b(?:how|what|who)\s+(?:can|may|do|did|is|are|am)\b"
    r"|\b(?:may|can|could)\s+i\s+(?:have|get|ask|help|please)\b"
    r"|\bare\s+you\s+(?:there|calling|still)\b|\bcan\s+you\s+hear\b",
    re.IGNORECASE,
)
_ASKS_MARKED = re.compile(r"\b(?:you|your|hello|anyone|anybody)\b", re.IGNORECASE)
_HOLD = re.compile(
    r"\bplease\s+(?:hold|wait|continue\s+to\s+hold)\b"
    r"|\b(?:stay|remain)\s+on\s+the\s+line\b|\bnext\s+available\b"
    r"|\b(?:estimated\s+)?(?:wait|hold)\s+time\b|\bin\s+the\s+order\b"
    r"|\btransfer(?:ring)?\s+(?:you|your\s+call)\b"
    r"|\b(?:representatives|agents|officers)\b.{0,40}\b(?:busy|assisting|helping)\b",
    re.IGNORECASE,
)
"""Queue language, used only when Claude is unavailable."""
_DIGIT_RUN = re.compile(r"\d(?:[\s./-]*\d){3,}")


class Phase(StrEnum):
    MENU = "menu"
    HOLD = "hold"
    HUMAN = "human"
    UNCLEAR = "unclear"


class ReadingSource(StrEnum):
    MODEL = "model"
    REPEAT = "repeat"
    """Reused the phase of an earlier, matching utterance."""
    FALLBACK = "fallback"
    """Claude failed or timed out; cues alone."""
    SKIPPED = "skipped"
    """Nothing to classify: empty text, or a state that doesn't listen."""


class PhaseReading(BaseModel):
    """What the line is doing now. `reason_en` names cues, never transcript text."""

    model_config = ConfigDict(frozen=True)

    phase: Phase
    confidence: float = Field(ge=0.0, le=1.0)
    reason_en: str
    source: ReadingSource


class HeardTurn(BaseModel):
    """One earlier utterance and the phase it was read as, kept by the runner."""

    model_config = ConfigDict(frozen=True)

    text: str
    at_s: float
    """Seconds since the call started, when the speech began."""
    phase: Phase


# The model's output. No numeric bounds: structured outputs don't enforce them, so
# code clamps `confidence` instead.
class PhaseJudgment(BaseModel):
    phase: Literal["menu", "hold", "human", "unclear"]
    confidence: float = Field(description="0 to 1, calibrated as the rules say.")
    reason_en: str = Field(description="At most 12 words naming the cues.")


@dataclass(frozen=True)
class Cues:
    """Deterministic signals about one utterance, computed before any model call."""

    repeat_of: HeardTurn | None
    closest_earlier: float
    """Highest similarity to any earlier utterance, 0 to 1."""
    seconds_since_previous: float | None
    introduces_self: bool
    asks_caller: bool
    says_automated: bool
    offers_options: bool
    hold_language: bool


@dataclass(frozen=True)
class Rule:
    trigger: Trigger
    min_confidence: float


RULES: dict[tuple[CallState, Phase], Rule] = {
    (CallState.MENU, Phase.HOLD): Rule(Trigger.HOLD_STARTED, 0.6),
    # Stricter than from hold: virtual assistants with names live in menus.
    (CallState.MENU, Phase.HUMAN): Rule(Trigger.HUMAN_DETECTED, 0.8),
    (CallState.HOLD, Phase.HUMAN): Rule(Trigger.HUMAN_DETECTED, 0.7),
    (CallState.HOLD, Phase.MENU): Rule(Trigger.MENU_RETURNED, 0.6),
    # Strictest: a wrong one walks away from a live person. Claude reads a rep's
    # "let me transfer you, please hold" at about 0.75-0.8.
    (CallState.HUMAN_DETECTED, Phase.HOLD): Rule(Trigger.FALSE_HUMAN, 0.75),
}
"""Asymmetric on purpose: each threshold follows what a wrong move costs."""


def to_trigger(state: CallState, reading: PhaseReading) -> Trigger | None:
    """The 1a trigger this reading fires in this state, or None to stay put.
    Only ever returns triggers `state.TRANSITIONS` allows from `state`."""
    rule = RULES.get((state, reading.phase))
    if rule is None or reading.confidence < rule.min_confidence:
        return None
    return rule.trigger


async def classify(
    text: str,
    *,
    at_s: float,
    state: CallState,
    history: list[HeardTurn],
    state_since_s: float | None = None,
    client: LlmClient | None = None,
    timeout_s: float = CLASSIFY_TIMEOUT_S,
    call_id: CallId | None = None,
) -> PhaseReading:
    """Read one finished utterance. Never raises for a model failure; falls back to
    the cues instead."""
    if state not in LISTENING_STATES:
        return _skipped(f"Not listening in state {state}")
    if not text.strip():
        return _skipped("Nothing was heard")

    cues = read_cues(text, at_s, history)
    if cues.repeat_of is not None:
        return PhaseReading(
            phase=cues.repeat_of.phase,
            confidence=REPEAT_CONFIDENCE,
            reason_en=f"Repeats an earlier {cues.repeat_of.phase} message word for word",
            source=ReadingSource.REPEAT,
        )

    seconds_in_state = None if state_since_s is None else at_s - state_since_s
    user = build_user_prompt(text, state, seconds_in_state, history, cues, at_s)
    llm = client or _default_client()
    try:
        async with asyncio.timeout(timeout_s):
            judgment = await llm.parse(
                system=PHASE_SYSTEM,
                user=user,
                output_type=PhaseJudgment,
                timeout_s=timeout_s,
            )
    except (LlmError, TimeoutError) as exc:
        logger.warning(
            "phase reading failed (call_id=%s state=%s): %s; using cues",
            call_id,
            state,
            str(exc) or type(exc).__name__,
        )
        return fallback_reading(cues)

    return PhaseReading(
        phase=Phase(judgment.phase),
        confidence=min(max(judgment.confidence, 0.0), 1.0),
        reason_en=_scrub(judgment.reason_en) or "No reason given",
        source=ReadingSource.MODEL,
    )


def read_cues(text: str, at_s: float, history: list[HeardTurn]) -> Cues:
    current = _normalize(text)
    similarities = [
        (
            SequenceMatcher(
                None, current, _normalize(turn.text), autojunk=False
            ).ratio(),
            turn,
        )
        for turn in history
    ]
    repeat_of = next(
        (
            turn
            for ratio, turn in reversed(similarities)
            if ratio >= REPEAT_SIMILARITY
            and turn.phase in (Phase.MENU, Phase.HOLD)
            and at_s - turn.at_s >= REPEAT_MIN_AGE_S
            and len(current.split()) >= REPEAT_MIN_WORDS
        ),
        None,
    )
    return Cues(
        repeat_of=repeat_of,
        closest_earlier=max((ratio for ratio, _ in similarities), default=0.0),
        seconds_since_previous=at_s - history[-1].at_s if history else None,
        introduces_self=_INTRO.search(text) is not None,
        asks_caller=_ASKS_FRAME.search(text) is not None
        or ("?" in text and _ASKS_MARKED.search(text) is not None),
        says_automated=_AUTOMATED.search(text) is not None,
        offers_options=_OPTIONS.search(text) is not None,
        hold_language=_HOLD.search(text) is not None,
    )


def fallback_reading(cues: Cues) -> PhaseReading:
    """The cues alone, for when Claude is unavailable. Conservative: a person only
    on a self-introduction plus a question to the caller from a voice that doesn't
    say it's automated; otherwise it leans on structure or abstains."""

    def reading(phase: Phase, confidence: float, reason: str) -> PhaseReading:
        return PhaseReading(
            phase=phase,
            confidence=confidence,
            reason_en=reason,
            source=ReadingSource.FALLBACK,
        )

    if cues.says_automated or cues.offers_options:
        return reading(Phase.MENU, 0.65, "Automated voice or menu options (cues only)")
    if cues.introduces_self and cues.asks_caller:
        return reading(
            Phase.HUMAN,
            0.8,
            "New speaker introduces themself and asks the caller (cues only)",
        )
    if cues.hold_language and not cues.asks_caller:
        return reading(Phase.HOLD, 0.65, "Queue language (cues only)")
    return reading(Phase.UNCLEAR, 0.3, "No decisive cue and the model was unavailable")


def build_user_prompt(
    text: str,
    state: CallState,
    seconds_in_state: float | None,
    history: list[HeardTurn],
    cues: Cues,
    at_s: float,
) -> str:
    in_state = (
        "" if seconds_in_state is None else f" (for {_duration(seconds_in_state)})"
    )
    lines = [f"CALL STATE: {state}{in_state}"]

    recent = history[-HISTORY_IN_PROMPT:]
    if recent:
        lines += ["", "RECENT LINE SPEECH (oldest first):"]
        lines += [
            f"{i}. {_duration(at_s - turn.at_s)} ago, read as {turn.phase}: "
            f'"{_clip(turn.text, _HISTORY_HEARD_CHARS)}"'
            for i, turn in enumerate(recent, 1)
        ]

    gap = cues.seconds_since_previous
    lines += [
        "",
        "CUES (computed by code; hints that can be wrong):",
        f"- similarity to the closest earlier utterance: {cues.closest_earlier:.0%}",
        f"- since the previous utterance: {'first utterance' if gap is None else _duration(gap)}",
        f"- introduces a person by name: {_yes(cues.introduces_self)}",
        f"- asks the caller a question: {_yes(cues.asks_caller)}",
        f"- says it is automated or a recording: {_yes(cues.says_automated)}",
        f"- lists keypad or spoken options: {_yes(cues.offers_options)}",
        "",
        "NOW HEARD (speech-to-text; may be garbled or cut off):",
        f'"{_clip(text, _HEARD_CHARS)}"',
    ]
    return "\n".join(lines)


def _skipped(reason: str) -> PhaseReading:
    return PhaseReading(
        phase=Phase.UNCLEAR,
        confidence=0.0,
        reason_en=reason,
        source=ReadingSource.SKIPPED,
    )


@cache
def _default_client() -> AnthropicLlmClient:
    return AnthropicLlmClient()


def _scrub(reason: str) -> str:
    """The log line names cues; drop quotes and number runs in case the model echoes."""
    reason = _DIGIT_RUN.sub("[number]", reason.replace('"', ""))
    return _clip(reason, _REASON_CHARS)


def _duration(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    return f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.0f} min"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())
