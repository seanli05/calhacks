"""The phone playground on a fake model: command parsing, a session on the real runner,
ask_user answered and timed out, steering (/fail, /phase), save → replay, and the
replay check. No real Claude; the phrases are made up and follow no particular tree.
"""

from pathlib import Path
from typing import Any

import pytest
from app.contracts import CallState
from app.phone.menu import (
    AskUserAction,
    AskUserOption,
    MenuAction,
    MenuDecision,
    PressAction,
    SayAction,
    WaitAction,
)
from app.phone.observe import StepRecord
from app.phone.phase import PhaseJudgment
from app.phone.playground import render
from app.phone.playground.repl import Meta, parse, parse_duration
from app.phone.playground.replay import recorded_answers, replay
from app.phone.playground.script import (
    Expect,
    FailStep,
    HeardStep,
    LineStep,
    Outcome,
    PhaseStep,
    ReplyStep,
    Script,
    SoundStep,
    TimeoutStep,
    WaitStep,
    check,
    load,
    save,
)
from app.phone.playground.session import CallSession, rebuild
from app.phone.playground.tap import TapLlm, parse_typed_action

S = CallState

GREETING = "Thanks for calling the benefits line. This call may be recorded."
MAIN = "For an interview or appointment, press four. For billing, press six."
COMMIT = "To cancel your interview, press one. To move it to a later date, press two."
HOLD = "Please hold for the next available officer."
REP = "Hi, this is Jordan, who am I speaking with?"


def _press(digits: str) -> PressAction:
    return PressAction(
        kind="press", digits=digits, option_label_en="option", reason_en="test"
    )


def _ask() -> AskUserAction:
    return AskUserAction(
        kind="ask_user",
        question_en="Cancel or move?",
        options=[
            AskUserOption(label_en="Move to a later date", digits="2"),
            AskUserOption(label_en="Cancel the interview", digits="1"),
        ],
        default_option=1,
        reason_en="test",
    )


def _menu(heard: str) -> MenuAction:
    if "cancel" in heard:
        return _ask()
    if "press four" in heard:
        return _press("4")
    return WaitAction(kind="wait", reason_en="test")


def _phase(heard: str) -> tuple[str, float]:
    if "hold" in heard:
        return "hold", 0.9
    if "who am i speaking" in heard:
        return "human", 0.95
    return "menu", 0.9


class FakeLlm:
    """1c and 1b answered from the NOW HEARD line, like the runner tests' fake."""

    def __init__(self) -> None:
        self.calls = 0

    async def parse(
        self, *, system: str, user: str, output_type: type, timeout_s: float
    ) -> Any:
        self.calls += 1
        heard = user.rsplit("\n", 1)[-1].strip().strip('"').lower()
        if output_type is PhaseJudgment:
            phase, confidence = _phase(heard)
            return PhaseJudgment(phase=phase, confidence=confidence, reason_en="cues")
        return MenuDecision(action=_menu(heard))


class NoModel:
    async def parse(self, **_: Any) -> Any:
        raise AssertionError("the model must not be called")


async def _session() -> CallSession:
    session = CallSession(TapLlm(FakeLlm()), step_wait_s=10)
    await session.start()
    return session


# Command parsing


def test_plain_text_is_what_the_line_said() -> None:
    assert parse("For billing, press six.", question_open=False) == HeardStep(
        text="For billing, press six."
    )


def test_a_gap_prefix_sets_the_time_since_the_last_line() -> None:
    step = parse("+3m Thank you for holding.", question_open=False)
    assert step == HeardStep(text="Thank you for holding.", after_s=180)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("/music 2m", SoundStep(sound="music", seconds=120)),
        ("/silence 20s", SoundStep(sound="silence", seconds=20)),
        ("/wait 1m30s", WaitStep(seconds=90)),
        ("/hangup", LineStep(event="agency_hung_up")),
        ("/no-answer", LineStep(event="no_answer")),
        ("/user answers", LineStep(event="user_answered")),
        ("/phase human 0.65", PhaseStep(phase="human", confidence=0.65)),
        ("/fail menu", FailStep(kind="menu")),
        ("/reply 2", ReplyStep(choice=2)),
        ("/timeout", TimeoutStep()),
        ("/undo", Meta("undo")),
        ("/save calm_line A short call", Meta("save", "calm_line A short call")),
    ],
)
def test_commands(line: str, expected: object) -> None:
    assert parse(line, question_open=False) == expected


def test_while_a_question_is_open_a_number_answers_and_enter_times_out() -> None:
    assert parse("2", question_open=True) == ReplyStep(choice=2)
    assert parse("", question_open=True) == TimeoutStep()
    assert parse("", question_open=False) is None
    assert parse("2", question_open=False) == HeardStep(text="2")


@pytest.mark.parametrize(
    "line", ["/bogus", "/reply x", "/phase maybe", "/fail both", "/wait soon", "/user"]
)
def test_bad_commands_say_why(line: str) -> None:
    with pytest.raises(ValueError):
        parse(line, question_open=False)


def test_durations() -> None:
    assert parse_duration("45") == 45
    assert parse_duration("2m") == 120
    assert parse_duration("1m5s") == 65
    with pytest.raises(ValueError):
        parse_duration("")


def test_typed_model_answers() -> None:
    press = parse_typed_action("p 4 interview or appointment")
    assert isinstance(press, PressAction) and press.digits == "4"
    assert isinstance(parse_typed_action(""), WaitAction)
    assert isinstance(parse_typed_action("s representative"), SayAction)
    assert parse_typed_action("x") is None
    ask = parse_typed_action("a 1 | 2=Keep the date | 1=Move it")
    assert isinstance(ask, AskUserAction)
    assert [o.digits for o in ask.options] == ["2", "1"]
    with pytest.raises(ValueError):
        parse_typed_action("press four")


# A call on the real runner


async def test_a_call_from_greeting_to_the_applicant_joining() -> None:
    session = await _session()
    greeting = await session.run(HeardStep(text=GREETING))
    menu = await session.run(HeardStep(text=MAIN))
    hold = await session.run(HeardStep(text=HOLD))
    rep = await session.run(HeardStep(text=REP))
    joined = await session.run(LineStep(event="user_answered"))
    ended = await session.run(LineStep(event="agency_hung_up"))

    assert greeting and greeting.state == S.MENU and greeting.kind == "wait"
    assert menu and isinstance(menu.action, PressAction) and menu.action.digits == "4"
    assert "speech: four" in [sent for r in menu.records for sent in r.sent]
    assert hold and hold.state == S.HOLD and hold.kind == "none"
    assert rep and rep.state == S.BRIDGING
    assert joined and joined.state == S.CONNECTED
    assert ended and ended.state == S.ENDED and session.ended
    assert session.report is not None
    await session.close()


async def test_the_family_answers_and_the_answer_is_pressed() -> None:
    session = await _session()
    asked = await session.run(HeardStep(text=COMMIT))
    assert asked and asked.kind == "ask_user"
    assert session.relay.open is not None

    answered = await session.run(ReplyStep(choice=1))

    assert answered and isinstance(answered.action, PressAction)
    assert answered.action.digits == "2"  # option 1 is the key-2 choice
    assert session.relay.open is None
    await session.close()


async def test_no_answer_takes_the_default_at_the_timeout() -> None:
    session = await _session()
    await session.run(HeardStep(text=COMMIT))
    question = session.relay.open
    assert question is not None

    timed_out = await session.run(TimeoutStep())

    assert timed_out and isinstance(timed_out.action, PressAction)
    assert timed_out.action.digits == "2"  # the default, option 1
    assert session.relay.timed_out == [question.request.question_id]
    await session.close()


async def test_a_reply_with_no_open_question_is_noted_not_raised() -> None:
    session = await _session()
    outcome = await session.run(ReplyStep(choice=1))
    assert outcome and outcome.note and "no open question" in outcome.note
    await session.close()


async def test_an_event_that_doesnt_fit_the_state_is_shown_not_crashing() -> None:
    session = await _session()
    await session.run(HeardStep(text=GREETING))
    outcome = await session.run(LineStep(event="user_answered"))
    assert outcome and outcome.state == S.MENU and "ignored" in outcome.flags
    assert not session.ended
    await session.close()


async def test_two_failed_decisions_wait_then_ask_for_a_person() -> None:
    session = await _session()
    await session.run(FailStep(kind="menu"))
    first = await session.run(HeardStep(text=MAIN))
    await session.run(FailStep(kind="menu"))
    second = await session.run(HeardStep(text="Sorry, I didn't get that. " + MAIN))

    assert first and isinstance(first.action, WaitAction) and first.action.fallback
    assert second and isinstance(second.action, SayAction)
    assert second.action.fallback and second.action.text == "representative"
    failed = [c for c in session.llm.calls if c.source == "failed"]
    assert len(failed) == 2
    await session.close()


async def test_a_forced_doubtful_reading_on_hold_doesnt_ring_the_applicant() -> None:
    session = await _session()
    await session.run(HeardStep(text=HOLD))
    await session.run(PhaseStep(phase="human", confidence=0.65))
    doubtful = await session.run(HeardStep(text="Thank you for holding.", after_s=60))
    assert doubtful and doubtful.state == S.HOLD
    assert doubtful.records[0].reading is not None
    assert doubtful.records[0].reading.confidence == 0.65
    lines = render.outcome_lines(
        doubtful, session, len(session.steps) - 1, verbose=False
    )
    assert any("human 0.65 < 0.70 needed" in line for line in lines)
    await session.close()


async def test_undo_redoes_the_steps_from_recorded_answers() -> None:
    session = await _session()
    for text in (GREETING, MAIN, HOLD):
        await session.run(HeardStep(text=text))
    answers = session.recorded_model()
    steps = session.steps[:-1]
    await session.close()

    redone = await rebuild(
        steps,
        lambda recorded, until: TapLlm(
            NoModel(), cassette=recorded, cassette_until=until
        ),
        answers,
        goal=None,
        config=None,
        step_wait_s=10,
    )
    assert redone.state == S.MENU
    assert len(redone.steps) == 2
    await redone.close()


# Save, replay, check


async def test_save_then_replay_from_recorded_answers_passes(tmp_path: Path) -> None:
    session = await _session()
    for step in (
        HeardStep(text=GREETING),
        HeardStep(text=COMMIT),
        ReplyStep(choice=2),
        HeardStep(text=HOLD),
    ):
        await session.run(step)
    path = tmp_path / "saved.json"
    save(session.to_script("round trip"), path)
    await session.close()

    script = load(path)
    llm = TapLlm(
        NoModel(),
        cassette=recorded_answers(script),
        cassette_until=len(script.steps),
    )
    rows, _ = await replay(script, llm, step_wait_s=10)

    assert [row.passed for row in rows] == [True] * 4
    assert script.steps[1].expect == Expect(
        state=S.MENU, kind=["ask_user"], options=["1", "2"]
    )


async def test_replay_fails_on_the_property_that_changed() -> None:
    script = Script(
        steps=[
            HeardStep(text=MAIN, expect=Expect(kind=["press"], digits=["6"])),
            HeardStep(text=HOLD, expect=Expect(state=S.MENU)),
            HeardStep(text=REP, expect=Expect(kind=["none", "wait"])),
        ]
    )
    rows, _ = await replay(script, TapLlm(FakeLlm()), step_wait_s=10)

    assert rows[0].problems == ["keys 4, expected 6"]
    assert rows[1].problems == ["state hold, expected menu"]
    assert rows[2].passed


def test_check_reads_properties_not_wording() -> None:
    say = SayAction(kind="say", text="Calling about an interview", reason_en="t")
    outcome = Outcome(records=[_record(say)], state=S.MENU)
    assert (
        check(Expect(kind=["say"], say_matches="interview|appointment"), outcome) == []
    )
    assert check(Expect(say_matches="cancel"), outcome) == ["say didn't match /cancel/"]
    assert check(Expect(kind=["press", "wait"]), outcome) == [
        "say, expected press/wait"
    ]
    assert check(Expect(fallback=True), outcome) == ["expected a fallback"]


def _record(action: MenuAction) -> StepRecord:
    return StepRecord(
        at_s=0, input="heard", state_before=S.MENU, state_after=S.MENU, action=action
    )


async def test_fake_mode_without_a_model_falls_back_to_cues() -> None:
    session = CallSession(TapLlm(None), step_wait_s=10)  # --fake, no typed answers
    await session.start()
    outcome = await session.run(HeardStep(text=HOLD))
    assert outcome and outcome.records[0].reading is not None
    assert outcome.records[0].reading.source == "fallback"
    assert any(isinstance(c.error, str) for c in session.llm.calls)
    await session.close()
