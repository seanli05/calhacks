"""Job payloads written to `jobs.payload` (Plan.md → Handoffs: H1, H2, other job payloads)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.common import (
    BriefId,
    CaseId,
    Contract,
    DocumentId,
    FactSource,
    LanguageCode,
    MessageId,
    PhoneE164,
    Sensitivity,
    UserId,
)


class ProposedFact(Contract):
    fact: str
    source: FactSource
    sensitivity: Sensitivity = Sensitivity.NORMAL
    """Research marks immigration facts `sensitive`; the memory writer holds those
    until the user consents (C15)."""


class ResearchFastJob(Contract):
    """H1. One letter per job; a document may hold several page images (C20)."""

    job: Literal["research_fast"] = "research_fast"
    case_id: CaseId
    user_id: UserId
    document_ids: list[DocumentId]
    user_language: LanguageCode
    user_note_en: str | None = None


class LetterPhone(Contract):
    number: PhoneE164
    label: str | None = None
    quote: str


class LegitimacySignals(Contract):
    """What the deep pass may see of the letter. Never names, case numbers, or the
    user's address."""

    letterhead: str | None = None
    sub_agency: str | None = None
    county: str | None = None
    return_address: str | None = None
    phones: list[LetterPhone] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    form_ids: list[str] = Field(default_factory=list)
    case_number_format: str | None = None
    """The shape of the case number (e.g. 3 letters + 10 digits), never the value."""
    payment_instructions: str | None = None
    signature_block: str | None = None


class ResearchDeepJob(Contract):
    """Queued by the fast pass. It carries the fast pass's signals so the deep pass
    needs nothing else from the case."""

    job: Literal["research_deep"] = "research_deep"
    case_id: CaseId
    user_id: UserId
    document_ids: list[DocumentId]
    signals: LegitimacySignals = Field(default_factory=LegitimacySignals)
    call_purpose: str | None = None
    call_goal_short_en: str | None = None
    """The call goal as the user reads it on WhatsApp: one clause, at most 12 words
    (C41). Becomes R2's `call_goal_en`; the brief keeps the full goal."""


class CallJob(Contract):
    """H2. Carries no phone numbers and no call_id: the phone agent reads the user's
    number through a helper (C6) and creates the call itself (C7). The dialed number
    always comes from the verified official number."""

    job: Literal["call"] = "call"
    case_id: CaseId
    user_id: UserId
    brief_id: BriefId
    user_language: LanguageCode
    consent_at: datetime
    consent_message_id: MessageId
    max_hold_minutes: int
    dial_number_source: Literal["official_phone"] = "official_phone"


class MemoryWriteJob(Contract):
    job: Literal["memory_write"] = "memory_write"
    user_id: UserId
    source: FactSource
    source_ref: str
    """ID of whatever produced the facts (a call, document, or message)."""
    proposed_facts: list[ProposedFact]


class GlossaryLookupJob(Contract):
    job: Literal["glossary_lookup"] = "glossary_lookup"
    term: str
    language: LanguageCode
    case_id: CaseId


class ResearchQuestionJob(Contract):
    """A user's factual question, answered from official sources (C38). The
    orchestrator sends it already in English; with `case_id`, research reads only
    that case's R1 and refs."""

    job: Literal["research_question"] = "research_question"
    user_id: UserId
    case_id: CaseId | None = None
    question_en: str = Field(min_length=1, max_length=2000)


JobPayload = Annotated[
    ResearchFastJob
    | ResearchDeepJob
    | CallJob
    | MemoryWriteJob
    | GlossaryLookupJob
    | ResearchQuestionJob,
    Field(discriminator="job"),
]
