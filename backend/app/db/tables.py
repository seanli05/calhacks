"""Every table, exactly as docs/specs/data-layer-schema.md lists them.

Enums are stored as text (AutoString) and typed with the StrEnums from
app.contracts.common, so adding a value never needs a schema change. JSON columns
hold Plan.md payloads; the helpers convert them to and from contract models.
Some class names match contract models (Event, Verification, CaseBrief), so
helpers import this module as `tables` and qualify.
"""

from datetime import UTC, date, datetime
from functools import partial
from typing import Any

from sqlalchemy import DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import AutoString, Field, SQLModel

from app.contracts.common import (
    CallOutcome,
    CallState,
    FactSource,
    FactStatus,
    JobStatus,
    JobType,
    MessageDirection,
    MessageSender,
    QuestionStatus,
    Sensitivity,
    TrustLevel,
    VerificationStatus,
)
from app.db.ids import new_id


def utcnow() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> Any:
    return Field(default_factory=partial(new_id, prefix), primary_key=True)


def _created() -> Any:
    return Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


def _created_indexed() -> Any:
    return Field(default_factory=utcnow, sa_type=DateTime(timezone=True), index=True)


def _maybe_time() -> Any:
    return Field(default=None, sa_type=DateTime(timezone=True))


def _text_enum() -> Any:
    return Field(sa_type=AutoString)


def _json_list() -> Any:
    return Field(default_factory=list, sa_type=JSONB)


def _json_dict() -> Any:
    return Field(default_factory=dict, sa_type=JSONB)


def _maybe_json() -> Any:
    return Field(default=None, sa_type=JSONB)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = _id("user")
    whatsapp_number: str = Field(unique=True)
    language: str | None = None
    created_at: datetime = _created()


class Profile(SQLModel, table=True):
    __tablename__ = "profile"

    user_id: str = Field(foreign_key="users.id", primary_key=True)
    fields: dict[str, Any] = _json_dict()
    updated_at: datetime = _created()


class Fact(SQLModel, table=True):
    __tablename__ = "facts"

    id: str = _id("fact")
    user_id: str = Field(foreign_key="users.id", index=True)
    fact: str
    category: str
    source: FactSource = _text_enum()
    source_ref: str | None = None
    sensitivity: Sensitivity = _text_enum()
    status: FactStatus = _text_enum()
    supersedes: str | None = None
    recorded_at: datetime = _created()


class Media(SQLModel, table=True):
    __tablename__ = "media"

    id: str = _id("media")
    user_id: str = Field(foreign_key="users.id")
    content_type: str
    data: bytes
    twilio_media_url: str | None = None
    created_at: datetime = _created()


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = _id("doc")
    user_id: str = Field(foreign_key="users.id", index=True)
    pages: list[dict[str, Any]] = _json_list()
    created_at: datetime = _created()


class Case(SQLModel, table=True):
    __tablename__ = "cases"

    id: str = _id("case")
    user_id: str = Field(foreign_key="users.id", index=True)
    document_ids: list[str] = _json_list()
    doc_type: str | None = None
    deadline: date | None = None
    fast_result: dict[str, Any] | None = _maybe_json()
    created_at: datetime = _created()
    updated_at: datetime = _created()


class CaseBrief(SQLModel, table=True):
    __tablename__ = "case_briefs"

    id: str = _id("brief")
    case_id: str = Field(foreign_key="cases.id", index=True)
    brief: dict[str, Any] = _json_dict()
    handoff_note: str
    created_at: datetime = _created()


class Verification(SQLModel, table=True):
    __tablename__ = "verifications"

    id: str = _id("ver")
    case_id: str = Field(foreign_key="cases.id", index=True)
    status: VerificationStatus = _text_enum()
    official_phone: str | None = None
    result: dict[str, Any] = _json_dict()
    created_at: datetime = _created()


class CaseRef(SQLModel, table=True):
    __tablename__ = "case_refs"

    case_id: str = Field(foreign_key="cases.id", primary_key=True)
    name: str = Field(primary_key=True)
    value: str
    created_at: datetime = _created()


class GlossaryTerm(SQLModel, table=True):
    __tablename__ = "glossary"
    __table_args__ = (UniqueConstraint("term", "language"),)

    id: str = _id("term")
    term: str
    language: str
    translation: str
    source_url: str | None = None
    trust_level: TrustLevel = _text_enum()
    created_at: datetime = _created()


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = _id("job")
    type: JobType = Field(sa_type=AutoString, index=True)
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_type=AutoString, index=True)
    created_by: str
    user_id: str = Field(foreign_key="users.id")
    case_id: str | None = None
    payload: dict[str, Any] = _json_dict()
    result: dict[str, Any] | None = _maybe_json()
    error: str | None = None
    created_at: datetime = _created()
    started_at: datetime | None = _maybe_time()
    finished_at: datetime | None = _maybe_time()


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = _id("msg")
    user_id: str = Field(foreign_key="users.id", index=True)
    case_id: str | None = None
    direction: MessageDirection = _text_enum()
    sender: MessageSender = _text_enum()
    body_original: str
    body_en: str | None = None
    language: str
    media_ids: list[str] = _json_list()
    template: str | None = None
    question_id: str | None = None
    twilio_sid: str | None = None
    created_at: datetime = _created_indexed()


class Call(SQLModel, table=True):
    __tablename__ = "calls"

    id: str = _id("call")
    case_id: str = Field(foreign_key="cases.id", index=True)
    job_id: str = Field(foreign_key="jobs.id")
    brief_id: str = Field(foreign_key="case_briefs.id")
    consent_message_id: str = Field(foreign_key="messages.id")
    state: CallState = Field(default=CallState.DIALING, sa_type=AutoString)
    twilio_call_sid: str | None = None
    outcome: CallOutcome | None = Field(default=None, sa_type=AutoString)
    report: dict[str, Any] | None = _maybe_json()
    started_at: datetime = _created()
    ended_at: datetime | None = _maybe_time()


class Transcript(SQLModel, table=True):
    __tablename__ = "transcripts"

    id: str = _id("transcript")
    call_id: str = Field(foreign_key="calls.id", unique=True)
    lines: list[dict[str, Any]] = _json_list()
    created_at: datetime = _created()


class Question(SQLModel, table=True):
    __tablename__ = "questions"

    id: str = _id("question")
    call_id: str = Field(foreign_key="calls.id", index=True)
    user_id: str = Field(foreign_key="users.id")
    template: str
    options_en: list[str] = _json_list()
    default_option: int
    timeout_s: int
    status: QuestionStatus = Field(default=QuestionStatus.OPEN, sa_type=AutoString)
    choice: int | None = None
    answered_at: datetime | None = _maybe_time()
    late_reply_at: datetime | None = _maybe_time()
    created_at: datetime = _created()


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: str = _id("event")
    created_at: datetime = _created_indexed()
    type: str = Field(index=True)
    source: str
    user_id: str = Field(foreign_key="users.id", index=True)
    case_id: str | None = None
    call_id: str | None = None
    job_id: str | None = None
    summary_en: str
    data: dict[str, Any] = _json_dict()
