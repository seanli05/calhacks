"""Job results written to `jobs.result` (Plan.md → Handoffs: R1, R2, P3, C38)."""

import datetime as dt
from typing import Self

from pydantic import Field, model_validator

from app.contracts.common import (
    BriefId,
    CallId,
    CallOutcome,
    CaseId,
    ChecklistKind,
    Contract,
    FastResultStatus,
    KeyDateType,
    PhoneE164,
    RefPlaceholder,
    ResearchQuestionStatus,
    SignalState,
    TranscriptId,
    Urgency,
    VerificationStatus,
)
from app.contracts.jobs import ProposedFact


class KeyDate(Contract):
    type: KeyDateType
    raw: str
    """The date as printed on the letter."""
    iso: dt.date | None = None


class KeyFact(Contract):
    """One fact from the letter. A sensitive fact carries `ref` and no `value` or
    `quote` (C11); a public one, like the form ID, carries `value`."""

    field: str
    value: str | None = None
    ref: RefPlaceholder | None = None
    quote: str | None = None
    """The letter's own words, so the fact stays grounded in it."""
    page: int = Field(ge=1)

    @model_validator(mode="after")
    def _value_xor_ref(self) -> Self:
        if (self.value is None) == (self.ref is None):
            raise ValueError("KeyFact needs exactly one of value or ref")
        if self.ref is not None and self.quote is not None:
            raise ValueError("a ref'd KeyFact must not quote the letter")
        return self


class Appointment(Contract):
    date: dt.date
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    """Local time at the location, "HH:MM"; None when the letter gives only a date."""
    location_ref: RefPlaceholder | None = None
    """None when the letter names no location."""
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
    question_en: str | None = None
    """With `needs_user_input`: what to ask the user (C39)."""
    doc_type: str | None = None
    issuer: str | None = None
    deadline: dt.date | None = None
    """Earliest date the user must act (C31)."""
    key_dates: list[KeyDate] = Field(default_factory=list)
    what_is_asked: str | None = None
    appointment: Appointment | None = None
    checklist_en: list[ChecklistItem] = Field(default_factory=list)
    key_facts: list[KeyFact] = Field(default_factory=list)
    explanation_en: str | None = None
    urgency: Urgency | None = None
    verification: VerificationStatus = VerificationStatus.PENDING
    proposed_facts: list[ProposedFact] = Field(default_factory=list)

    @model_validator(mode="after")
    def _status_fields(self) -> Self:
        if self.status == FastResultStatus.NEEDS_BETTER_IMAGE and not self.image_issue:
            raise ValueError("needs_better_image requires image_issue")
        if self.status == FastResultStatus.NEEDS_USER_INPUT and not self.question_en:
            raise ValueError("needs_user_input requires question_en")
        if self.status == FastResultStatus.OK and not (
            self.doc_type and self.explanation_en
        ):
            raise ValueError("ok requires doc_type and explanation_en")
        return self


class SignalResult(Contract):
    signal: str
    state: SignalState
    evidence: list[str] = Field(default_factory=list)


class Verification(Contract):
    status: VerificationStatus
    official_phone: PhoneE164 | None
    """Looked up on the agency's site at run time, never taken from the letter (C32)."""
    letter_phone_matches: bool | None
    """None when the letter prints no phone number, as on the I-797C."""
    evidence: list[str]
    """URLs, the official source first (the dashboard shows its domain)."""
    red_flags: list[str]
    signals: list[SignalResult] = Field(default_factory=list)
    """Each letter signal checked against the official source; explains `unknown`."""


class AlternativeContact(Contract):
    """A verified place to turn when the letter's sender can't be called."""

    name: str
    purpose: str
    phone: PhoneE164 | None = None
    url: str | None = None


class DeepResult(Contract):
    """R2."""

    case_id: CaseId
    verification: Verification
    official_phone_purpose: str | None = None
    alternative_contacts: list[AlternativeContact] = Field(default_factory=list)
    call_recommended: bool
    brief_id: BriefId | None = None
    """None when there's no call to brief, e.g. a suspicious letter."""
    call_goal_en: str | None = None

    @model_validator(mode="after")
    def _call_needs_verified_number(self) -> Self:
        if self.call_recommended and not (
            self.verification.status == VerificationStatus.VERIFIED
            and self.verification.official_phone
        ):
            raise ValueError("call_recommended requires a verified official_phone")
        return self


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
    summary_en: str | None = None
    """Two or three sentences on how the call went, for the orchestrator to send in
    the user's language. None when the report was built without reading the call
    (it never reached a person, or the model failed)."""


class QuestionSource(Contract):
    """An official page an answer rests on, with a quote found on that page."""

    url: str
    quote: str = Field(min_length=1)


class QuestionAnswer(Contract):
    """Result of a `research_question` job (C38). Only `answered` carries an answer,
    always with sources; every other status carries a reason."""

    status: ResearchQuestionStatus
    answer_en: str | None = None
    sources: list[QuestionSource] = Field(default_factory=list)
    reason_en: str | None = None

    @model_validator(mode="after")
    def _answer_has_sources(self) -> Self:
        if self.status == ResearchQuestionStatus.ANSWERED:
            if not (self.answer_en and self.sources):
                raise ValueError("an answered question needs answer_en and sources")
        elif self.answer_en or self.sources:
            raise ValueError(f"status {self.status} carries no answer or sources")
        return self
