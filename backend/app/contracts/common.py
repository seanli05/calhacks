"""Enums, string formats, ID aliases, and the base model shared by every contract.

Enum values are stored as text in the DB (data-layer-schema.md → Conventions), so
renaming a value is a data change, not just a code change.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class JobType(StrEnum):
    RESEARCH_FAST = "research_fast"
    RESEARCH_DEEP = "research_deep"
    CALL = "call"
    MEMORY_WRITE = "memory_write"
    GLOSSARY_LOOKUP = "glossary_lookup"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"


class FactSource(StrEnum):
    USER_SAID = "user_said"
    FROM_DOCUMENT = "from_document"
    FROM_CALL = "from_call"
    INFERRED = "inferred"


class FactStatus(StrEnum):
    ACTIVE = "active"
    PENDING_CONSENT = "pending_consent"
    SUPERSEDED = "superseded"


class Sensitivity(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"


class CallState(StrEnum):
    DIALING = "dialing"
    MENU = "menu"
    HOLD = "hold"
    HUMAN_DETECTED = "human_detected"
    BRIDGING = "bridging"
    CONNECTED = "connected"
    WRAP_UP = "wrap_up"
    ENDED = "ended"


class CallOutcome(StrEnum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    FAILED = "failed"
    USER_UNREACHABLE = "user_unreachable"


class QuestionStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    TIMED_OUT = "timed_out"


class FastResultStatus(StrEnum):
    OK = "ok"
    NEEDS_BETTER_IMAGE = "needs_better_image"


class Urgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChecklistKind(StrEnum):
    WHO_MUST_COME = "who_must_come"
    BRING = "bring"
    DEADLINE = "deadline"


class MessageDirection(StrEnum):
    IN = "in"
    OUT = "out"


class MessageSender(StrEnum):
    USER = "user"
    ORCHESTRATOR = "orchestrator"
    RELAY = "relay"


class TrustLevel(StrEnum):
    OFFICIAL = "official"
    COMMUNITY = "community"
    MACHINE = "machine"


class Component(StrEnum):
    ORCHESTRATOR = "orchestrator"
    RESEARCH_AGENT = "research_agent"
    PHONE_AGENT = "phone_agent"
    RELAY = "relay"
    MEMORY_WRITER = "memory_writer"
    TRANSLATION = "translation"
    GLOSSARY_WORKER = "glossary_worker"
    DASHBOARD = "dashboard"
    DELETE_HELPER = "delete_helper"


LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]
"""ISO 639-1, e.g. `es`."""

PhoneE164 = Annotated[str, StringConstraints(pattern=r"^\+[1-9]\d{6,14}$")]

RefPlaceholder = Annotated[str, StringConstraints(pattern=r"^<ref:[a-z_]+>$")]
"""A sensitive value's stand-in, resolved within its case via `case_refs` (C11)."""

# Plain aliases with no pattern: Plan.md's examples (`case_123`) are shorter than
# the real `<prefix>_<16 hex>` IDs, and both must validate.
UserId = str
CaseId = str
DocumentId = str
BriefId = str
CallId = str
JobId = str
QuestionId = str
MessageId = str
FactId = str
EventId = str
TranscriptId = str
VerificationId = str
MediaId = str


class Contract(BaseModel):
    """Base for every contract: unknown fields fail loudly instead of being dropped."""

    model_config = ConfigDict(extra="forbid")
