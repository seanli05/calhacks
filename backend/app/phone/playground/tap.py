"""The playground's two hooks into the runner: a Claude wrapper and a console relay.

`TapLlm` sits between the runner and the real (or fake) model. It records each call's
prompt and raw answer, so the playground can show the exact prompt and why the guard
rejected an answer, and it can fail or force the next call (`/fail`, `/phase`). On
undo and in fake replay it answers from recorded outputs instead of calling Claude.

`ConsoleRelay` is P1 with the console as the family: a question stays open while the
line keeps talking, and the REPL answers it, or the fake clock times it out.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import pydantic
from pydantic import BaseModel

from app.contracts import AskUserReply, AskUserRequest
from app.phone.clock import with_timeout
from app.phone.llm import LlmClient, LlmError
from app.phone.menu import (
    AskUserAction,
    AskUserOption,
    MenuAction,
    MenuDecision,
    PressAction,
    SayAction,
    WaitAction,
)
from app.phone.phase import PhaseJudgment
from app.phone.ports import Clock

type ModelKind = Literal["phase", "menu"]
type CallSource = Literal["model", "forced", "failed", "recorded", "you", "fake"]


class Recorded(BaseModel):
    """One model answer as saved in a script: the raw output, or the error."""

    output: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ModelCall:
    step: int
    kind: ModelKind
    system: str
    user: str
    source: CallSource
    ms: int
    output: BaseModel | None = None
    error: str | None = None

    def recorded(self) -> Recorded:
        if self.output is None:
            return Recorded(error=self.error or "failed")
        return Recorded(output=self.output.model_dump(mode="json"))


type TypedModel = Callable[[str], Awaitable[MenuDecision | None]]
"""Interactive `--fake`: asks you for the menu action; None means fail the call."""


class TapLlm:
    """`LlmClient` that records and steers. `inner` None means no real model: phase
    calls fail (1c falls back to its cues) and menu calls go to `typed`, if given."""

    def __init__(
        self,
        inner: LlmClient | None,
        *,
        typed: TypedModel | None = None,
        cassette: dict[tuple[int, ModelKind], Recorded] | None = None,
        cassette_until: int = 0,
    ) -> None:
        self._inner = inner
        self._typed = typed
        self._cassette = cassette or {}
        self._cassette_until = cassette_until
        self.step = -1
        self.force_phase: PhaseJudgment | None = None
        self.fail_next: set[ModelKind] = set()
        self.calls: list[ModelCall] = []
        self.in_flight = 0

    async def parse[T: pydantic.BaseModel](
        self, *, system: str, user: str, output_type: type[T], timeout_s: float
    ) -> T:
        kind: ModelKind = "phase" if output_type is PhaseJudgment else "menu"
        step = self.step
        start = time.perf_counter()
        self.in_flight += 1
        try:
            # A real call always yields; recorded and fake answers should too, so the
            # runner's parallel 1b call starts before a 1c reading can discard it.
            await asyncio.sleep(0)
            source, output = await self._answer(kind, step, system, user, output_type)
        except LlmError as exc:
            self._record(
                step, kind, system, user, source_for(exc), start, error=str(exc)
            )
            raise
        finally:
            self.in_flight -= 1
        self._record(step, kind, system, user, source, start, output=output)
        assert isinstance(output, output_type)
        return output

    async def _answer(
        self,
        kind: ModelKind,
        step: int,
        system: str,
        user: str,
        output_type: type[BaseModel],
    ) -> tuple[CallSource, BaseModel]:
        # Injections come first, so a replayed `/fail` or `/phase` lands on the same call.
        if kind in self.fail_next:
            self.fail_next.discard(kind)
            raise _Injected("failed on purpose (/fail)")
        if kind == "phase" and self.force_phase is not None:
            forced, self.force_phase = self.force_phase, None
            return "forced", forced
        recorded = self._cassette.get((step, kind))
        if recorded is not None:
            if recorded.output is None:
                raise _Replayed(recorded.error or "recorded failure")
            return "recorded", output_type.model_validate(recorded.output)
        if step < self._cassette_until:
            # A call the recording never finished (the runner discarded it).
            raise _Replayed("no recorded answer")
        if self._inner is not None:
            parsed = await self._inner.parse(
                system=system, user=user, output_type=output_type, timeout_s=_TIMEOUT
            )
            return "model", parsed
        if kind == "menu" and self._typed is not None:
            decision = await self._typed(user)
            if decision is None:
                raise _Injected("you failed the call")
            return "you", decision
        raise _Fake("no model in --fake mode")

    def _record(
        self,
        step: int,
        kind: ModelKind,
        system: str,
        user: str,
        source: CallSource,
        start: float,
        *,
        output: BaseModel | None = None,
        error: str | None = None,
    ) -> None:
        ms = round((time.perf_counter() - start) * 1000)
        self.calls.append(
            ModelCall(step, kind, system, user, source, ms, output, error)
        )

    def for_step(self, step: int) -> list[ModelCall]:
        return [call for call in self.calls if call.step == step]

    def last(self, kind: ModelKind) -> ModelCall | None:
        return next((c for c in reversed(self.calls) if c.kind == kind), None)


_TIMEOUT = 30.0
"""The runner's own timeouts (`DECIDE_TIMEOUT_S`, `CLASSIFY_TIMEOUT_S`) wrap this call."""


class _Injected(LlmError):
    pass


class _Replayed(LlmError):
    pass


class _Fake(LlmError):
    pass


def source_for(exc: LlmError) -> CallSource:
    match exc:
        case _Replayed():
            return "recorded"
        case _Fake():
            return "fake"
        case _Injected():
            return "failed"
    return "model"


# Interactive --fake: you are the model.

TYPED_HELP = (
    "p <keys> <label>  |  s <text>  |  w  |  "
    "a <default> | <keys>=<label> | <keys>=<label>  |  x (fail the call)"
)


def parse_typed_action(text: str) -> MenuAction | None:
    """Your answer as the model, e.g. `p 4 appointments`. None means fail the call.
    Raises ValueError with a hint when it doesn't parse."""
    text = text.strip()
    head, _, rest = text.partition(" ")
    rest = rest.strip()
    reason = "Typed in the playground"
    match head.lower():
        case "" | "w":
            return WaitAction(kind="wait", reason_en=reason)
        case "x":
            return None
        case "s" if rest:
            return SayAction(kind="say", text=rest, reason_en=reason)
        case "p" if rest:
            keys, _, label = rest.partition(" ")
            return PressAction(
                kind="press",
                digits=keys,
                option_label_en=label.strip() or keys,
                reason_en=reason,
            )
        case "a" if "|" in rest:
            default, *choices = (part.strip() for part in rest.split("|"))
            options = []
            for choice in choices:
                keys, sep, label = choice.partition("=")
                if not sep:
                    raise ValueError("each option is <keys>=<label>")
                options.append(
                    AskUserOption(label_en=label.strip(), digits=keys.strip())
                )
            return AskUserAction(
                kind="ask_user",
                question_en="Typed in the playground",
                options=options,
                default_option=int(default),
                reason_en=reason,
            )
    raise ValueError(TYPED_HELP)


# The relay


@dataclass
class OpenQuestion:
    request: AskUserRequest
    deadline: datetime
    reply: asyncio.Future[int]


class ConsoleRelay:
    """P1 for the playground. On a timeout the reply carries the default, as the real
    relay does; when the runner drops the question, the wait is cancelled."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self.open: OpenQuestion | None = None
        self.asked: list[AskUserRequest] = []
        self.timed_out: list[str] = []

    async def ask_user(self, request: AskUserRequest) -> AskUserReply:
        self.asked.append(request)
        reply = asyncio.get_running_loop().create_future()
        deadline = self._clock.now() + timedelta(seconds=request.timeout_s)
        self.open = OpenQuestion(request, deadline, reply)
        try:
            choice = await with_timeout(self._clock, reply, request.timeout_s)
        except TimeoutError:
            self.timed_out.append(request.question_id)
            choice = request.default_option
        finally:
            self.open = None
        return AskUserReply(question_id=request.question_id, choice=choice)

    def answer(self, choice: int) -> None:
        """Raises ValueError if nothing is open or the choice is out of range."""
        if self.open is None:
            raise ValueError("no open question (answered, timed out, or dropped)")
        options = len(self.open.request.options_en)
        if not 1 <= choice <= options:
            raise ValueError(f"choose 1-{options}")
        if not self.open.reply.done():
            self.open.reply.set_result(choice)
