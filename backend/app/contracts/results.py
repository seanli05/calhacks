"""Job results written to `jobs.result` (Plan.md → Handoffs: R1, R2, P3)."""

import datetime as dt

from pydantic import Field

from app.contracts.common import (
    BriefId,
    CallId,
    CallOutcome,
    CaseId,
    ChecklistKind,
    Contract,
    FastResultStatus,
    PhoneE164,
    RefPlaceholder,
    TranscriptId,
    Urgency,
    VerificationStatus,
)
from app.contracts.jobs import ProposedFact


class KeyFact(Contract):
    field: str
    ref: RefPlaceholder
    citation: str


class Appointment(Contract):
    date: dt.date
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    """Local time at the location, "HH:MM"."""
    location_ref: RefPlaceholder
    citation: str


class ChecklistItem(Contract):
    kind: ChecklistKind
    item: str
    citation: str


class FastResult(Contract):
    """R1. With `needs_better_image`, only `case_id`, `status`, and `image_issue` are
    set; the orchestrator asks for a new photo using `image_issue` as the tip (C9)."""

    case_id: CaseId
    status: FastResultStatus
    image_issue: str | None = None
    doc_type: str | None = None
    issuer: str | None = None
    deadline: dt.date | None = None
    """Earliest date the user must act (C31)."""
    what_is_asked: str | None = None
    appointment: Appointment | None = None
    checklist_en: list[ChecklistItem] = Field(default_factory=list)
    key_facts: list[KeyFact] = Field(default_factory=list)
    explanation_en: str | None = None
    urgency: Urgency | None = None
    verification: VerificationStatus = VerificationStatus.PENDING
    proposed_facts: list[ProposedFact] = Field(default_factory=list)


class Verification(Contract):
    status: VerificationStatus
    official_phone: PhoneE164 | None
    """Looked up on the agency's site at run time, never taken from the letter (C32)."""
    letter_phone_matches: bool | None
    """None when the letter prints no phone number, as on the I-797C."""
    evidence: list[str]
    red_flags: list[str]


class DeepResult(Contract):
    """R2."""

    case_id: CaseId
    verification: Verification
    call_recommended: bool
    brief_id: BriefId
    call_goal_en: str | None = None


class CallReport(Contract):
    """P3. Stored on the `calls` row (C12)."""

    call_id: CallId
    case_id: CaseId
    outcome: CallOutcome
    reference_number: str | None = None
    rep_name: str | None = None
    next_steps_en: list[str]
    new_deadlines: list[dt.date]
    transcript_id: TranscriptId
    proposed_facts: list[ProposedFact]
    followup_needed: bool
