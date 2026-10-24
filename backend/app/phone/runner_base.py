"""The call runner's shared state and primitives: logging, the classifier call, the
transcript, and the observer. `runner_menu.MenuSteps` and `runner._CallRunner`
build on it; see `runner.py` for the whole picture.
"""

import asyncio
import itertools
import logging
import time
from collections.abc import Awaitable
from typing import Any, Literal

from app.contracts import CallJob, EventType
from app.contracts.common import CallId, CallState, JobId
from app.phone import phase
from app.phone.call_events import CallEvents
from app.phone.executor import MenuExecutor, Sent
from app.phone.line import Heard, NonSpeech
from app.phone.llm import LlmClient
from app.phone.menu import MenuTurn
from app.phone.observe import Observer, StepRecord
from app.phone.phase import HeardTurn, PhaseReading
from app.phone.ports import CallDeps, LineClosed, TranscriptLine
from app.phone.report import ReportBuilder
from app.phone.runner_parts import (
    AskDone,
    Input,
    LineEnded,
    LineInput,
    OpenAsk,
    RunnerConfig,
    StepDraft,
    TimerFired,
    Timers,
)
from app.phone.state import CallStateMachine, Trigger

logger = logging.getLogger("app.phone.runner")

S = CallState


class RunnerBase:
    """One call's runner state. Subclasses add the handlers."""

    def __init__(
        self,
        job_id: JobId,
        job: CallJob,
        deps: CallDeps,
        llm: LlmClient | None,
        observer: Observer | None,
        config: RunnerConfig,
        report_builder: ReportBuilder,
    ) -> None:
        self.job_id = job_id
        self.job = job
        self.deps = deps
        self.clock = deps.clock
        self.llm = llm
        self.observer = observer
        self.config = config
        self.report_builder = report_builder

        self.started = self.clock.now()
        self.sm = CallStateMachine()
        self.call_id: CallId = ""
        self.events = CallEvents(
            deps.events, deps.clock, job.user_id, job.case_id, job_id
        )
        self.brief: dict[str, Any] = {}
        self.inbox: asyncio.Queue[Input] = asyncio.Queue()
        self.timers = Timers(self.clock, self.inbox, self.now_s)
        self.executor = MenuExecutor(deps.telephony)
        self.pump: asyncio.Task[None] | None = None
        self.step = StepDraft(0.0, "start", S.DIALING)

        self.transcript: list[TranscriptLine] = []
        self.heard_history: list[HeardTurn] = []
        self.menu_history: list[MenuTurn] = []
        self.menu_buffer: list[str] = []
        """Menu speech since the last decision that was used, so a prompt that
        speech-to-text split in pieces is decided as a whole."""
        self.heard_arrived = 0
        self.state_since_s = 0.0
        self.passive = False
        """After a crash with the applicant on: only watch for the end."""
        self.error: str | None = None

        self.ask: OpenAsk | None = None
        self._ask_seq = itertools.count(1)
        self._dropped: list[asyncio.Task[None]] = []
        self.menu_entered_s = 0.0
        self.menu_spent_s = 0.0
        self.escapes = 0
        self.blocked_streak = 0
        self.hold_started = False
        self.hold_overdue = False
        self.holding_said = 0
        self.last_holding_s: float | None = None

    def now_s(self) -> float:
        return (self.clock.now() - self.started).total_seconds()

    async def _classify(self, text: str, at_s: float) -> PhaseReading:
        reading = await self._timed(
            "classify",
            phase.classify(
                text,
                at_s=at_s,
                state=self.sm.state,
                history=self.heard_history,
                state_since_s=self.state_since_s,
                client=self.llm,
                call_id=self.call_id,
            ),
        )
        self.heard_history.append(HeardTurn(text=text, at_s=at_s, phase=reading.phase))
        self.step.reading = reading
        return reading

    async def _discard(self, task: asyncio.Future[Any]) -> None:
        """Cancel a model call whose answer is no longer wanted, and wait for it."""
        if not task.done():
            task.cancel()
        [result] = await asyncio.gather(task, return_exceptions=True)
        if isinstance(result, Exception):
            logger.warning(
                "discarded model call had failed (%s): %s",
                self._ids(),
                type(result).__name__,
            )

    async def _timed[T](self, name: str, awaitable: Awaitable[T]) -> T:
        """Real time per model call, for the observer; not a wait (that's `clock`)."""
        start = time.perf_counter()
        try:
            return await awaitable
        finally:
            self.step.latency_ms[name] = round((time.perf_counter() - start) * 1000)

    async def _say_line(self, text: str) -> bool:
        """A fixed line to the representative. False if the line had closed."""
        try:
            await self.deps.telephony.say(text)
        except LineClosed:
            self.step.flags.append("line_closed")
            return False
        self._sent(Sent("speech", text))
        return True

    async def _log(self, event_type: EventType, summary_en: str, **data: Any) -> None:
        """IDs and short fields only; never what was heard or said (C27)."""
        self.step.logged.append(event_type)
        await self.events.append(event_type, summary_en, **data)

    def _said(self, speaker: Literal["agent", "agency"], text: str) -> None:
        self.transcript.append(
            TranscriptLine(at=self.clock.now(), speaker=speaker, text=text)
        )

    def _sent(self, sent: Sent) -> None:
        self._said("agent", sent.out)
        self.step.sent.append(f"{sent.via}: {sent.out}")

    def _ids(self) -> str:
        return f"call_id={self.call_id} case_id={self.job.case_id} job_id={self.job_id}"

    def _begin(self, input_kind: str, text: str | None = None) -> None:
        self.step = StepDraft(self.now_s(), input_kind, self.sm.state, text)

    def _begin_for(self, item: Input) -> None:
        match item:
            case LineInput(event=Heard(text=text)):
                self._begin("heard", text)
            case LineInput(event=NonSpeech(sound=sound, seconds=seconds)):
                self._begin("non_speech", f"{sound} {seconds:.0f} s")
            case LineInput(event=event):
                self._begin(event.kind)
            case LineEnded():
                self._begin("line_ended")
            case AskDone():
                self._begin("ask_answered")
            case TimerFired(name=name):
                self._begin(f"timer:{name}")
        self.step.at_s = item.at_s

    def _emit(self) -> None:
        if self.observer is None:
            return
        step = self.step
        record = StepRecord(
            at_s=round(step.at_s, 2),
            input=step.input,
            text=step.text,
            state_before=step.state_before,
            state_after=self.sm.state,
            reading=step.reading,
            action=step.action,
            transitions=step.transitions,
            sent=step.sent,
            logged=step.logged,
            latency_ms=step.latency_ms,
            flags=step.flags,
        )
        try:
            self.observer(record)
        except Exception:
            logger.exception("observer failed (%s)", self._ids())

    async def _fire_reading(self, trigger: Trigger, reading: PhaseReading) -> None:
        """Fire a trigger a phase reading gave (the runner implements it)."""
        raise NotImplementedError
