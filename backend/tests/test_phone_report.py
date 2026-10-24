"""The call report (P3) on a fake Claude: hand-written transcripts, including messy
ones, and the checks code applies to whatever the model drafts.

What would hurt in the demo: a report that doesn't validate, an invented reference
number or name, an identifier in the report (C34, C35), a fallback that never
comes, or a model call for a call that never reached a person.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any

import pytest
from app.contracts import (
    CallOutcome,
    CallReport,
    FactSource,
    MemoryWriteJob,
    Sensitivity,
)
from app.phone.llm import LlmError
from app.phone.ports import TranscriptLine
from app.phone.report import (
    TRANSCRIPT_CHARS,
    LlmReportBuilder,
    ReportDraft,
    ReportInput,
    build_report,
    format_transcript,
    report_prompt,
)
from app.phone.report_prompts import REPORT_SYSTEM
from app.phone.state import Trigger
from pydantic import ValidationError

START = dt.datetime(2026, 10, 25, 10, 0, tzinfo=dt.UTC)
RECEIPT = "IOE0912345678"
A_NUMBER = "A201234567"
BRIEF: dict[str, Any] = {
    "brief_id": "brief_77",
    "case_id": "case_123",
    "call_goal_en": (
        "Confirm the asylum interview is still scheduled and ask what to do if the "
        "interpreter can't come"
    ),
    "appointment": {
        "date": "2026-11-18",
        "time": "09:30",
        "location_ref": "<ref:interview_location>",
        "citation": "p1",
    },
    "questions_to_ask": [
        "Is the interview still on?",
        "What if the interpreter is sick?",
    ],
}

type Line = tuple[float, str, str]


def _transcript(lines: Sequence[Line]) -> list[TranscriptLine]:
    return [
        TranscriptLine(at=START + dt.timedelta(seconds=s), speaker=who, text=text)
        for s, who, text in lines
    ]


def _input(
    lines: Sequence[Line],
    *,
    outcome: CallOutcome | None = None,
    cause: Trigger | None = Trigger.CALL_FINISHED,
    brief: dict[str, Any] | None = None,
) -> ReportInput:
    return ReportInput(
        call_id="call_5",
        case_id="case_123",
        outcome=outcome,
        cause=cause,
        transcript_id="transcript_5",
        transcript=_transcript(lines),
        brief=BRIEF if brief is None else brief,
    )


def _draft(**overrides: Any) -> ReportDraft:
    fields: dict[str, Any] = {
        "summary_en": "The representative confirmed the interview.",
        "outcome": "resolved",
        "reference_number": None,
        "rep_name": None,
        "next_steps_en": [],
        "new_deadlines": [],
        "proposed_facts": [],
        "followup_needed": False,
    }
    return ReportDraft(**(fields | overrides))


def _validation_error() -> ValidationError:
    try:
        CallReport.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a validation error")


class FakeReportLlm:
    """Returns `answer` (or raises it) and records each request."""

    def __init__(self, answer: ReportDraft | Exception) -> None:
        self.answer = answer
        self.requests: list[dict[str, Any]] = []

    async def parse(
        self, *, system: str, user: str, output_type: type, timeout_s: float
    ) -> Any:
        self.requests.append({"system": system, "user": user, "type": output_type})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


# The front of a call that reached a person; each transcript adds its own end.
OPENING: list[Line] = [
    (0, "agency", "Thank you for calling. For English, press one."),
    (4, "agent", "one"),
    (20, "agency", "For questions about an appointment, press four."),
    (24, "agent", "four"),
    (30, "agency", "Please continue to hold. Your call is important to us."),
    (600, "agency", "Thank you for holding, this is Maria, how can I help you?"),
    (
        603,
        "agent",
        (
            "Hello, I'm an automated assistant calling for the applicant. "
            "I'm connecting them now."
        ),
    ),
]

RESOLVED: list[Line] = [
    *OPENING,
    (640, "agency", "Okay, I see the interview. It's still on for November 18th."),
    (
        680,
        "agency",
        (
            "If your interpreter can't come, call the asylum office before the "
            "interview and ask to reschedule."
        ),
    ),
    (700, "agency", "Your reference number for today is R-55821."),
    (720, "agency", "Anything else? Okay, have a good day."),
]

NO_REFERENCE: list[Line] = [
    *OPENING[:5],
    (900, "agency", "Hi, thanks for waiting. What can I do for you?"),
    (905, "agent", "Hello, I'm an automated assistant calling for the applicant."),
    (950, "agency", "I can't see appointment details from here, sorry."),
    (980, "agency", "You'll need to contact the asylum office directly."),
]

DROPPED: list[Line] = [
    *OPENING,
    (640, "agency", "Let me pull that up. Can you hear me?"),
    (660, "agency", "Hello? Are you still there? Hello?"),
]

RESCHEDULED: list[Line] = [
    *OPENING,
    (640, "agency", "This is Officer Chen. I see the interview on the 18th."),
    (
        680,
        "agency",
        (
            "That date has been moved. Your new interview is December 2nd at 1 PM. "
            "You'll get a new notice in the mail."
        ),
    ),
    (700, "agency", "Bring the new notice and your interpreter on December 2nd."),
]

HOLD_MUSIC: list[Line] = [
    *OPENING[:4],
    *[
        (
            30 + 30 * i,
            "agency",
            "Please continue to hold. Your call is important to us.",
        )
        for i in range(40)
    ],
    (1300, "agency", "Hello, this is... sorry, the line is bad."),
]


async def test_resolved_call_becomes_a_valid_report() -> None:
    llm = FakeReportLlm(
        _draft(
            reference_number="R-55821",
            rep_name="Maria",
            next_steps_en=[
                "The interview is still on for November 18",
                (
                    "If the interpreter can't come, call the asylum office before the "
                    "interview to ask to reschedule"
                ),
            ],
            proposed_facts=["Asylum interview confirmed for November 18, 2026"],
        )
    )
    report = await LlmReportBuilder(llm)(_input(RESOLVED))

    assert report.outcome == CallOutcome.RESOLVED
    assert report.reference_number == "R-55821"
    assert report.rep_name == "Maria"
    assert len(report.next_steps_en) == 2
    assert report.followup_needed is False
    [fact] = report.proposed_facts
    assert fact.source == FactSource.FROM_CALL
    assert fact.sensitivity == Sensitivity.SENSITIVE
    assert report.transcript_id == "transcript_5"
    assert CallReport.model_validate_json(report.model_dump_json()) == report

    [request] = llm.requests
    assert request["system"] == REPORT_SYSTEM
    assert request["type"] is ReportDraft
    assert "Call goal: Confirm the asylum interview" in request["user"]
    assert "Appointment on the notice: 2026-11-18 at 09:30" in request["user"]
    assert "Call date: 2026-10-25" in request["user"]
    assert "AGENCY: Your reference number for today is R-55821." in request["user"]


async def test_report_round_trips_and_feeds_a_memory_write_job() -> None:
    llm = FakeReportLlm(
        _draft(outcome="partial", proposed_facts=["Interview confirmed for Nov 18"])
    )
    report = await LlmReportBuilder(llm)(_input(RESOLVED))

    dumped = report.model_dump(mode="json")
    assert CallReport.model_validate(dumped) == report
    job = MemoryWriteJob(
        user_id="user_9",
        source=FactSource.FROM_CALL,
        source_ref=report.call_id,
        proposed_facts=report.proposed_facts,
    )
    assert MemoryWriteJob.model_validate_json(job.model_dump_json()) == job


async def test_no_reference_given_drops_an_invented_one_and_its_name() -> None:
    llm = FakeReportLlm(
        _draft(
            outcome="failed",
            reference_number="R-12345",
            rep_name="John",
            next_steps_en=["Contact the asylum office directly"],
            followup_needed=True,
        )
    )
    report = await LlmReportBuilder(llm)(_input(NO_REFERENCE))

    assert report.outcome == CallOutcome.FAILED
    assert report.reference_number is None
    assert report.rep_name is None
    assert report.next_steps_en == ["Contact the asylum office directly"]
    assert report.followup_needed is True


async def test_user_dropped_mid_call_is_partial_and_needs_followup() -> None:
    llm = FakeReportLlm(
        _draft(
            outcome="partial",
            summary_en="The applicant dropped off before the question was answered.",
            next_steps_en=["Call again to confirm the interview"],
            followup_needed=False,
        )
    )
    report = await LlmReportBuilder(llm)(_input(DROPPED))

    assert report.outcome == CallOutcome.PARTIAL
    # Code forces follow-up for anything short of resolved.
    assert report.followup_needed is True
    assert "applicant dropped off" in llm.requests[0]["user"]


async def test_officer_reschedules_and_deadlines_are_checked() -> None:
    llm = FakeReportLlm(
        _draft(
            outcome="resolved",
            rep_name="Officer Chen",
            next_steps_en=["Go to the interview on December 2 at 1 PM instead"],
            new_deadlines=[
                "2026-12-02",
                "2026-12-02",
                "2025-01-01",
                "Dec 2",
                "2031-01-01",
            ],
            proposed_facts=["Asylum interview rescheduled to December 2, 2026"],
            followup_needed=True,
        )
    )
    report = await LlmReportBuilder(llm)(_input(RESCHEDULED))

    # Duplicates, past dates, unparseable text, and far-off dates are dropped.
    assert report.new_deadlines == [dt.date(2026, 12, 2)]
    assert report.rep_name == "Officer Chen"
    assert report.followup_needed is True


async def test_mostly_hold_music_collapses_the_repeats() -> None:
    llm = FakeReportLlm(_draft(outcome="failed", followup_needed=True))
    report = await LlmReportBuilder(llm)(_input(HOLD_MUSIC))

    prompt = llm.requests[0]["user"]
    assert "(repeated 40 times)" in prompt
    assert prompt.count("Please continue to hold") == 1
    assert report.outcome == CallOutcome.FAILED
    assert report.next_steps_en == [] and report.proposed_facts == []


async def test_identifiers_never_reach_the_report() -> None:
    lines = [
        *OPENING,
        (640, "agency", f"I have receipt number {RECEIPT} here."),
        (660, "agency", "Your confirmation number is 7 7 4 1 9."),
    ]
    llm = FakeReportLlm(
        _draft(
            outcome="partial",
            reference_number=RECEIPT,
            next_steps_en=[
                f"Keep your A-Number {A_NUMBER} handy",
                "Wait for a new notice",
                f"Quote {RECEIPT[:3]} {RECEIPT[3:]} when you call",
            ],
            proposed_facts=["The receipt number is IOE-0912-345678", "Notice pending"],
        )
    )
    report = await LlmReportBuilder(llm, blocked_values=[RECEIPT, A_NUMBER])(
        _input(lines)
    )

    assert report.reference_number is None
    assert report.next_steps_en == ["Wait for a new notice"]
    assert [f.fact for f in report.proposed_facts] == ["Notice pending"]
    dumped = report.model_dump_json()
    assert RECEIPT not in dumped and A_NUMBER not in dumped


async def test_blocked_value_without_a_known_shape_is_dropped() -> None:
    """A date of birth has no receipt or A-Number shape; only the blocked list
    catches it."""
    llm = FakeReportLlm(
        _draft(outcome="partial", proposed_facts=["Born 1990-03-14", "Interview on"])
    )
    report = await LlmReportBuilder(llm, blocked_values=["1990-03-14"])(
        _input(RESOLVED)
    )
    assert [f.fact for f in report.proposed_facts] == ["Interview on"]


async def test_reference_read_out_digit_by_digit_is_kept() -> None:
    lines = [*OPENING, (640, "agency", "Your reference is R, five five eight two one.")]
    llm = FakeReportLlm(_draft(outcome="partial", reference_number="R-55821"))
    report = await LlmReportBuilder(llm)(_input(lines))
    assert report.reference_number == "R-55821"


@pytest.mark.parametrize(
    "error",
    [LlmError("timed out after 45.0s"), RuntimeError("a bug"), _validation_error()],
)
async def test_llm_failure_falls_back_to_the_deterministic_report(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    report = await LlmReportBuilder(FakeReportLlm(error))(_input(RESOLVED))

    assert report == await build_report(_input(RESOLVED))
    assert report.outcome == CallOutcome.PARTIAL
    assert report.followup_needed is True
    assert "call_id=call_5" in caplog.text


async def test_items_are_capped_at_five() -> None:
    llm = FakeReportLlm(
        _draft(
            outcome="partial",
            next_steps_en=[f"Step {i}" for i in range(9)] + ["  "],
            proposed_facts=[f"Fact {i}" for i in range(9)],
        )
    )
    report = await LlmReportBuilder(llm)(_input(RESOLVED))
    assert report.next_steps_en == [f"Step {i}" for i in range(5)]
    assert len(report.proposed_facts) == 5


@pytest.mark.parametrize(
    ("outcome", "cause"),
    [
        (CallOutcome.FAILED, Trigger.NO_ANSWER),
        (CallOutcome.FAILED, Trigger.HOLD_TIMEOUT),
        (CallOutcome.FAILED, Trigger.AGENCY_HUNG_UP),
        (CallOutcome.FAILED, Trigger.AGENT_ABORTED),
        (CallOutcome.USER_UNREACHABLE, Trigger.USER_UNREACHABLE),
    ],
)
async def test_calls_that_never_reached_a_person_need_no_model(
    outcome: CallOutcome, cause: Trigger
) -> None:
    llm = FakeReportLlm(_draft())
    report = await LlmReportBuilder(llm)(
        _input(HOLD_MUSIC, outcome=outcome, cause=cause)
    )

    assert llm.requests == []
    assert report.outcome == outcome
    assert report.next_steps_en and report.followup_needed


async def test_connected_call_with_nothing_heard_needs_no_model() -> None:
    llm = FakeReportLlm(_draft())
    report = await LlmReportBuilder(llm)(_input([(0, "agent", "Hello?")]))
    assert llm.requests == []
    assert report.outcome == CallOutcome.PARTIAL


async def test_long_transcript_keeps_its_start_and_end() -> None:
    lines = [(float(i), "agency", f"hold message number {i}") for i in range(5000)]
    text = format_transcript(_transcript(lines))
    assert len(text) <= TRANSCRIPT_CHARS + 100
    assert "hold message number 0" in text
    assert "hold message number 4999" in text
    assert "middle of the call cut" in text


def test_prompt_reads_an_empty_brief() -> None:
    prompt = report_prompt(_input(RESOLVED, brief={}))
    assert "Call goal: Not given" in prompt
    assert "Appointment" not in prompt


def test_prompt_never_resolves_refs() -> None:
    prompt = report_prompt(_input(RESOLVED))
    assert "<ref:" not in prompt  # the location ref isn't passed on at all
