"""The call runner (1e) on fakes: a fake Claude, a scripted line, virtual time.

What would hurt in the demo: the states and events of a whole call, ask_user while
the menu keeps talking, every way a call ends, the guard, and the report always
being written. Line scripts are small and made up; they follow no particular tree.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from app.contracts import CallJob, CallOutcome, CallReport, Event, EventType
from app.contracts.common import CallState
from app.phone import call_lines
from app.phone.fakes import (
    Action,
    Answer,
    ConnectedUser,
    FakeCallStore,
    FakeCaseReader,
    FakeClock,
    FakeEventLog,
    FakeNumberSource,
    FakeRelay,
    FakeTelephony,
    HungUp,
    NoAnswer,
    PressedKeys,
    RangListener,
    RangUser,
    Said,
    Step,
)
from app.phone.guard import GuardedTelephony
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    HangUpRequested,
    Heard,
    ListenEnded,
    ListenRequested,
    ListenStarted,
    NonSpeech,
    Overheard,
    SpeechStarted,
    UserAnswered,
    UserLeft,
    UserUnreachable,
)
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
from app.phone.ports import CallDeps
from app.phone.runner import RunnerConfig, run_call

S = CallState
OFFICIAL = "+18005550100"
BLOCKED_A_NUMBER = "A123456789"
BRIEF = {
    "brief_id": "brief_77",
    "case_id": "case_123",
    "call_goal_en": "Confirm the interview is still scheduled",
}


def _job() -> CallJob:
    return CallJob(
        case_id="case_123",
        user_id="user_9",
        brief_id="brief_77",
        user_language="es",
        consent_at=datetime(2026, 10, 25, 10, 2, tzinfo=UTC),
        consent_message_id="msg_41",
        max_hold_minutes=60,
    )


# A fake Claude: the phase and the menu action come from what was heard.


def _phase(heard: str) -> tuple[str, float]:
    text = heard.lower()
    if "virtual assistant" in text:
        return "human", 0.5
    if "press" in text or "say" in text:
        return "menu", 0.95
    if "this is" in text and "?" in text:
        return "human", 0.92
    if "hold" in text or "wait" in text:
        return "hold", 0.9
    return "unclear", 0.3


def _press(digits: str, label: str = "option") -> PressAction:
    return PressAction(
        kind="press", digits=digits, option_label_en=label, reason_en="test"
    )


def _wait() -> WaitAction:
    return WaitAction(kind="wait", reason_en="test")


def _ask() -> AskUserAction:
    return AskUserAction(
        kind="ask_user",
        question_en="Which topic?",
        options=[
            AskUserOption(label_en="Pending application", digits="4"),
            AskUserOption(label_en="Interview notice", digits="6"),
        ],
        default_option=1,
        reason_en="test",
    )


class FakeLlm:
    """Answers 1c from `phase` and 1b from `menu`, keyed on the NOW HEARD line."""

    def __init__(
        self,
        menu: Callable[[str], MenuAction],
        phase: Callable[[str], tuple[str, float]] = _phase,
    ) -> None:
        self._menu = menu
        self._phase = phase
        self.menu_calls: list[str] = []

    async def parse(
        self, *, system: str, user: str, output_type: type, timeout_s: float
    ) -> Any:
        heard = user.rsplit("\n", 1)[-1].strip().strip('"')
        if output_type is PhaseJudgment:
            phase, confidence = self._phase(heard)
            return PhaseJudgment(phase=phase, confidence=confidence, reason_en="cues")
        self.menu_calls.append(heard)
        return MenuDecision(action=self._menu(heard))


def _menu_by_text(rules: dict[str, MenuAction]) -> Callable[[str], MenuAction]:
    def menu(heard: str) -> MenuAction:
        return next(
            (action for key, action in rules.items() if key in heard.lower()), _wait()
        )

    return menu


# The line


@dataclass
class Call:
    clock: FakeClock = field(default_factory=FakeClock)
    store: FakeCallStore = field(default_factory=FakeCallStore)
    log: FakeEventLog = field(default_factory=FakeEventLog)
    steps: list[StepRecord] = field(default_factory=list)
    line: FakeTelephony | None = None
    relay: FakeRelay | None = None
    say_s_per_word: float = 0.0

    def deps(
        self,
        script: Iterable[Step],
        responder: Callable[[Action], Iterable[Step]] | None,
        replies: Iterable[Answer | NoAnswer],
        verified: bool,
    ) -> CallDeps:
        numbers = FakeNumberSource(
            verified={"case_123": OFFICIAL} if verified else {},
            users={"user_9": "+15555550123"},
        )
        self.line = FakeTelephony(
            numbers, self.clock, script, responder, say_s_per_word=self.say_s_per_word
        )
        self.relay = FakeRelay(self.clock, replies)
        return CallDeps(
            telephony=GuardedTelephony(self.line, [BLOCKED_A_NUMBER]),
            relay=self.relay,
            cases=FakeCaseReader({"brief_77": BRIEF}),
            calls=self.store,
            events=self.log,
            clock=self.clock,
        )

    @property
    def record(self):
        [call] = self.store.calls.values()
        return call

    @property
    def actions(self) -> list[Action]:
        assert self.line is not None
        return self.line.actions

    def events_of(self, event_type: EventType) -> list[Event]:
        return [event for event in self.log.events if event.type == event_type]


async def _run(
    llm: FakeLlm,
    script: Iterable[Step],
    responder: Callable[[Action], Iterable[Step]] | None = None,
    *,
    replies: Iterable[Answer | NoAnswer] = (),
    verified: bool = True,
    config: RunnerConfig | None = None,
    call: Call | None = None,
) -> tuple[Call, CallReport]:
    call = call or Call()
    deps = call.deps(script, responder, replies, verified)
    report = await call.clock.run(
        run_call(
            "job_12", _job(), deps, llm=llm, observer=call.steps.append, config=config
        )
    )
    return call, report


def _sent_step(
    call: Call, sent: str, among: Iterable[StepRecord] | None = None
) -> StepRecord:
    """The first step that put `sent` on the line."""
    return next(step for step in among or call.steps if sent in step.sent)


MENU = "For appointments, press 2. For anything else, press 3."
REP = "Thank you for holding, this is Maria, how can I help you?"


def _opening(prompt: str = MENU) -> list[Step]:
    return [Step(2, AgencyAnswered()), Step(1, Heard(text=prompt))]


def _to_rep(on: Action, *, user: Step | None = None) -> Callable[[Action], list[Step]]:
    """After `on`: hold music, a hold message, then a person. The user answers."""

    def tree(action: Action) -> list[Step]:
        if action == on:
            return [
                Step(1, NonSpeech(sound="music", seconds=30)),
                Step(30, Heard(text="Please continue to hold.")),
                Step(60, Heard(text=REP)),
            ]
        if isinstance(action, RangUser):
            return [user or Step(8, UserAnswered())]
        if isinstance(action, ConnectedUser):
            return [
                Step(90, Heard(text="Okay, the interview is still on.")),
                Step(20, AgencyHungUp()),
            ]
        return []

    return tree


# The whole call


async def test_happy_path_persists_each_state_and_logs_each_event() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2", "appointments")}))
    call, report = await _run(llm, _opening(), _to_rep(Said("two")))

    assert call.record.states == [
        S.DIALING,  # create_call
        S.DIALING,  # with the SID, once the dial went out
        S.MENU,
        S.HOLD,
        S.HUMAN_DETECTED,
        S.BRIDGING,
        S.CONNECTED,
        S.WRAP_UP,
        S.ENDED,
    ]
    assert call.log.types == [
        EventType.CALL_DIALING,
        EventType.CALL_MENU_HEARD,
        EventType.CALL_MENU_CHOICE,
        EventType.CALL_ON_HOLD,
        EventType.CALL_HUMAN_DETECTED,
        EventType.CALL_USER_DIALED,
        EventType.CALL_USER_JOINED,
        EventType.CALL_ENDED,
    ]
    assert call.actions[1:] == [
        Said("two"),
        RangUser(call.record.call_id, "user_9", "+15555550123"),
        Said(call_lines.INTRO),
        ConnectedUser(),
        HungUp(),
    ]
    assert call.events_of(EventType.CALL_MENU_CHOICE)[0].data["digit"] == "2"
    assert call.events_of(EventType.CALL_HUMAN_DETECTED)[0].data["phase"] == "human"
    # Connected and ended normally: partial until the Phase 4 report reads it.
    assert report.outcome == CallOutcome.PARTIAL
    assert call.record.report == report
    assert report.transcript_id == call.record.transcript_id
    speakers = [line.speaker for line in call.record.transcript]
    assert speakers == ["agency", "agent", "agency", "agency", "agent", "agency"]
    [ended] = call.events_of(EventType.CALL_ENDED)
    assert ended.data["cause"] == "agency_hung_up"


async def test_observer_sees_readings_actions_and_transitions() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2", "appointments")}))
    call, _ = await _run(llm, _opening(), _to_rep(Said("two")))

    menu_step = next(step for step in call.steps if step.text == MENU)
    assert menu_step.reading is not None and menu_step.reading.phase == "menu"
    assert isinstance(menu_step.action, PressAction)
    assert menu_step.sent == []
    assert "held" in menu_step.flags
    sent_step = _sent_step(call, "speech: two")
    assert sent_step.input == "timer:menu_quiet"
    assert sent_step.at_s == pytest.approx(menu_step.at_s + 1.0)
    assert set(menu_step.latency_ms) == {"classify", "decide"}
    assert call.steps[0].input == "dial"
    assert call.steps[-1].input == "wrap_up"
    assert call.steps[-1].state_after == S.ENDED


# ask_user


ASK_MENU = "For a pending application, press 4. For interview notices, press 6."


def _hang_up_after(action: Action) -> Callable[[Action], list[Step]]:
    return lambda a: [Step(1, AgencyHungUp())] if a == action else []


async def test_ask_user_answer_is_pressed() -> None:
    llm = FakeLlm(_menu_by_text({"press 4": _ask()}))
    call, _ = await _run(
        llm,
        _opening(ASK_MENU),
        _hang_up_after(Said("six")),
        replies=[Answer(2, after_s=5)],
    )
    assert call.relay is not None
    [asked] = call.relay.asked
    assert asked.timeout_s == 30
    assert asked.call_id == call.record.call_id
    assert Said("six") in call.actions
    [choice] = call.events_of(EventType.CALL_MENU_CHOICE)
    assert choice.data == {"digit": "6", "via": "speech", "source": "ask_user"}
    # The relay logs every call.ask_user* event; the runner logs none.
    assert not {EventType.CALL_ASK_USER, EventType.CALL_ASK_USER_ANSWERED} & set(
        call.log.types
    )


async def test_ask_user_timeout_takes_the_default() -> None:
    llm = FakeLlm(_menu_by_text({"press 4": _ask()}))
    call, _ = await _run(
        llm, _opening(ASK_MENU), _hang_up_after(Said("four")), replies=[NoAnswer()]
    )
    assert Said("four") in call.actions
    # Asked once the menu had been quiet 1 s; the default goes out at the timeout.
    assert _sent_step(call, "speech: four").at_s == pytest.approx(3 + 1 + 30)


async def test_menu_reprompts_while_asking_take_the_default_early() -> None:
    reprompt = "Sorry, I didn't get that. " + ASK_MENU
    script = [*_opening(ASK_MENU), Step(7, Heard(text=reprompt))]
    script.append(Step(7, Heard(text=reprompt)))
    llm = FakeLlm(_menu_by_text({"press 4": _ask()}))
    call, _ = await _run(
        llm, script, _hang_up_after(Said("four")), replies=[NoAnswer()]
    )

    # Reprompts aren't decided again (that would ask again); the second one
    # takes the default instead of waiting out the 30 s.
    assert len(llm.menu_calls) == 1
    assert call.relay is not None
    assert call.relay.cancelled == [call.relay.asked[0].question_id]
    # The default is held until the second reprompt has been quiet 1 s.
    assert _sent_step(call, "speech: four").at_s == pytest.approx(3 + 14 + 1)
    flags = [flag for step in call.steps for flag in step.flags]
    assert flags.count("reprompt_while_asking") == 2
    assert "ask_default_early" in flags


async def test_a_new_prompt_while_asking_drops_the_question() -> None:
    script = [*_opening(ASK_MENU), Step(6, Heard(text="To repeat, press 9."))]
    llm = FakeLlm(_menu_by_text({"press 4": _ask(), "press 9": _press("9")}))
    call, _ = await _run(
        llm, script, _hang_up_after(Said("nine")), replies=[Answer(2, after_s=20)]
    )
    assert call.relay is not None
    assert len(call.relay.cancelled) == 1
    assert Said("nine") in call.actions
    assert Said("six") not in call.actions


# Every way a call ends


async def test_hold_timeout_hangs_up_and_reports_failed() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    tree = _hang_up_after(Said("nothing"))  # the hold never ends

    def hold_forever(action: Action) -> list[Step]:
        if action == Said("two"):
            return [Step(1, NonSpeech(sound="music", seconds=30))]
        return tree(action)

    call, report = await _run(llm, _opening(), hold_forever)
    assert call.record.states[-3:] == [S.HOLD, S.WRAP_UP, S.ENDED]
    assert report.outcome == CallOutcome.FAILED
    assert report.next_steps_en and "hold" in report.next_steps_en[0]
    assert isinstance(call.actions[-1], HungUp)
    [ended] = call.events_of(EventType.CALL_ENDED)
    assert ended.data["cause"] == "hold_timeout"
    assert ended.data["minutes"] == 60


async def test_listening_in_runs_beside_the_call_and_never_ends_it() -> None:
    """The user asks to sit in during the menu, listens, and hangs up; the call
    goes on exactly as it would have."""
    llm = FakeLlm(_menu_by_text({"press 2": _press("2", "appointments")}))
    to_rep = _to_rep(Said("two"))

    def tree(action: Action) -> list[Step]:
        if isinstance(action, RangListener):
            return [Step(5, ListenStarted()), Step(20, ListenEnded(reason="hung_up"))]
        return to_rep(action)

    script = [*_opening(), Step(0.5, ListenRequested())]
    call, report = await _run(llm, script, tree)

    rang = RangListener(call.record.call_id, "user_9", "+15555550123")
    assert rang in call.actions
    assert call.record.states[-5:] == [
        S.HUMAN_DETECTED,
        S.BRIDGING,
        S.CONNECTED,
        S.WRAP_UP,
        S.ENDED,
    ]
    assert EventType.CALL_USER_JOINED in call.log.types
    assert report.outcome == CallOutcome.PARTIAL
    ended = next(step for step in call.steps if step.input == "listen_ended")
    assert "listen_ended:hung_up" in ended.flags


async def test_hang_up_now_on_hold_cancels_the_call_without_a_word() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))

    def tree(action: Action) -> list[Step]:
        if action == Said("two"):
            return [
                Step(1, NonSpeech(sound="music", seconds=30)),
                Step(20, HangUpRequested()),
                Step(600, Heard(text=REP)),  # never reached
            ]
        return []

    call, report = await _run(llm, _opening(), tree)

    assert report.outcome == CallOutcome.CANCELLED
    assert call.actions[-2:] == [Said("two"), HungUp()]
    assert call.record.states[-3:] == [S.HOLD, S.WRAP_UP, S.ENDED]
    [ended] = call.events_of(EventType.CALL_ENDED)
    assert ended.data["cause"] == "user_ended"


async def test_hang_up_now_with_a_rep_waiting_says_goodbye_first() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    to_rep = _to_rep(Said("two"), user=Step(999, UserAnswered()))

    def tree(action: Action) -> list[Step]:
        if isinstance(action, RangUser):
            return [Step(5, HangUpRequested())]
        return to_rep(action)

    call, report = await _run(llm, _opening(), tree)

    assert report.outcome == CallOutcome.CANCELLED
    assert call.actions[-2:] == [Said(call_lines.USER_ENDED), HungUp()]
    assert ConnectedUser() not in call.actions


async def test_hang_up_now_on_a_connected_call_ends_it() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    to_rep = _to_rep(Said("two"))

    def tree(action: Action) -> list[Step]:
        if isinstance(action, ConnectedUser):
            return [Step(30, HangUpRequested())]
        return to_rep(action)

    call, report = await _run(llm, _opening(), tree)

    assert call.actions[-2:] == [ConnectedUser(), HungUp()]  # the agent stays silent
    assert report.outcome == CallOutcome.PARTIAL  # the report reads the conversation
    assert call.record.states[-3:] == [S.CONNECTED, S.WRAP_UP, S.ENDED]


async def test_a_failed_listen_ring_doesnt_stop_the_call() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    script = [*_opening(), Step(0.5, ListenRequested())]
    call = Call()
    deps = call.deps(script, _to_rep(Said("two")), (), True)
    assert call.line is not None

    async def broken(call_id: str, user_id: str) -> None:
        raise RuntimeError("boom")

    call.line.listen_in = broken  # type: ignore[method-assign]
    report = await call.clock.run(
        run_call("job_12", _job(), deps, llm=llm, observer=call.steps.append)
    )
    assert report.outcome == CallOutcome.PARTIAL
    assert any("listen_failed" in step.flags for step in call.steps)


async def test_user_unreachable_tells_the_rep_and_hangs_up() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    tree = _to_rep(Said("two"), user=Step(30, UserUnreachable(reason="no_answer")))
    call, report = await _run(llm, _opening(), tree)

    assert call.actions[-2:] == [Said(call_lines.CALL_BACK), HungUp()]
    assert report.outcome == CallOutcome.USER_UNREACHABLE
    assert EventType.CALL_USER_UNREACHABLE in call.log.types
    assert call.record.states[-3:] == [S.BRIDGING, S.WRAP_UP, S.ENDED]


async def test_user_never_heard_from_hits_the_backstop() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    tree = _to_rep(Said("two"), user=Step(999, UserAnswered()))
    call, report = await _run(llm, _opening(), tree)
    assert report.outcome == CallOutcome.USER_UNREACHABLE
    assert Said(call_lines.CALL_BACK) in call.actions
    rang = _sent_step(call, "rang the applicant")
    backstop = next(step for step in call.steps if step.input == "timer:user_backstop")
    # Long enough for 30 s of ringing plus the join gate.
    assert backstop.at_s - rang.at_s == pytest.approx(75)


async def test_no_key_at_the_join_gate_tells_the_rep_and_hangs_up() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    tree = _to_rep(Said("two"), user=Step(35, UserUnreachable(reason="no_key_press")))
    call, report = await _run(llm, _opening(), tree)

    assert call.actions[-2:] == [Said(call_lines.CALL_BACK), HungUp()]
    assert report.outcome == CallOutcome.USER_UNREACHABLE
    [unreachable] = call.events_of(EventType.CALL_USER_UNREACHABLE)
    assert unreachable.data["reason"] == "no_key_press"


async def test_the_applicant_joining_cuts_the_intro_short() -> None:
    """Speech takes time on a real line; a join mustn't wait for the intro to end."""
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    tree = _to_rep(Said("two"), user=Step(2, UserAnswered()))
    call, report = await _run(llm, _opening(), tree, call=Call(say_s_per_word=0.4))

    rang = _sent_step(call, "rang the applicant")
    joined = _sent_step(call, "connected the applicant")
    assert joined.at_s - rang.at_s == pytest.approx(2)  # the intro takes ~9 s
    assert "speech_cut" in joined.flags
    assert report.outcome == CallOutcome.PARTIAL


async def test_the_rep_talking_over_the_intro_gets_no_second_line() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    base = _to_rep(Said("two"), user=Step(20, UserAnswered()))

    def tree(action: Action) -> list[Step]:
        if isinstance(action, RangUser):
            return [Step(1, Heard(text="Hello? Who is this?")), *base(action)]
        return base(action)

    call, _ = await _run(llm, _opening(), tree, call=Call(say_s_per_word=0.4))
    assert Said(call_lines.HOLDING) not in call.actions
    talked_over = next(
        step for step in call.steps if step.text == "Hello? Who is this?"
    )
    assert "quiet" in talked_over.flags


async def test_overheard_lines_after_the_bridge_go_in_the_transcript() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    base = _to_rep(Said("two"))

    def tree(action: Action) -> list[Step]:
        if isinstance(action, ConnectedUser):
            return [
                Step(2, Overheard(speaker="agency", text="Can I have your name?")),
                Step(3, Overheard(speaker="user", text="Ana Morales.")),
                Step(9, Overheard(speaker="agency", text="Your reference is C447.")),
                Step(5, UserLeft()),
            ]
        return base(action)

    call, report = await _run(llm, _opening(), tree)

    after = call.record.transcript[-3:]
    assert [(line.speaker, line.text) for line in after] == [
        ("agency", "Can I have your name?"),
        ("user", "Ana Morales."),
        ("agency", "Your reference is C447."),
    ]
    [ended] = call.events_of(EventType.CALL_ENDED)
    assert ended.data["cause"] == "call_finished"
    assert report.outcome == CallOutcome.PARTIAL


def _hang_up_in(state: CallState) -> tuple[list[Step], Callable[[Action], list[Step]]]:
    if state == S.MENU:
        return [*_opening(), Step(5, AgencyHungUp())], lambda a: []
    base = _to_rep(Said("two"))

    def tree(action: Action) -> list[Step]:
        if state == S.HOLD and action == Said("two"):
            return [
                Step(1, NonSpeech(sound="music", seconds=30)),
                Step(40, AgencyHungUp()),
            ]
        if state == S.BRIDGING and isinstance(action, RangUser):
            return [Step(3, AgencyHungUp())]
        return base(action)

    return _opening(), tree


@pytest.mark.parametrize(
    ("state", "outcome"),
    [
        (S.MENU, CallOutcome.FAILED),
        (S.HOLD, CallOutcome.FAILED),
        (S.BRIDGING, CallOutcome.FAILED),
        (S.CONNECTED, CallOutcome.PARTIAL),
    ],
)
async def test_agency_hangs_up(state: CallState, outcome: CallOutcome) -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    script, tree = _hang_up_in(state)
    call, report = await _run(llm, script, tree)
    assert call.record.states[-3:] == [state, S.WRAP_UP, S.ENDED]
    assert report.outcome == outcome
    assert call.events_of(EventType.CALL_ENDED)[0].data["cause"] == "agency_hung_up"


async def test_agency_never_answers() -> None:
    from app.phone.line import AgencyUnreachable

    llm = FakeLlm(_menu_by_text({}))
    call, report = await _run(llm, [Step(20, AgencyUnreachable(reason="busy"))])
    assert call.record.states == [S.DIALING, S.DIALING, S.WRAP_UP, S.ENDED]
    assert report.outcome == CallOutcome.FAILED


# Detection


async def test_a_doubtful_person_doesnt_ring_the_applicant() -> None:
    """With the applicant rung at once (< 5 s), the defense against a false person
    is 1c's threshold: a named virtual assistant reads as a person at 0.5, which
    doesn't fire from hold; the real rep after it does."""
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))

    def tree(action: Action) -> list[Step]:
        if action == Said("two"):
            return [
                Step(1, NonSpeech(sound="music", seconds=30)),
                Step(30, Heard(text="Hi, this is Ava, your virtual assistant.")),
                Step(30, Heard(text=REP)),
            ]
        if isinstance(action, RangUser):
            return [Step(5, UserAnswered()), Step(10, AgencyHungUp())]
        return []

    call, _ = await _run(llm, _opening(), tree)
    rang = [step for step in call.steps if "rang the applicant" in step.sent]
    assert [step.text for step in rang] == [REP]
    assert call.events_of(EventType.CALL_HUMAN_DETECTED)[0].data["confidence"] == 0.92


async def test_music_in_a_menu_means_hold_without_a_model_call() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    call, _ = await _run(llm, _opening(), _to_rep(Said("two")))
    hold_step = next(step for step in call.steps if step.input == "non_speech")
    assert hold_step.state_after == S.HOLD
    assert hold_step.latency_ms == {}
    assert call.events_of(EventType.CALL_ON_HOLD)[0].data == {"cue": "music"}


# C35 and C37


async def test_a_blocked_identifier_never_reaches_the_line() -> None:
    leak = SayAction(
        kind="say", text="one two three four five six seven eight nine", reason_en="t"
    )
    script = [
        *_opening("Please say your A-Number."),
        Step(8, Heard(text="I didn't catch that. Please say your A-Number now.")),
        Step(8, AgencyHungUp()),
    ]
    llm = FakeLlm(_menu_by_text({"a-number": leak}))
    call, report = await _run(llm, script)

    said = [action.text for action in call.actions if isinstance(action, Said)]
    assert said == ["representative"]  # two blocked steps in a row → ask for a person
    flags = [flag for step in call.steps for flag in step.flags]
    assert flags.count("blocked") == 2
    assert report.outcome == CallOutcome.FAILED


async def test_a_keypad_only_step_falls_back_to_keys() -> None:
    reprompt = "We did not receive your selection. For appointments, press 5."
    script = [
        *_opening("For appointments, press 5."),
        Step(8, Heard(text=reprompt)),  # the spoken "five" wasn't taken
    ]

    def tree(action: Action) -> list[Step]:
        if action == PressedKeys("5"):
            return [
                Step(1, NonSpeech(sound="music", seconds=30)),
                Step(5, AgencyHungUp()),
            ]
        return []

    llm = FakeLlm(_menu_by_text({"press 5": _press("5", "appointments")}))
    call, _ = await _run(llm, script, tree)

    assert Said("five") in call.actions
    assert PressedKeys("5") in call.actions
    vias = [e.data["via"] for e in call.events_of(EventType.CALL_MENU_CHOICE)]
    assert vias == ["speech", "keys"]
    assert any("keypad_mode" in step.flags for step in call.steps)


async def test_a_prompt_that_names_the_keypad_is_keyed_at_once() -> None:
    llm = FakeLlm(_menu_by_text({"press 1": _press("1")}))
    call, _ = await _run(
        llm,
        _opening("Using your telephone keypad, press 1 for English."),
        _hang_up_after(PressedKeys("1")),
    )
    assert PressedKeys("1") in call.actions
    assert not any(isinstance(action, Said) for action in call.actions)


# Failures on our side


async def test_an_unexpected_error_aborts_but_still_wraps_up() -> None:
    def broken(heard: str) -> MenuAction:
        raise RuntimeError("bug in the decider")

    call, report = await _run(FakeLlm(broken), _opening())
    assert call.record.states[-3:] == [S.MENU, S.WRAP_UP, S.ENDED]
    assert report.outcome == CallOutcome.FAILED
    assert call.record.report == report
    assert isinstance(call.actions[-1], HungUp)
    [ended] = call.events_of(EventType.CALL_ENDED)
    assert ended.data["cause"] == "agent_aborted"
    assert ended.data["error"] == "RuntimeError"


async def test_an_unverified_number_is_never_dialed_or_announced() -> None:
    call, report = await _run(FakeLlm(_menu_by_text({})), [], verified=False)
    assert call.actions == [HungUp()]
    assert EventType.CALL_DIALING not in call.log.types
    assert report.outcome == CallOutcome.FAILED
    assert call.events_of(EventType.CALL_ENDED)[0].data["error"] == "UnverifiedNumber"


async def test_a_crash_with_the_applicant_on_keeps_the_bridge() -> None:
    class FailingOnJoin(FakeEventLog):
        async def append(self, event: Event) -> None:
            await super().append(event)
            if event.type == EventType.CALL_USER_JOINED:
                raise RuntimeError("event log down")

    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    call = Call(log=FailingOnJoin())
    call, report = await _run(llm, _opening(), _to_rep(Said("two")), call=call)

    # Nobody hung up on the applicant: the agency ended the call, 110 s later.
    hang_up_at = call.steps[-1].at_s
    joined_at = next(s.at_s for s in call.steps if "connected the applicant" in s.sent)
    assert hang_up_at - joined_at == pytest.approx(110)
    assert report.outcome == CallOutcome.PARTIAL
    assert call.record.states[-3:] == [S.CONNECTED, S.WRAP_UP, S.ENDED]


async def test_the_runner_refuses_an_unguarded_line() -> None:
    call = Call()
    deps = call.deps([], None, [], True)
    assert call.line is not None
    unguarded = CallDeps(
        telephony=call.line,
        relay=deps.relay,
        cases=deps.cases,
        calls=deps.calls,
        events=deps.events,
        clock=deps.clock,
    )
    with pytest.raises(TypeError, match="GuardedTelephony"):
        await run_call("job_12", _job(), unguarded, llm=FakeLlm(_menu_by_text({})))


async def test_menu_budget_gives_up() -> None:
    llm = FakeLlm(_menu_by_text({}))
    script = [*_opening(), *(Step(60, Heard(text=f"Message {i}.")) for i in range(9))]
    call, report = await _run(llm, script, config=RunnerConfig(menu_budget_s=300))
    assert report.outcome == CallOutcome.FAILED
    [ended] = call.events_of(EventType.CALL_ENDED)
    assert ended.data["error"] == "MenuGaveUp"
    assert call.steps[-1].at_s == pytest.approx(2 + 300)


# C27


async def test_no_event_carries_what_was_heard_or_said() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2", "appointments")}))
    call, _ = await _run(llm, _opening(), _to_rep(Said("two")))
    texts = [line.text for line in call.record.transcript]
    assert len(texts) >= 5
    for event in call.log.events:
        blob = json.dumps(event.data) + event.summary_en
        for text in texts:
            assert text not in blob
        assert "Maria" not in blob
        assert "appointments" not in blob


async def test_asking_for_a_person_too_often_gives_up() -> None:
    escape = SayAction(kind="say", text="representative", reason_en="t")
    script = [
        *_opening("Tell me why you're calling."),
        *(Step(8, Heard(text=f"I can help with that, version {i}.")) for i in range(4)),
    ]
    call, report = await _run(FakeLlm(lambda heard: escape), script)
    said = [action for action in call.actions if isinstance(action, Said)]
    assert len(said) == 3  # escape_limit, then the next one gives up
    assert report.outcome == CallOutcome.FAILED
    assert call.events_of(EventType.CALL_ENDED)[0].data["error"] == "MenuGaveUp"


async def test_a_menu_after_hold_is_answered_on_the_utterance_that_showed_it() -> None:
    second_menu = "Scheduling unit. For an existing appointment, press 2."
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))

    def tree(action: Action) -> list[Step]:
        if action == Said("two") and not any(
            isinstance(a, Said) and a.text == "two" for a in call.actions[:-1]
        ):
            return [
                Step(1, NonSpeech(sound="music", seconds=30)),
                Step(10, Heard(text=second_menu)),
            ]
        if action == Said("two"):
            return [Step(1, AgencyHungUp())]
        return []

    call = Call()
    call, _ = await _run(llm, _opening(), tree, call=call)
    returned = next(step for step in call.steps if step.text == second_menu)
    assert [t.trigger for t in returned.transitions] == ["menu_returned"]
    assert isinstance(returned.action, PressAction)
    later = [step for step in call.steps if step.at_s > returned.at_s]
    assert _sent_step(call, "speech: two", among=later).at_s == pytest.approx(
        returned.at_s + 1.0
    )


# Every option is heard before the agent answers


SPLIT_MENU = ("For case status, press 1.", "For interview appointments, press 2.")


def _option_one_first() -> FakeLlm:
    """Option 1 fits on its own; option 2 fits better once it has been heard."""
    return FakeLlm(_menu_by_text({"press 2": _press("2"), "press 1": _press("1")}))


def _said(call: Call) -> list[Said]:
    return [action for action in call.actions if isinstance(action, Said)]


async def test_options_heard_in_pieces_are_answered_once_after_the_last() -> None:
    llm = _option_one_first()
    script = [
        Step(2, AgencyAnswered()),
        Step(1, Heard(text=SPLIT_MENU[0])),
        Step(0.6, Heard(text=SPLIT_MENU[1])),
    ]
    call, _ = await _run(llm, script, _hang_up_after(Said("two")))

    assert _said(call) == [Said("two")]
    assert llm.menu_calls[-1] == " ".join(SPLIT_MENU)
    assert _sent_step(call, "speech: two").at_s == pytest.approx(3.6 + 1.0)


async def test_speech_starting_in_the_quiet_window_holds_the_answer() -> None:
    llm = _option_one_first()
    script = [
        Step(2, AgencyAnswered()),
        Step(1, Heard(text=SPLIT_MENU[0])),
        Step(0.5, SpeechStarted()),  # inside the 1 s window after option 1
        Step(2.5, Heard(text=SPLIT_MENU[1])),
    ]
    call, _ = await _run(llm, script, _hang_up_after(Said("two")))

    assert _said(call) == [Said("two")]
    assert _sent_step(call, "speech: two").at_s == pytest.approx(6 + 1.0)
    assert any("held_dropped" in step.flags for step in call.steps)


@pytest.mark.parametrize(
    ("close", "sent_at"),
    [
        (Step(1, NonSpeech(sound="silence", seconds=1)), 3.5 + 1 + 1.0),
        (None, 3.5 + 30 + 1.0),  # never closes: the backstop releases it
    ],
)
async def test_a_turn_with_no_words_lets_the_held_answer_out(
    close: Step | None, sent_at: float
) -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    script = [*_opening(), Step(0.5, SpeechStarted())]
    if close is not None:
        script.append(close)
    call, _ = await _run(llm, script, _hang_up_after(Said("two")))

    assert _said(call) == [Said("two")]
    assert _sent_step(call, "speech: two").at_s == pytest.approx(sent_at)
    assert llm.menu_calls == [MENU]
    flags = [flag for step in call.steps for flag in step.flags]
    assert ("turn_never_closed" in flags) is (close is None)


async def test_the_applicants_choice_waits_for_the_line_to_go_quiet() -> None:
    reprompt = "Sorry, I didn't get that. " + ASK_MENU
    script = [
        *_opening(ASK_MENU),  # heard at 3 s; asked at 4 s
        Step(5.5, SpeechStarted()),  # a reprompt starts at 8.5 s
        Step(3.5, Heard(text=reprompt)),  # and ends at 12 s
    ]
    llm = FakeLlm(_menu_by_text({"press 4": _ask()}))
    call, _ = await _run(
        llm,
        script,
        _hang_up_after(Said("six")),
        replies=[Answer(choice=2, after_s=5)],  # at 9 s, mid-reprompt
    )

    assert _said(call) == [Said("six")]
    assert _sent_step(call, "speech: six").at_s == pytest.approx(12 + 1.0)
    assert len(llm.menu_calls) == 1  # the reprompt wasn't decided, or asked, again
    assert any("reprompt_while_held" in step.flags for step in call.steps)


async def test_leaving_the_menu_drops_a_held_answer() -> None:
    llm = FakeLlm(_menu_by_text({"press 2": _press("2")}))
    script = [
        *_opening(),
        Step(0.5, NonSpeech(sound="music", seconds=6)),  # hold, before the answer
        Step(10, AgencyHungUp()),
    ]
    call, _ = await _run(llm, script)

    assert _said(call) == []
    assert S.HOLD in call.record.states
    assert any("held_dropped" in step.flags for step in call.steps)
