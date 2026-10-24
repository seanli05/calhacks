"""Playground scripts: the steps of a session, what to expect of each, and the check.

A script is JSON (`Script`). Each step is something the line or the family did, or a
playground control (`phase`, `fail`). `/save` writes what happened as each step's
`expect`, and `model` keeps the raw model answers so `--fake` can replay for free.
Expectations are properties, never wording: model output varies run to run. Widen
them by hand: `kind` and `digits` take lists, `say_matches` is a regex on meaning.
"""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts import CallState
from app.phone.menu import AskUserAction, MenuAction, PressAction, SayAction
from app.phone.observe import StepRecord
from app.phone.playground.tap import ModelKind, Recorded

SCRIPTS_DIR = Path(__file__).parent / "scripts"
DEFAULT_GAP_S = 10.0
"""Clock time before each line, unless the line says otherwise (`+90s ›`)."""

type ActionKind = Literal["press", "say", "wait", "ask_user", "none"]
"""`none`: the step led to no menu decision (e.g. the line was read as hold)."""


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: CallState | None = None
    """The call state once the step has settled."""
    kind: list[ActionKind] | None = None
    digits: list[str] | None = None
    """For a press: any of these keys."""
    options: list[str] | None = None
    """For ask_user: the keys offered, in any order."""
    say_matches: str | None = None
    """For a say: a regex (case-insensitive) the text must match."""
    fallback: bool = False
    """Whether a fallback action is expected. Unexpected ones fail."""

    @field_validator("kind", "digits", mode="before")
    @classmethod
    def _one_or_many(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expect: Expect | None = None
    model: dict[ModelKind, Recorded] = Field(default_factory=dict)


class HeardStep(_Step):
    """The line said `text`, `after_s` after the previous step."""

    do: Literal["heard"] = "heard"
    text: str
    after_s: float = DEFAULT_GAP_S


class ReplyStep(_Step):
    """The family answered the open question (1-based)."""

    do: Literal["reply"] = "reply"
    choice: int = Field(ge=1)


class TimeoutStep(_Step):
    """The family never answered: the clock runs to the question's timeout."""

    do: Literal["timeout"] = "timeout"


class WaitStep(_Step):
    do: Literal["wait"] = "wait"
    seconds: float = Field(gt=0)


class SoundStep(_Step):
    """A stretch of music or silence of `seconds` (1d `NonSpeech`)."""

    do: Literal["sound"] = "sound"
    sound: Literal["music", "silence"]
    seconds: float = Field(gt=0)


type LineEventName = Literal[
    "agency_answered",
    "no_answer",
    "agency_hung_up",
    "user_answered",
    "user_unreachable",
    "user_left",
]


class LineStep(_Step):
    """A line event that isn't speech: what Twilio's callbacks report."""

    do: Literal["line"] = "line"
    event: LineEventName


class PhaseStep(_Step):
    """Force the next phase reading from the model (skips Claude for that call)."""

    do: Literal["phase"] = "phase"
    phase: Literal["menu", "hold", "human", "unclear"]
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class FailStep(_Step):
    """Make the next model call of this kind fail, as a timeout would."""

    do: Literal["fail"] = "fail"
    kind: ModelKind


ScriptStep = Annotated[
    HeardStep
    | ReplyStep
    | TimeoutStep
    | WaitStep
    | SoundStep
    | LineStep
    | PhaseStep
    | FailStep,
    Field(discriminator="do"),
]
CONTROL_STEPS = (PhaseStep, FailStep)
"""Steps that only arm the next model call; they have no outcome to check."""


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    about: str = ""
    goal: str | None = None
    """Overrides the brief's `call_goal_en`."""
    steps: list[ScriptStep] = Field(default_factory=list)


def load(path: Path) -> Script:
    return Script.model_validate_json(path.read_text())


def save(script: Script, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script.model_dump_json(indent=2, exclude_none=True) + "\n")


def script_path(name: str) -> Path:
    path = Path(name)
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    return path if path.parent != Path(".") else SCRIPTS_DIR / path


# Outcomes and checks


class Outcome(BaseModel):
    """What one step led to, across every runner step it caused."""

    model_config = ConfigDict(frozen=True)

    records: list[StepRecord]
    state: CallState
    note: str | None = None
    """Why the step couldn't run, e.g. no open question to answer."""

    @property
    def action(self) -> MenuAction | None:
        return next((r.action for r in reversed(self.records) if r.action), None)

    @property
    def kind(self) -> ActionKind:
        action = self.action
        return "none" if action is None else action.kind

    @property
    def flags(self) -> list[str]:
        return [flag for record in self.records for flag in record.flags]


def expect_from(outcome: Outcome) -> Expect:
    """The default expectation `/save` writes: state, kind, and keys."""
    action = outcome.action
    return Expect(
        state=outcome.state,
        kind=[outcome.kind],
        digits=[action.digits] if isinstance(action, PressAction) else None,
        options=(
            sorted(o.digits for o in action.options)
            if isinstance(action, AskUserAction)
            else None
        ),
        fallback=bool(action and action.fallback),
    )


def check(expect: Expect, outcome: Outcome) -> list[str]:
    """What didn't match, as short notes. Empty means pass."""
    problems = []
    if outcome.note:
        problems.append(outcome.note)
    errors = [flag for flag in outcome.flags if flag.startswith("error:")]
    if errors:
        problems.append(", ".join(errors))
    action = outcome.action
    if expect.state is not None and outcome.state != expect.state:
        problems.append(f"state {outcome.state}, expected {expect.state}")
    if expect.kind is not None and outcome.kind not in expect.kind:
        problems.append(f"{outcome.kind}, expected {'/'.join(expect.kind)}")
    if (
        expect.digits is not None
        and isinstance(action, PressAction)
        and action.digits not in expect.digits
    ):
        problems.append(f"keys {action.digits}, expected {'/'.join(expect.digits)}")
    if expect.options is not None and isinstance(action, AskUserAction):
        keys = sorted(o.digits for o in action.options)
        if keys != sorted(expect.options):
            problems.append(f"options {keys}, expected {sorted(expect.options)}")
    if (
        expect.say_matches is not None
        and isinstance(action, SayAction)
        and not re.search(expect.say_matches, action.text, re.IGNORECASE)
    ):
        problems.append(f"say didn't match /{expect.say_matches}/")
    fell_back = bool(action and action.fallback)
    if fell_back != expect.fallback:
        problems.append("fallback" if fell_back else "expected a fallback")
    return problems
