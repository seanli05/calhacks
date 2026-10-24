"""Event envelope and types (Plan.md → Events, C14)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.contracts.common import (
    CallId,
    CaseId,
    Component,
    Contract,
    EventId,
    JobId,
    UserId,
)


class EventType(StrEnum):
    CASE_CREATED = "case.created"
    CASE_DOCUMENT_ADDED = "case.document_added"
    CASE_CLOSED = "case.closed"

    RESEARCH_FAST_STARTED = "research.fast_started"
    RESEARCH_FAST_DONE = "research.fast_done"
    RESEARCH_DEEP_STARTED = "research.deep_started"
    RESEARCH_DEEP_DONE = "research.deep_done"

    VERIFICATION_VERIFIED = "verification.verified"
    VERIFICATION_SUSPICIOUS = "verification.suspicious"
    VERIFICATION_UNKNOWN = "verification.unknown"

    CONSENT_REQUESTED = "consent.requested"
    CONSENT_GIVEN = "consent.given"
    CONSENT_DECLINED = "consent.declined"

    CALL_DIALING = "call.dialing"
    CALL_MENU_HEARD = "call.menu_heard"
    CALL_MENU_CHOICE = "call.menu_choice"
    CALL_ASK_USER = "call.ask_user"
    CALL_ASK_USER_ANSWERED = "call.ask_user_answered"
    CALL_ASK_USER_TIMEOUT = "call.ask_user_timeout"
    CALL_ASK_USER_LATE_REPLY = "call.ask_user_late_reply"
    CALL_ON_HOLD = "call.on_hold"
    CALL_HUMAN_DETECTED = "call.human_detected"
    CALL_USER_DIALED = "call.user_dialed"
    CALL_USER_JOINED = "call.user_joined"
    CALL_USER_UNREACHABLE = "call.user_unreachable"
    CALL_ENDED = "call.ended"

    MEMORY_FACT_SAVED = "memory.fact_saved"
    MEMORY_FACT_SUPERSEDED = "memory.fact_superseded"
    MEMORY_FACT_PENDING_CONSENT = "memory.fact_pending_consent"

    FACT_DELETED = "fact.deleted"
    DOCUMENT_DELETED = "document.deleted"
    TRANSCRIPT_DELETED = "transcript.deleted"
    USER_DELETED_ALL = "user.deleted_all"

    GLOSSARY_TERM_ADDED = "glossary.term_added"


USER_MESSAGING_EVENTS: frozenset[EventType] = frozenset(
    {
        EventType.CALL_DIALING,
        EventType.CALL_ON_HOLD,
        EventType.CALL_HUMAN_DETECTED,
        EventType.CALL_USER_UNREACHABLE,
    }
)
"""The only events that message the user (P2); everything else is dashboard-only."""


class Event(Contract):
    """C14 envelope plus `user_id` (data-layer-schema.md, resolution 3). Never put
    fact or document content in `summary_en` or `data`; carry IDs instead (C27)."""

    event_id: EventId
    created_at: datetime
    type: EventType
    source: Component
    user_id: UserId
    case_id: CaseId | None = None
    call_id: CallId | None = None
    job_id: JobId | None = None
    summary_en: str
    data: dict[str, Any] = Field(default_factory=dict)
