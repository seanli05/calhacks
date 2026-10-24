"""Line-phase classifier: the trigger mapping, the repeat short-circuit, and the
fallback when Claude fails. Fakes only; the real-Claude check is
`python -m app.phone.phase_eval`."""

import asyncio
import logging

import pytest
from app.contracts import CallState
from app.phone.llm import LlmError
from app.phone.phase import (
    LISTENING_STATES,
    HeardTurn,
    Phase,
    PhaseReading,
    ReadingSource,
    build_user_prompt,
    classify,
    fallback_reading,
    read_cues,
    to_trigger,
)
from app.phone.phase_eval import CASES, HOLD_IMPORTANT, HOLD_LOOP
from app.phone.state import TRANSITIONS, Trigger
from pydantic import BaseModel

REP_GREETING = (
    "Thank you for holding, my name is Daniel. Can I get the name of the person I'm "
    "speaking with?"
)


class FakeLlm:
    """Returns a canned judgment, raises, or hangs; records what it was sent."""

    def __init__(
        self,
        judgment: dict | None = None,
        *,
        error: Exception | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.judgment = judgment or {
            "phase": "hold",
            "confidence": 0.9,
            "reason_en": "Hold message",
        }
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
        return output_type.model_validate(self.judgment)


def reading(phase: Phase, confidence: float = 1.0) -> PhaseReading:
    return PhaseReading(
        phase=phase, confidence=confidence, reason_en="test", source=ReadingSource.MODEL
    )


async def classify_with(
    llm: FakeLlm,
    text: str,
    *,
    state: CallState = CallState.HOLD,
    history: list[HeardTurn] | None = None,
    at_s: float = 600.0,
    **kwargs: object,
) -> PhaseReading:
    return await classify(
        text,
        at_s=at_s,
        state=state,
        history=HOLD_LOOP if history is None else history,
        client=llm,
        **kwargs,
    )


# --- the trigger mapping ---


@pytest.mark.parametrize("state", list(CallState))
@pytest.mark.parametrize("phase", list(Phase))
def test_mapping_only_returns_legal_triggers(state: CallState, phase: Phase) -> None:
    trigger = to_trigger(state, reading(phase))
    assert trigger is None or (state, trigger) in TRANSITIONS


@pytest.mark.parametrize(
    ("state", "phase", "trigger"),
    [
        (CallState.MENU, Phase.HOLD, Trigger.HOLD_STARTED),
        (CallState.MENU, Phase.HUMAN, Trigger.HUMAN_DETECTED),
        (CallState.MENU, Phase.MENU, None),
        (CallState.HOLD, Phase.HUMAN, Trigger.HUMAN_DETECTED),
        (CallState.HOLD, Phase.MENU, Trigger.MENU_RETURNED),
        (CallState.HOLD, Phase.HOLD, None),
        (CallState.HUMAN_DETECTED, Phase.HOLD, Trigger.FALSE_HUMAN),
        (CallState.HUMAN_DETECTED, Phase.HUMAN, None),
        (CallState.HUMAN_DETECTED, Phase.MENU, None),
        (CallState.BRIDGING, Phase.HOLD, None),
        (CallState.CONNECTED, Phase.HUMAN, None),
    ],
)
def test_mapping_table(state: CallState, phase: Phase, trigger: Trigger | None) -> None:
    assert to_trigger(state, reading(phase)) == trigger


@pytest.mark.parametrize("state", list(CallState))
def test_unclear_never_fires(state: CallState) -> None:
    assert to_trigger(state, reading(Phase.UNCLEAR)) is None


@pytest.mark.parametrize(
    ("state", "phase", "below", "at"),
    [
        (CallState.HOLD, Phase.HUMAN, 0.69, 0.7),
        (CallState.MENU, Phase.HUMAN, 0.79, 0.8),
        (CallState.HUMAN_DETECTED, Phase.HOLD, 0.74, 0.75),
        (CallState.MENU, Phase.HOLD, 0.59, 0.6),
        (CallState.HOLD, Phase.MENU, 0.59, 0.6),
    ],
)
def test_thresholds_are_asymmetric(
    state: CallState, phase: Phase, below: float, at: float
) -> None:
    assert to_trigger(state, reading(phase, below)) is None
    assert to_trigger(state, reading(phase, at)) is not None


# --- the cascade ---


async def test_repeat_of_hold_message_skips_the_model() -> None:
    llm = FakeLlm()
    result = await classify_with(llm, HOLD_IMPORTANT.lower().replace(",", ""))

    assert result.phase == Phase.HOLD
    assert result.source == ReadingSource.REPEAT
    assert llm.calls == []


async def test_repeat_of_menu_prompt_stays_menu() -> None:
    menu = "For an appointment, press one. For all other questions, press zero."
    llm = FakeLlm()
    result = await classify_with(
        llm,
        "for an appointment press one for all other questions press zero",
        state=CallState.MENU,
        history=[HeardTurn(text=menu, at_s=30, phase=Phase.MENU)],
        at_s=60,
    )

    assert result.phase == Phase.MENU
    assert to_trigger(CallState.MENU, result) is None
    assert llm.calls == []


async def test_quick_repeat_from_a_person_is_not_a_recording() -> None:
    """ "Hello, is anyone there?" said twice, seconds apart, is a person."""
    text = "Hello, hello, is anyone there on the line?"
    llm = FakeLlm({"phase": "human", "confidence": 0.9, "reason_en": "Asks if anyone"})
    result = await classify_with(
        llm, text, history=[HeardTurn(text=text, at_s=595, phase=Phase.HOLD)]
    )

    assert result.source == ReadingSource.MODEL
    assert len(llm.calls) == 1


async def test_repeat_of_a_human_reading_goes_to_the_model() -> None:
    llm = FakeLlm()
    await classify_with(
        llm,
        REP_GREETING,
        history=[HeardTurn(text=REP_GREETING, at_s=300, phase=Phase.HUMAN)],
    )
    assert len(llm.calls) == 1


async def test_rep_greeting_is_not_a_repeat_of_the_hold_opener() -> None:
    cues = read_cues(REP_GREETING, 600, HOLD_LOOP)
    assert cues.repeat_of is None
    assert cues.introduces_self and cues.asks_caller and not cues.says_automated


async def test_model_reading_passes_through_clamped_and_scrubbed() -> None:
    llm = FakeLlm(
        {
            "phase": "human",
            "confidence": 1.4,
            "reason_en": 'Said "my ID is 4 7 2 9" and asked a question',
        }
    )
    result = await classify_with(llm, REP_GREETING)

    assert result.phase == Phase.HUMAN
    assert result.confidence == 1.0
    assert '"' not in result.reason_en and "4 7 2 9" not in result.reason_en
    assert to_trigger(CallState.HOLD, result) == Trigger.HUMAN_DETECTED


async def test_prompt_carries_state_history_and_cues() -> None:
    llm = FakeLlm()
    await classify_with(llm, REP_GREETING, state_since_s=60)
    user = str(llm.calls[0]["user"])

    assert "CALL STATE: hold (for 9 min)" in user
    assert HOLD_LOOP[-1].text in user
    assert "introduces a person by name: yes" in user
    assert REP_GREETING in user


def test_prompt_marks_the_first_utterance() -> None:
    cues = read_cues("Thank you for calling.", 3, [])
    prompt = build_user_prompt("Thank you for calling.", CallState.MENU, 3, [], cues, 3)
    assert "first utterance" in prompt
    assert "RECENT LINE SPEECH" not in prompt


@pytest.mark.parametrize("state", sorted(set(CallState) - LISTENING_STATES))
async def test_no_model_call_outside_listening_states(state: CallState) -> None:
    llm = FakeLlm()
    result = await classify_with(llm, REP_GREETING, state=state)

    assert result.source == ReadingSource.SKIPPED
    assert to_trigger(state, result) is None
    assert llm.calls == []


async def test_empty_utterance_is_skipped() -> None:
    llm = FakeLlm()
    result = await classify_with(llm, "   ")
    assert result.source == ReadingSource.SKIPPED
    assert llm.calls == []


# --- the fallback ---


@pytest.mark.parametrize(
    "error", [LlmError("API error: InternalServerError"), LlmError("no parsed output")]
)
async def test_model_error_falls_back_to_cues(error: LlmError) -> None:
    result = await classify_with(FakeLlm(error=error), REP_GREETING)

    assert result.source == ReadingSource.FALLBACK
    assert to_trigger(CallState.HOLD, result) == Trigger.HUMAN_DETECTED


async def test_slow_model_times_out_and_falls_back() -> None:
    llm = FakeLlm(delay_s=1.0)
    start = asyncio.get_running_loop().time()
    result = await classify_with(llm, REP_GREETING, timeout_s=0.05)

    assert asyncio.get_running_loop().time() - start < 0.5
    assert result.source == ReadingSource.FALLBACK


async def test_fallback_log_has_context_but_no_transcript(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.phone.phase"):
        await classify_with(
            FakeLlm(error=LlmError("timed out after 3.0s")),
            REP_GREETING,
            call_id="call_9",
        )

    assert "call_id=call_9" in caplog.text
    assert "state=hold" in caplog.text
    assert "Daniel" not in caplog.text


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_fallback_never_fires_a_wrong_trigger(case) -> None:
    """With Claude down, the cues may abstain, but anything they fire is right."""
    cues = read_cues(case.heard, case.at_s, case.history)
    if cues.repeat_of is not None:
        assert cues.repeat_of.phase in case.phases
    else:
        assert to_trigger(case.state, fallback_reading(cues)) in {case.trigger, None}


def test_fallback_still_catches_a_clear_rep_greeting() -> None:
    """The reason for allowing a cue-only human: an outage on hold can't lose the call."""
    clear = [c for c in CASES if c.trigger == Trigger.HUMAN_DETECTED]
    fired = [
        c.name
        for c in clear
        if to_trigger(c.state, fallback_reading(read_cues(c.heard, c.at_s, c.history)))
        == Trigger.HUMAN_DETECTED
    ]
    assert len(fired) >= len(clear) // 2, fired


@pytest.mark.parametrize(
    "text",
    [
        "Hi, I'm Ava, the automated virtual assistant. What can I help you with today?",
        "Did you know you can check your case status online? Visit our website.",
        "This is the contact center. How can we help? For forms, press one.",
    ],
)
def test_fallback_does_not_call_a_recording_human(text: str) -> None:
    result = fallback_reading(read_cues(text, 600, HOLD_LOOP))
    assert result.phase != Phase.HUMAN
