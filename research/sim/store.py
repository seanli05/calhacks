# SIM: replace with person 1's DB helpers when person 1 lands them
"""Store interface the research agent expects from the shared DB helpers.

Only jobs.py talks to a Store. The record types here are guesses at person 1's
rows; swap them for the real ones when the schema lands.
"""

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from research.models import R1, CaseBrief, LegitimacySignals, Verification

JobType = Literal[
    "research_fast",
    "research_deep",
    "research_question",
    "call",
    "memory_write",
    "glossary_lookup",
]
JobStatus = Literal["queued", "running", "done", "failed"]


class DocumentPage(BaseModel):
    content_type: str
    data: bytes


class Document(BaseModel):
    document_id: str
    user_id: str
    pages: list[DocumentPage]


class CaseRecord(BaseModel):
    """`cases` row. Holds the signals so the deep pass can run from the case_id alone."""

    case_id: str
    user_id: str
    document_ids: list[str]
    r1: R1
    signals: LegitimacySignals
    call_purpose: str | None = None


class Job(BaseModel):
    job_id: str
    type: JobType
    status: JobStatus
    case_id: str | None = None
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


class Event(BaseModel):
    """Event envelope from Plan.md (C14). Carries IDs, never user data (C27)."""

    event_id: str
    created_at: datetime
    type: str
    source: str
    case_id: str | None = None
    call_id: str | None = None
    job_id: str | None = None
    summary_en: str
    data: dict[str, Any] = {}


class Store(Protocol):
    async def get_document(self, document_id: str) -> Document: ...

    async def get_case(self, case_id: str) -> CaseRecord: ...

    async def insert_case(self, case: CaseRecord) -> None: ...

    async def insert_verification(
        self, case_id: str, verification: Verification
    ) -> str:
        """Returns the new ver_ id."""
        ...

    async def insert_case_brief(self, brief: CaseBrief) -> None: ...

    async def insert_case_ref(self, case_id: str, field: str, value: str) -> str:
        """Stores the real value and returns its `<ref:field>` placeholder."""
        ...

    async def get_case_refs(self, case_id: str) -> dict[str, str]:
        """Real values for a case, by field. Read only to scrub them from text."""
        ...

    async def create_job(
        self, job_type: JobType, payload: dict[str, Any], case_id: str | None = None
    ) -> str:
        """Queues a job and returns its job_ id."""
        ...

    async def update_job(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None: ...

    async def add_event(
        self,
        event_type: str,
        source: str,
        summary_en: str,
        *,
        case_id: str | None = None,
        call_id: str | None = None,
        job_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Appends an event and returns its event_ id."""
        ...
