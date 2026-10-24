"""The call report (P3): what the call established, built in wrap-up.

The runner calls a `ReportBuilder` in wrap-up and saves what it returns. Two live
here:

- `build_report`: deterministic, from the state machine's outcome alone. It's the
  runner's default and the answer for every call that never reached a person
  (no answer, hold timeout, hang-up, abort, applicant unreachable), so those need
  no model call.
- `LlmReportBuilder`: for calls that connected, one Claude call over the
  transcript. Code, not the model, owns the outcome of unconnected calls, the
  fact source and sensitivity, and the checks below. Any failure falls back to
  `build_report`, so a report is always saved.

Checks on the model's draft (C34, C35, and no invented details): the reference
number and rep name must appear in the transcript; anything that looks like a
receipt number or A-Number, or carries one of the case's identifier values, is
dropped; deadlines must parse and fall after the call.
"""

import datetime as dt
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.contracts import (
    CallOutcome,
    CallReport,
    FactSource,
    ProposedFact,
    Sensitivity,
)
from app.contracts.common import CallId, CaseId, TranscriptId
from app.phone.guard import spoken_digits
from app.phone.llm import LlmClient, LlmError
from app.phone.ports import TranscriptLine
from app.phone.report_prompts import REPORT_SYSTEM
from app.phone.state import Trigger

logger = logging.getLogger(__name__)

REPORT_TIMEOUT_S = 45.0
"""The applicant is off the call and waiting for the summary, but nothing else is
blocked; a report usually takes a few seconds."""

MAX_ITEMS = 5
MAX_DEADLINE_DAYS = 2 * 365
TRANSCRIPT_CHARS = 60_000
"""Kept from the end: the representative comes last, the hold first."""
_HEAD_CHARS = 8_000

_RECEIPT = re.compile(r"\b[a-z]{3}[\s-]*\d(?:[\s-]*\d){9}\b", re.IGNORECASE)
_A_NUMBER = re.compile(r"\ba[\s-]*\d(?:[\s-]*\d){7,8}\b", re.IGNORECASE)
_MIN_REF_DIGITS = 4
"""Fewer spoken digits could match by chance anywhere in a long transcript."""


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


class ReportDraft(BaseModel):
    """What the model fills in; code turns it into a `CallReport`. `summary_en`
    comes first so the model sums up before it fills the fields; `CallReport` has
    no place for it, so only the eval reads it."""

    summary_en: str = Field(description="Two or three sentences on how the call went.")
    outcome: Literal["resolved", "partial", "failed"]
    reference_number: str | None = Field(
        description="A confirmation number the representative gave, or null."
    )
    rep_name: str | None = Field(description="The representative's name, or null.")
    next_steps_en: list[str] = Field(description="At most five short sentences.")
    new_deadlines: list[str] = Field(description="Dates as YYYY-MM-DD.")
    proposed_facts: list[str] = Field(description="At most five short facts.")
    followup_needed: bool


class LlmReportBuilder:
    """A `ReportBuilder` that reads the transcript with Claude. One per call:
    `blocked_values` are the case's identifier values (`adapters.load_blocked_values`)
    and never leave this object."""

    def __init__(
        self,
        client: LlmClient,
        *,
        blocked_values: Sequence[str] = (),
        timeout_s: float = REPORT_TIMEOUT_S,
    ) -> None:
        self._client = client
        self._blocked = [_alnum(v) for v in blocked_values if _alnum(v)]
        self._timeout_s = timeout_s
        self.last_draft: ReportDraft | None = None
        """For the eval. Carries call content; never log it."""

    async def __call__(self, report: ReportInput) -> CallReport:
        fallback = await build_report(report)
        if report.outcome is not None:
            return fallback
        if not any(line.speaker != "agent" for line in report.transcript):
            logger.warning(
                "connected call with nothing heard; deterministic report (%s)",
                _ids(report),
            )
            return fallback
        try:
            draft = await self._client.parse(
                system=REPORT_SYSTEM,
                user=report_prompt(report),
                output_type=ReportDraft,
                timeout_s=self._timeout_s,
            )
            self.last_draft = draft
            return self._from_draft(report, draft)
        except (LlmError, ValidationError) as exc:
            logger.warning(
                "call report fell back to deterministic (%s): %s",
                _ids(report),
                type(exc).__name__,
            )
        except Exception:
            # The report must always be saved; a bug here mustn't lose it.
            logger.exception(
                "call report failed unexpectedly; deterministic (%s)", _ids(report)
            )
        return fallback

    def _from_draft(self, report: ReportInput, draft: ReportDraft) -> CallReport:
        heard = _heard_text(report.transcript)
        outcome = CallOutcome(draft.outcome)
        facts = [
            ProposedFact(
                fact=fact,
                source=FactSource.FROM_CALL,
                # Everything a call to an immigration agency confirms is an
                # immigration fact, held until the applicant agrees (C15, C25).
                sensitivity=Sensitivity.SENSITIVE,
            )
            for fact in self._keep(draft.proposed_facts)
        ]
        return CallReport(
            call_id=report.call_id,
            case_id=report.case_id,
            outcome=outcome,
            reference_number=self._reference(draft.reference_number, heard),
            rep_name=_rep_name(draft.rep_name, heard),
            next_steps_en=self._keep(draft.next_steps_en),
            new_deadlines=_deadlines(draft.new_deadlines, _call_date(report)),
            transcript_id=report.transcript_id,
            proposed_facts=facts,
            followup_needed=draft.followup_needed or outcome != CallOutcome.RESOLVED,
        )

    def _keep(self, items: Sequence[str]) -> list[str]:
        kept = [item.strip() for item in items if item.strip()]
        return [item for item in kept if not self._identifier(item)][:MAX_ITEMS]

    def _identifier(self, text: str) -> bool:
        """True if `text` carries an identifier (C34, C35)."""
        if _RECEIPT.search(text) or _A_NUMBER.search(text):
            return True
        flat = _alnum(text)
        return any(value in flat for value in self._blocked)

    def _reference(self, value: str | None, heard: str) -> str | None:
        value = (value or "").strip()
        if not value or self._identifier(value):
            return None
        flat = _alnum(value)
        if flat and flat in _alnum(heard):
            return value
        # Read out digit by digit ("R five five eight two one"): match the digits.
        digits = spoken_digits(value)
        if len(digits) >= _MIN_REF_DIGITS and digits in spoken_digits(heard):
            return value
        return None


def report_prompt(report: ReportInput) -> str:
    """The user message: the call goal and dates from the brief, how the call ended,
    the call date, and the transcript. Refs stay placeholders; nothing is resolved."""
    brief = report.brief
    lines = [f"Call goal: {brief.get('call_goal_en') or 'Not given'}"]
    appointment = brief.get("appointment")
    if isinstance(appointment, dict) and appointment.get("date"):
        when = str(appointment["date"])
        if appointment.get("time"):
            when += f" at {appointment['time']}"
        lines.append(f"Appointment on the notice: {when}")
    if brief.get("deadline"):
        lines.append(f"Deadline on the notice: {brief['deadline']}")
    questions = [q for q in brief.get("questions_to_ask") or [] if isinstance(q, str)]
    if questions:
        lines.append("Questions the applicant wanted answered:")
        lines.extend(f"- {q}" for q in questions)
    call_date = _call_date(report)
    if call_date:
        lines.append(f"Call date: {call_date.isoformat()}")
    lines.append(f"How the call ended: {_ending(report.cause)}")
    lines.append("")
    lines.append("Transcript:")
    lines.append(format_transcript(report.transcript))
    return "\n".join(lines)


def format_transcript(transcript: Sequence[TranscriptLine]) -> str:
    """One line per turn, minutes from the start. Runs of the same line (a hold
    message every 30 s) collapse into one, and a long call keeps its start and its
    end, where the representative is."""
    if not transcript:
        return "(empty)"
    start = transcript[0].at
    rows: list[str] = []
    previous: tuple[str, str] | None = None
    repeats = 0
    for line in transcript:
        key = (line.speaker, _alnum(line.text))
        if key == previous:
            repeats += 1
            continue
        if repeats:
            rows[-1] += f" (repeated {repeats + 1} times)"
        repeats = 0
        previous = key
        offset = int((line.at - start).total_seconds())
        rows.append(
            f"[{offset // 60:02d}:{offset % 60:02d}] {line.speaker.upper()}: "
            f"{line.text.strip()}"
        )
    if repeats:
        rows[-1] += f" (repeated {repeats + 1} times)"
    text = "\n".join(rows)
    if len(text) <= TRANSCRIPT_CHARS:
        return text
    tail = TRANSCRIPT_CHARS - _HEAD_CHARS
    return f"{text[:_HEAD_CHARS]}\n[… middle of the call cut …]\n{text[-tail:]}"


def _ending(cause: Trigger | None) -> str:
    if cause == Trigger.CALL_FINISHED:
        return (
            "the applicant was connected with the representative; then the call "
            "ended (either side may have hung up, or the applicant dropped off)"
        )
    return "the applicant was connected with the representative"


def _heard_text(transcript: Sequence[TranscriptLine]) -> str:
    return "\n".join(line.text for line in transcript if line.speaker != "agent")


def _call_date(report: ReportInput) -> dt.date | None:
    return report.transcript[-1].at.date() if report.transcript else None


def _rep_name(value: str | None, heard: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    words = {w.lower() for w in re.findall(r"[^\W\d_]+", heard)}
    name_words = re.findall(r"[^\W\d_]+", value.lower())
    return value if name_words and all(w in words for w in name_words) else None


def _deadlines(values: Sequence[str], call_date: dt.date | None) -> list[dt.date]:
    dates: set[dt.date] = set()
    for value in values:
        try:
            date = dt.date.fromisoformat(value.strip())
        except ValueError:
            continue
        if call_date is not None and not (
            call_date <= date <= call_date + dt.timedelta(days=MAX_DEADLINE_DAYS)
        ):
            continue
        dates.add(date)
    return sorted(dates)


def _alnum(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _ids(report: ReportInput) -> str:
    return f"call_id={report.call_id} case_id={report.case_id}"
