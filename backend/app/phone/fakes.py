"""In-memory fakes of every port, for tests and the call simulator. Never wired
into the running app.

They keep the rules the real side enforces (an unverified case can't be dialed,
a call needs a consent message, an unknown call raises `NotFound`) and record
everything asked of them, so tests can assert on it.
"""

import asyncio
import heapq
import itertools
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.contracts import (
    AskUserReply,
    AskUserRequest,
    CallJob,
    CallReport,
    Event,
    EventType,
)
from app.contracts.common import (
    BriefId,
    CallId,
    CallState,
    CaseId,
    JobId,
    QuestionId,
    TranscriptId,
    UserId,
)
from app.db.errors import NotFound, UnverifiedNumber
from app.db.ids import new_id
from app.phone.line import AgencyHungUp, AgencyUnreachable, LineEvent
from app.phone.ports import Clock, LineClosed, NumberSource, TranscriptLine

_SETTLE_ROUNDS = 20
"""Loop turns given to woken tasks before the clock moves again. Enough for the
short await chains here; a runner that needs more is doing too much per step."""

# Clock


class FakeClock:
    """Virtual time. Nothing moves until `advance` or `run` moves it."""

    def __init__(self, start: datetime = datetime(2026, 10, 25, 10, 0, tzinfo=UTC)):
        self._now = start
        self._sleepers: list[tuple[datetime, int, asyncio.Future[None]]] = []
        self._seq = itertools.count()

    def now(self) -> datetime:
        return self._now

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        deadline = self._now + timedelta(seconds=seconds)
        heapq.heappush(self._sleepers, (deadline, next(self._seq), future))
        await future

    def _next_deadline(self) -> datetime | None:
        while self._sleepers and self._sleepers[0][2].done():
            heapq.heappop(self._sleepers)  # its sleeper was cancelled
        return self._sleepers[0][0] if self._sleepers else None

    async def advance(self, seconds: float) -> None:
        """Move time forward, waking each sleeper at its own deadline, in order."""
        target = self._now + timedelta(seconds=seconds)
        await _settle()
        while (deadline := self._next_deadline()) is not None and deadline <= target:
            _, _, future = heapq.heappop(self._sleepers)
            self._now = deadline
            future.set_result(None)
            await _settle()
        self._now = target

    async def run[T](self, awaitable: Awaitable[T]) -> T:
        """Run to completion, jumping to the next deadline whenever everything is
        waiting. Raises `RuntimeError` if it's stuck with nothing scheduled."""
        task = asyncio.ensure_future(awaitable)
        while True:
            await _settle()
            if task.done():
                return task.result()
            deadline = self._next_deadline()
            if deadline is None:
                task.cancel()
                raise RuntimeError("stuck: still waiting, and nothing is scheduled")
            await self.advance((deadline - self._now).total_seconds())


async def _settle() -> None:
    for _ in range(_SETTLE_ROUNDS):
        await asyncio.sleep(0)


# Numbers, cases, calls, events


class FakeNumberSource:
    def __init__(
        self,
        verified: dict[CaseId, str] | None = None,
        users: dict[UserId, str] | None = None,
    ) -> None:
        """`verified`: the official number of each verified case; any other case
        is unverified."""
        self.verified = verified or {}
        self.users = users or {}

    async def official_dial_number(self, case_id: CaseId) -> str:
        if case_id not in self.verified:
            raise UnverifiedNumber(f"case {case_id} is not verified")
        return self.verified[case_id]

    async def user_number(self, user_id: UserId) -> str:
        if user_id not in self.users:
            raise NotFound(f"users {user_id} not found")
        return self.users[user_id]


class FakeCaseReader:
    def __init__(self, briefs: dict[BriefId, dict[str, Any]] | None = None) -> None:
        self.briefs = briefs or {}

    async def get_brief(self, brief_id: BriefId) -> dict[str, Any]:
        if brief_id not in self.briefs:
            raise NotFound(f"case_briefs {brief_id} not found")
        return self.briefs[brief_id]


@dataclass
class FakeCall:
    call_id: CallId
    job_id: JobId
    job: CallJob
    states: list[CallState] = field(default_factory=lambda: [CallState.DIALING])
    twilio_call_sid: str | None = None
    transcript: list[TranscriptLine] = field(default_factory=list)
    transcript_id: TranscriptId | None = None
    report: CallReport | None = None

    @property
    def state(self) -> CallState:
        return self.states[-1]


class FakeCallStore:
    def __init__(self) -> None:
        self.calls: dict[CallId, FakeCall] = {}

    def _get(self, call_id: CallId) -> FakeCall:
        if call_id not in self.calls:
            raise NotFound(f"calls {call_id} not found")
        return self.calls[call_id]

    async def create_call(self, job_id: JobId, job: CallJob) -> CallId:
        if not job.consent_message_id:
            raise ValueError("a call needs the user's consent message (rule 4)")
        call_id = new_id("call")
        self.calls[call_id] = FakeCall(call_id, job_id, job)
        return call_id

    async def set_state(
        self, call_id: CallId, state: CallState, twilio_call_sid: str | None = None
    ) -> None:
        call = self._get(call_id)
        call.states.append(state)
        if twilio_call_sid is not None:
            call.twilio_call_sid = twilio_call_sid

    async def save_transcript(
        self, call_id: CallId, lines: Sequence[TranscriptLine]
    ) -> TranscriptId:
        call = self._get(call_id)
        call.transcript = list(lines)
        call.transcript_id = call.transcript_id or new_id("transcript")
        return call.transcript_id

    async def save_report(self, call_id: CallId, report: CallReport) -> None:
        self._get(call_id).report = report


class FakeEventLog:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def append(self, event: Event) -> None:
        self.events.append(event)

    @property
    def types(self) -> list[EventType]:
        return [event.type for event in self.events]


# Relay


@dataclass(frozen=True)
class Answer:
    """The user replies `choice` after `after_s`; past the timeout it counts as none."""

    choice: int
    after_s: float = 5.0


@dataclass(frozen=True)
class NoAnswer:
    """The user never replies; the relay takes the default at the timeout."""


class FakeRelay:
    """Replies come from `replies` in order, then `NoAnswer` once they run out."""

    def __init__(self, clock: Clock, replies: Iterable[Answer | NoAnswer] = ()) -> None:
        self._clock = clock
        self._replies = deque(replies)
        self.asked: list[AskUserRequest] = []
        self.cancelled: list[QuestionId] = []

    async def ask_user(self, request: AskUserRequest) -> AskUserReply:
        self.asked.append(request)
        reply = self._replies.popleft() if self._replies else NoAnswer()
        try:
            if isinstance(reply, Answer) and reply.after_s < request.timeout_s:
                if not 1 <= reply.choice <= len(request.options_en):
                    raise ValueError(f"scripted choice {reply.choice} is out of range")
                await self._clock.sleep(reply.after_s)
                return AskUserReply(
                    question_id=request.question_id, choice=reply.choice
                )
            await self._clock.sleep(request.timeout_s)
        except asyncio.CancelledError:
            self.cancelled.append(request.question_id)
            raise
        return AskUserReply(
            question_id=request.question_id, choice=request.default_option
        )


# Telephony


@dataclass(frozen=True)
class Step:
    """A scripted line event, `after_s` after the step before it (or the action)."""

    after_s: float
    event: LineEvent


@dataclass(frozen=True)
class Dialed:
    call_id: CallId
    case_id: CaseId
    number: str


@dataclass(frozen=True)
class Said:
    text: str


@dataclass(frozen=True)
class PressedKeys:
    digits: str


@dataclass(frozen=True)
class RangUser:
    call_id: CallId
    user_id: UserId
    number: str


@dataclass(frozen=True)
class ConnectedUser:
    pass


@dataclass(frozen=True)
class RangListener:
    call_id: CallId
    user_id: UserId
    number: str


@dataclass(frozen=True)
class HungUp:
    pass


type Action = (
    Dialed | Said | PressedKeys | RangUser | ConnectedUser | RangListener | HungUp
)
type Responder = Callable[[Action], Iterable[Step]]


class FakeTelephony:
    """A scripted line. `script` plays after `dial_agency`. `responder`, if given,
    sees every action and returns the steps that follow it; that's how the
    simulator plugs in a phone tree. `push` injects an event directly.
    `say_s_per_word` makes `say` take that long per word on the clock, as speech
    does on a real line; by default it returns at once."""

    def __init__(
        self,
        numbers: NumberSource,
        clock: Clock,
        script: Iterable[Step] = (),
        responder: Responder | None = None,
        *,
        say_s_per_word: float = 0.0,
    ) -> None:
        self._numbers = numbers
        self._clock = clock
        self._script = list(script)
        self._responder = responder
        self._say_s_per_word = say_s_per_word
        self._queue: asyncio.Queue[LineEvent | None] = asyncio.Queue()
        self._tasks: set[asyncio.Task[None]] = set()
        self._dialed = False
        self._hung_up = False
        self._agency_gone = False
        self.actions: list[Action] = []

    async def dial_agency(self, call_id: CallId, case_id: CaseId) -> str:
        if self._dialed:
            raise RuntimeError("this line already dialed")
        number = await self._numbers.official_dial_number(case_id)
        self._dialed = True
        self._act(Dialed(call_id, case_id, number), self._script)
        return f"CA{call_id}"

    async def say(self, text: str) -> None:
        self._require_agency()
        self._act(Said(text))
        if self._say_s_per_word:
            await self._clock.sleep(len(text.split()) * self._say_s_per_word)

    async def press_keys(self, digits: str) -> None:
        self._require_agency()
        self._act(PressedKeys(digits))

    async def ring_user(self, call_id: CallId, user_id: UserId) -> None:
        self._require_agency()
        number = await self._numbers.user_number(user_id)
        self._act(RangUser(call_id, user_id, number))

    async def connect_user(self) -> None:
        self._require_agency()
        self._act(ConnectedUser())

    async def listen_in(self, call_id: CallId, user_id: UserId) -> None:
        self._require_agency()
        number = await self._numbers.user_number(user_id)
        self._act(RangListener(call_id, user_id, number))

    async def hang_up(self) -> None:
        if self._hung_up:
            return
        self._hung_up = True
        self.actions.append(HungUp())
        for task in list(self._tasks):
            task.cancel()
        self._queue.put_nowait(None)

    async def events(self) -> AsyncIterator[LineEvent]:
        while (event := await self._queue.get()) is not None:
            yield event

    def push(self, event: LineEvent) -> None:
        if isinstance(event, AgencyHungUp | AgencyUnreachable):
            self._agency_gone = True
        self._queue.put_nowait(event)

    def _require_agency(self) -> None:
        if not self._dialed:
            raise RuntimeError("dial the agency first")
        if self._hung_up or self._agency_gone:
            raise LineClosed("the agency leg has ended")

    def _act(self, action: Action, steps: Iterable[Step] = ()) -> None:
        self.actions.append(action)
        follow = [*steps, *(self._responder(action) if self._responder else ())]
        if follow:
            task = asyncio.create_task(self._play(follow))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _play(self, steps: list[Step]) -> None:
        for step in steps:
            await self._clock.sleep(step.after_s)
            self.push(step.event)
