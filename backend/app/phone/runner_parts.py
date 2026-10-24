"""The call runner's parts: its config, the inputs its inbox carries, and timers.

See `runner.py` for how they fit together.
"""

import asyncio
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field

from app.contracts import AskUserReply, EventType
from app.contracts.common import CallState
from app.phone.line import LineEvent
from app.phone.menu import AskUserAction, MenuAction
from app.phone.phase import PhaseReading
from app.phone.ports import Clock
from app.phone.state import Transition


@dataclass(frozen=True)
class RunnerConfig:
    """Policy numbers. First guesses, to tune on real lines (see the spec)."""

    hold_limit_s: float | None = None
    """Overrides the job's `max_hold_minutes`; for the simulator's short holds."""
    ask_timeout_s: int = 30
    ask_reprompts_before_default: int = 2
    """Menu reprompts heard while the applicant decides before the default is taken:
    menus usually hang up after two or three no-inputs."""
    music_to_hold_s: float = 5.0
    """Music this long in a menu means hold, with no model call."""
    user_answer_backstop_s: float = 45.0
    """In case `UserUnreachable` never comes (Twilio's ring timeout is 30 s)."""
    holding_lines_max: int = 2
    holding_line_gap_s: float = 8.0
    menu_budget_s: float = 8 * 60
    """Total time in menus before the agent gives up (AGENT_ABORTED)."""
    escape_limit: int = 3
    """"representative" said this many times in one menu stretch; the next gives up."""
    cleanup_timeout_s: float = 10.0


class MenuGaveUp(Exception):
    """The agent can't get through the menu (budget or escape limit)."""


# Inputs to the inbox


@dataclass(frozen=True)
class LineInput:
    event: LineEvent
    at_s: float
    heard_seq: int = 0
    """For `Heard`: its number in arrival order, to spot a stale decision."""


@dataclass(frozen=True)
class LineEnded:
    at_s: float


@dataclass(frozen=True)
class AskDone:
    token: int
    reply: AskUserReply | None
    """None if the relay raised; the default is taken."""
    at_s: float


@dataclass(frozen=True)
class TimerFired:
    name: str
    token: int
    at_s: float


type Input = LineInput | LineEnded | AskDone | TimerFired


@dataclass
class OpenAsk:
    token: int
    action: AskUserAction
    heard: str
    turn_index: int
    """Its turn in the menu history, replaced by the press once answered."""
    task: asyncio.Task[None]
    reprompts: int = 0


@dataclass
class StepDraft:
    """The step being handled, filled in as it goes; becomes a `StepRecord`."""

    at_s: float
    input: str
    state_before: CallState
    text: str | None = None
    reading: PhaseReading | None = None
    action: MenuAction | None = None
    transitions: list[Transition] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)
    logged: list[EventType] = field(default_factory=list)
    latency_ms: dict[str, int] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


class Timers:
    """Named one-shot timers on the call's clock, each posting `TimerFired`. A
    firing that lost a race with `cancel` or a restart is stale: `take` says no."""

    def __init__(
        self, clock: Clock, inbox: asyncio.Queue[Input], now_s: Callable[[], float]
    ) -> None:
        self._clock = clock
        self._inbox = inbox
        self._now_s = now_s
        self._tokens: dict[str, int] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._seq = itertools.count(1)

    def start(self, name: str, seconds: float) -> None:
        self.cancel(name)
        token = self._tokens[name] = next(self._seq)
        self._tasks[name] = asyncio.create_task(self._run(name, token, seconds))

    def post_now(self, name: str) -> None:
        """Fire `name` on the next loop turn, without waiting."""
        self.cancel(name)
        token = self._tokens[name] = next(self._seq)
        self._inbox.put_nowait(TimerFired(name, token, self._now_s()))

    def cancel(self, name: str) -> None:
        self._tokens.pop(name, None)
        task = self._tasks.pop(name, None)
        if task is not None:
            task.cancel()

    def cancel_all(self) -> None:
        for name in list(self._tokens):
            self.cancel(name)

    def take(self, fired: TimerFired) -> bool:
        if self._tokens.get(fired.name) != fired.token:
            return False
        del self._tokens[fired.name]
        self._tasks.pop(fired.name, None)
        return True

    async def _run(self, name: str, token: int, seconds: float) -> None:
        await self._clock.sleep(seconds)
        self._inbox.put_nowait(TimerFired(name, token, self._now_s()))
