"""One call on the real runner (1e), driven a step at a time.

The runner runs unchanged on 1d fakes: `FakeTelephony` is the line (what you paste is
pushed as `Heard`; what the agent says or keys is recorded), `ConsoleRelay` is the
family, and a `FakeClock` keeps time still between steps, so the runner's timers
(ask timeout, hold limit, menu budget) fire only when a step moves the clock. Real
Claude takes real time, but no clock time.

A step is done when the runner has handled what the step caused and gone quiet: the
runner reports each handled input to its observer, so `run` waits for that report,
then for any model call still in flight. No step overlaps another.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.contracts import CallJob, CallReport, CallState
from app.db.reset import demo_brief
from app.phone.fakes import (
    FakeCallStore,
    FakeCaseReader,
    FakeClock,
    FakeEventLog,
    FakeNumberSource,
    FakeTelephony,
)
from app.phone.guard import GuardedTelephony
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    AgencyUnreachable,
    Heard,
    LineEvent,
    NonSpeech,
    UserAnswered,
    UserLeft,
    UserUnreachable,
)
from app.phone.observe import StepRecord
from app.phone.phase import PhaseJudgment
from app.phone.playground.script import (
    CONTROL_STEPS,
    FailStep,
    HeardStep,
    LineEventName,
    LineStep,
    Outcome,
    PhaseStep,
    ReplyStep,
    Script,
    ScriptStep,
    SoundStep,
    TimeoutStep,
    WaitStep,
    expect_from,
)
from app.phone.playground.tap import ConsoleRelay, ModelKind, Recorded, TapLlm
from app.phone.ports import CallDeps
from app.phone.runner import RunnerConfig, run_call
from app.phone.simulate import SIM_BLOCKED

logger = logging.getLogger(__name__)

CASE_ID = "case_playground"
USER_ID = "user_playground"
BRIEF_ID = "brief_playground"
JOB_ID = "job_playground"

STEP_WAIT_S = 60.0
"""Real seconds a step may take: two model calls plus slack. None waits forever
(interactive `--fake`, where you type the model's answer)."""
_POLL_S = 0.01
_SETTLE_ROUNDS = 50

LINE_EVENTS: dict[LineEventName, Callable[[], LineEvent]] = {
    "agency_answered": AgencyAnswered,
    "no_answer": lambda: AgencyUnreachable(reason="no_answer"),
    "agency_hung_up": AgencyHungUp,
    "user_answered": UserAnswered,
    "user_unreachable": lambda: UserUnreachable(reason="no_answer"),
    "user_left": UserLeft,
}


def playground_brief(goal: str | None = None) -> dict[str, Any]:
    """The demo brief, as research writes it; refs stay `<ref:…>` placeholders."""
    brief = demo_brief(CASE_ID, BRIEF_ID)
    if goal:
        brief["call_goal_en"] = goal
    return brief


class CallSession:
    def __init__(
        self,
        llm: TapLlm,
        *,
        goal: str | None = None,
        config: RunnerConfig | None = None,
        step_wait_s: float | None = STEP_WAIT_S,
    ) -> None:
        self.llm = llm
        self.goal = goal
        self.brief = playground_brief(goal)
        self.config = config or RunnerConfig()
        self.step_wait_s = step_wait_s
        self.clock = FakeClock()
        self.started = self.clock.now()
        numbers = FakeNumberSource(
            verified={CASE_ID: "<official number>"},
            users={USER_ID: "<applicant's number>"},
        )
        self.line = FakeTelephony(numbers, self.clock)
        self.relay = ConsoleRelay(self.clock)
        self.log = FakeEventLog()
        self.store = FakeCallStore()
        self.deps = CallDeps(
            # Made-up identifiers, so 1d's line guard is live (C35).
            telephony=GuardedTelephony(self.line, SIM_BLOCKED),
            relay=self.relay,
            cases=FakeCaseReader({BRIEF_ID: self.brief}),
            calls=self.store,
            events=self.log,
            clock=self.clock,
        )
        self.records: list[StepRecord] = []
        self.steps: list[ScriptStep] = []
        self.outcomes: list[Outcome | None] = []
        self.task: asyncio.Task[CallReport] | None = None

    @property
    def state(self) -> CallState:
        return self.records[-1].state_after if self.records else CallState.DIALING

    @property
    def ended(self) -> bool:
        return self.task is not None and self.task.done()

    @property
    def now_s(self) -> float:
        return (self.clock.now() - self.started).total_seconds()

    @property
    def report(self) -> CallReport | None:
        if self.task is None or not self.task.done() or self.task.cancelled():
            return None
        return self.task.result() if self.task.exception() is None else None

    async def start(self) -> Outcome:
        """Place the call: the runner reads the brief and dials."""
        job = CallJob(
            case_id=CASE_ID,
            user_id=USER_ID,
            brief_id=BRIEF_ID,
            user_language="es",
            consent_at=datetime.now(UTC),
            consent_message_id="msg_playground",
            max_hold_minutes=60,
        )
        self.task = asyncio.create_task(
            run_call(
                JOB_ID,
                job,
                self.deps,
                llm=self.llm,
                observer=self.records.append,
                config=self.config,
            )
        )
        await self._until(lambda: any(r.input == "dial" for r in self.records))
        await self._settle()
        return Outcome(records=list(self.records), state=self.state)

    async def run(self, step: ScriptStep) -> Outcome | None:
        """Do one step and wait for the runner to settle. None for control steps."""
        self.llm.step = len(self.steps)
        self.steps.append(step)
        outcome = await self._do(step)
        self.outcomes.append(outcome)
        return outcome

    async def _do(self, step: ScriptStep) -> Outcome | None:
        start = len(self.records)
        match step:
            case PhaseStep():
                self.llm.force_phase = PhaseJudgment(
                    phase=step.phase,
                    confidence=step.confidence,
                    reason_en="Forced in the playground",
                )
                return None
            case FailStep():
                self.llm.fail_next.add(step.kind)
                return None
        if self.ended:
            return self._outcome(start, "the call has ended")
        match step:
            case HeardStep():
                await self._advance(step.after_s)
                await self._push(Heard(text=step.text), start)
                # The line goes quiet while you type the next step, so a held menu
                # answer goes out, as it would on a real line.
                await self._settle()
                await self._advance(self.config.menu_quiet_s)
            case SoundStep():
                await self._advance(step.seconds)
                await self._push(
                    NonSpeech(sound=step.sound, seconds=step.seconds), start
                )
            case LineStep():
                await self._push(LINE_EVENTS[step.event](), start)
            case WaitStep():
                await self._advance(step.seconds)
            case ReplyStep():
                try:
                    self.relay.answer(step.choice)
                except ValueError as exc:
                    return self._outcome(start, str(exc))
                await self._until_input("ask_answered", start)
            case TimeoutStep():
                question = self.relay.open
                if question is None:
                    return self._outcome(start, "no open question to time out")
                left = (question.deadline - self.clock.now()).total_seconds()
                await self._advance(max(left, 0.0))
                await self._until_input("ask_answered", start)
        await self._settle()
        return self._outcome(start)

    def _outcome(self, start: int, note: str | None = None) -> Outcome:
        return Outcome(records=self.records[start:], state=self.state, note=note)

    async def _push(self, event: LineEvent, start: int) -> None:
        self.line.push(event)
        await self._until_input(event.kind, start)

    async def _advance(self, seconds: float) -> None:
        await self.clock.advance(seconds)
        await self._settle()

    async def _until_input(self, kind: str, start: int) -> None:
        await self._until(lambda: any(r.input == kind for r in self.records[start:]))

    async def _until(self, done: Callable[[], bool]) -> None:
        """Wait (real time) until `done`, or the call ended."""
        async with asyncio.timeout(self.step_wait_s):
            while not done() and not self.ended:
                await asyncio.sleep(_POLL_S)

    async def _settle(self) -> None:
        """Let follow-on work finish: woken tasks, then any model call in flight."""
        async with asyncio.timeout(self.step_wait_s):
            while True:
                seen = len(self.records)
                for _ in range(_SETTLE_ROUNDS):
                    await asyncio.sleep(0)
                if self.llm.in_flight == 0 and len(self.records) == seen:
                    return
                await asyncio.sleep(_POLL_S)

    async def close(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    # Recording

    def recorded_model(self) -> dict[tuple[int, ModelKind], Recorded]:
        """Every model answer so far, by step, for undo and `--fake` replay."""
        return {
            (call.step, call.kind): call.recorded()
            for call in self.llm.calls
            if call.step >= 0
        }

    def to_script(self, about: str = "") -> Script:
        """The session as a script; each step's `expect` is what happened, unless it
        already had one (a replayed script keeps its hand-written expectations)."""
        answers = self.recorded_model()
        steps: list[ScriptStep] = []
        for index, (step, outcome) in enumerate(zip(self.steps, self.outcomes)):
            model = {
                kind: recorded
                for (at, kind), recorded in answers.items()
                if at == index
            }
            update: dict[str, Any] = {"model": model}
            if not isinstance(step, CONTROL_STEPS) and outcome is not None:
                update["expect"] = step.expect or expect_from(outcome)
            steps.append(step.model_copy(update=update))
        return Script(about=about, goal=self.goal, steps=steps)


async def rebuild(
    steps: list[ScriptStep],
    llm_factory: Callable[[dict[tuple[int, ModelKind], Recorded], int], TapLlm],
    answers: dict[tuple[int, ModelKind], Recorded],
    *,
    goal: str | None,
    config: RunnerConfig | None,
    step_wait_s: float | None,
) -> CallSession:
    """A fresh call that redoes `steps`, answering from `answers` where it can. Undo
    is this with the last step left out: a live call can't be wound back."""
    llm = llm_factory(answers, len(steps))
    session = CallSession(llm, goal=goal, config=config, step_wait_s=step_wait_s)
    await session.start()
    for step in steps:
        await session.run(step.model_copy(update={"model": {}}))
    return session
