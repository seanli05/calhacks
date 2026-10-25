"""Response bodies of the dashboard API. They mirror dashboard/lib/api/types.ts field
for field (same names, same nullability); change both in the same commit."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts import (
    CallOutcome,
    CallState,
    ChecklistKind,
    FactSource,
    FactStatus,
    MessageDirection,
    MessageSender,
    Sensitivity,
    TrustLevel,
    Urgency,
    VerificationStatus,
)
from app.db.progress import CaseStage


class Localized(BaseModel):
    """`text` in the requested language; `en` the English it came from."""

    text: str
    en: str


class DemoInfo(BaseModel):
    user_id: str
    case_id: str | None


class PublicConfig(BaseModel):
    whatsapp_number: str
    sandbox_join_message: str | None


class UserInfo(BaseModel):
    id: str
    language: str | None


class FeedItem(BaseModel):
    id: str
    at: dt.datetime
    type: str
    case_id: str | None
    call_id: str | None
    text: Localized
    deleted_at: dt.datetime | None


class Appointment(BaseModel):
    date: dt.date
    time: str | None
    location: str | None


class ChecklistEntry(BaseModel):
    kind: ChecklistKind
    item: Localized


class MaskedRef(BaseModel):
    name: str
    masked: str


class VerificationInfo(BaseModel):
    status: VerificationStatus
    evidence: list[str]
    red_flags: list[Localized]


class BriefInfo(BaseModel):
    call_goal: Localized | None
    questions_to_ask: list[Localized]


class CallReportInfo(BaseModel):
    outcome: CallOutcome
    summary: Localized | None
    """How the call went, in two or three sentences; None when the call never
    reached a person."""
    reference_number: str | None
    rep_name: str | None
    next_steps: list[Localized]
    new_deadlines: list[dt.date]
    followup_needed: bool


class CallSummary(BaseModel):
    id: str
    state: CallState
    outcome: CallOutcome | None
    started_at: dt.datetime
    ended_at: dt.datetime | None
    hold_started_at: dt.datetime | None
    report: CallReportInfo | None
    transcript_id: str | None


class CaseSummary(BaseModel):
    id: str
    doc_type: str | None
    stage: CaseStage
    deadline: dt.date | None
    appointment: Appointment | None
    latest_call: CallSummary | None
    thumbnail_media_id: str | None
    created_at: dt.datetime


class CaseDetail(BaseModel):
    id: str
    user_id: str
    doc_type: str | None
    issuer: str | None
    stage: CaseStage
    deadline: dt.date | None
    urgency: Urgency | None
    document_id: str | None
    page_media_ids: list[str]
    explanation: Localized | None
    what_is_asked: Localized | None
    appointment: Appointment | None
    checklist: list[ChecklistEntry]
    refs: list[MaskedRef]
    verification: VerificationInfo | None
    brief: BriefInfo | None
    calls: list[CallSummary]


class TranscriptLine(BaseModel):
    at: dt.datetime
    speaker: Literal["agent", "agency", "user"]
    text: str


class Transcript(BaseModel):
    id: str
    call_id: str
    lines: list[TranscriptLine]


class FactInfo(BaseModel):
    id: str
    fact: Localized
    category: str
    source: FactSource
    sensitivity: Sensitivity
    status: FactStatus
    recorded_at: dt.datetime


class DocumentInfo(BaseModel):
    id: str
    doc_type: str | None
    case_id: str | None
    page_media_ids: list[str]
    created_at: dt.datetime


class TranscriptInfo(BaseModel):
    id: str
    call_id: str
    case_id: str
    created_at: dt.datetime


class Memory(BaseModel):
    profile: dict[str, str]
    facts: list[FactInfo]
    documents: list[DocumentInfo]
    transcripts: list[TranscriptInfo]


class Message(BaseModel):
    id: str
    at: dt.datetime
    direction: MessageDirection
    sender: MessageSender
    body: str
    body_en: str | None
    language: str
    media_ids: list[str] = Field(default_factory=list)
    case_id: str | None


class Suggestion(BaseModel):
    id: str
    kind: Literal["countdown", "glossary", "checklist"]
    case_id: str | None
    title: Localized
    detail: Localized
    action: Localized
    prefill: str


class GlossaryEntry(BaseModel):
    term: str
    translation: str
    trust_level: TrustLevel
    source_url: str | None


class LiveTip(BaseModel):
    """`say_en` is English to read out loud; null for `yourself`, which marks a
    question only the user may answer (rule 3) and never carries an answer."""

    id: str
    kind: Literal["ask", "yourself"]
    line_id: str
    say_en: str | None
    meaning: Localized


class LiveLineHeard(BaseModel):
    type: Literal["line"] = "line"
    id: str
    at: dt.datetime
    speaker: Literal["agent", "agency", "user"]
    en: str


class LiveDelta(BaseModel):
    type: Literal["delta"] = "delta"
    id: str
    text: str


class LiveLineDone(BaseModel):
    type: Literal["done"] = "done"
    id: str


class LiveTipShown(BaseModel):
    type: Literal["tip"] = "tip"
    tip: LiveTip


class LiveTipUsed(BaseModel):
    type: Literal["tip_used"] = "tip_used"
    id: str


LiveCallEvent = LiveLineHeard | LiveDelta | LiveLineDone | LiveTipShown | LiveTipUsed
