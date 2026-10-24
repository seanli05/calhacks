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
    UserId,
)


class ProposedFact(Contract):
    fact: str
    source: FactSource


class ResearchFastJob(Contract):
    """H1. One letter per job; a document may hold several page images (C20)."""

    job: Literal["research_fast"] = "research_fast"
    case_id: CaseId
    user_id: UserId
    document_ids: list[DocumentId]
    user_language: LanguageCode
    user_note_en: str | None = None


class ResearchDeepJob(Contract):
    job: Literal["research_deep"] = "research_deep"
    case_id: CaseId
    user_id: UserId
    document_ids: list[DocumentId]


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


JobPayload = Annotated[
    ResearchFastJob | ResearchDeepJob | CallJob | MemoryWriteJob | GlossaryLookupJob,
    Field(discriminator="job"),
]
