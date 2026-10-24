"""The call report hook (P3). A minimal stand-in until Phase 4's LLM report.

The runner calls a `ReportBuilder` in wrap-up and saves what it returns. This one
uses only the state machine's outcome and the transcript ID; it reads nothing from
the transcript. Swap in the real builder through `run_call(report_builder=...)`.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.contracts import CallOutcome, CallReport
from app.contracts.common import CallId, CaseId, TranscriptId
from app.phone.ports import TranscriptLine
from app.phone.state import Trigger


@dataclass(frozen=True)
class ReportInput:
    call_id: CallId
    case_id: CaseId
    outcome: CallOutcome | None
    """The state machine's outcome; None when the call connected and ended normally
    (resolved vs. partial is the report's call)."""
    cause: Trigger | None
    """The trigger that moved the call into wrap-up."""
    transcript_id: TranscriptId
    transcript: Sequence[TranscriptLine]
    brief: dict[str, Any]
    """Empty if the brief couldn't be read."""


type ReportBuilder = Callable[[ReportInput], Awaitable[CallReport]]

_NEXT_STEPS: dict[Trigger, str] = {
    Trigger.NO_ANSWER: "The agency line didn't answer; try the call again later",
    Trigger.HOLD_TIMEOUT: (
        "The hold passed the time limit; the call can be tried again later"
    ),
    Trigger.AGENCY_HUNG_UP: (
        "The agency ended the call before the applicant joined; try again later"
    ),
    Trigger.AGENT_ABORTED: (
        "The call stopped because of a problem on our side; try again later"
    ),
    Trigger.USER_UNREACHABLE: (
        "The applicant didn't answer; the representative was told they'll call back"
    ),
}


async def build_report(report: ReportInput) -> CallReport:
    """Without reading the conversation it can't claim `resolved`: a connected call
    is `partial` and always needs follow-up. Retries ask for consent again (C21);
    that's the orchestrator's to say."""
    outcome = report.outcome or CallOutcome.PARTIAL
    connected = report.outcome is None
    step = None if connected or report.cause is None else _NEXT_STEPS.get(report.cause)
    return CallReport(
        call_id=report.call_id,
        case_id=report.case_id,
        outcome=outcome,
        next_steps_en=[step] if step else [],
        new_deadlines=[],
        transcript_id=report.transcript_id,
        proposed_facts=[],
        followup_needed=outcome != CallOutcome.RESOLVED,
    )
