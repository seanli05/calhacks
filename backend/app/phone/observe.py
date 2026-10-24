"""What the runner reports about each step, for the simulator, the playground, and
debugging. Local only: a `StepRecord` carries what was heard and said, so it never
goes to `events` or the logs (events carry IDs and short fields, C27)."""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from app.contracts import CallState, EventType
from app.phone.menu import MenuAction
from app.phone.phase import PhaseReading
from app.phone.state import Transition


class StepRecord(BaseModel):
    """One input the runner handled (a line event, the applicant's answer, a timer),
    plus the dial and the wrap-up, with everything it led to."""

    model_config = ConfigDict(frozen=True)

    at_s: float
    """Seconds since the runner started, when the input arrived."""
    input: str
    """`heard`, `non_speech`, `agency_answered`, …, `ask_answered`, `timer:<name>`,
    `dial`, `wrap_up`, or `error`."""
    text: str | None = None
    """What the agency said, or a short description of a non-speech input."""
    state_before: CallState
    state_after: CallState
    reading: PhaseReading | None = None
    action: MenuAction | None = None
    transitions: list[Transition] = Field(default_factory=list)
    sent: list[str] = Field(default_factory=list)
    """What went out on the line, e.g. `speech: two`, `keys: 2`."""
    logged: list[EventType] = Field(default_factory=list)
    latency_ms: dict[str, int] = Field(default_factory=dict)
    """Real time per model call (`classify`, `decide`), even on a fake clock."""
    flags: list[str] = Field(default_factory=list)
    """Guard, fallback, and policy notes: `blocked`, `fallback`, `stale_dropped`,
    `keypad_mode`, `ask_default_early`, `line_closed`, `ignored`, …"""


type Observer = Callable[[StepRecord], None]
"""Called once per step, synchronously. Keep it fast; an observer that raises is
logged and skipped, never allowed to break the call."""
