"""Research event types and the guarded event writer.

Events carry IDs and non-sensitive fields only (C27). Every write goes through
`LeakGuard` first, so a sensitive value for the case can't reach `events` or a
job row.
"""

import json
import re
from collections.abc import Iterable
from typing import Any

from app.contracts import Component, Event, EventType
from app.db import events as db_events
from app.db.ids import new_id
from app.db.tables import utcnow

SOURCE = Component.RESEARCH_AGENT

CASE_CREATED = EventType.CASE_CREATED
FAST_STARTED = EventType("research.fast_started")
FAST_SLOW = EventType("research.fast_slow")
FAST_DONE = EventType("research.fast_done")
FAST_FAILED = EventType("research.fast_failed")
DEEP_STARTED = EventType("research.deep_started")
DEEP_DONE = EventType("research.deep_done")
DEEP_FAILED = EventType("research.deep_failed")
QUESTION_STARTED = EventType("research.question_started")
QUESTION_DONE = EventType("research.question_done")
QUESTION_FAILED = EventType("research.question_failed")
SEARCH = EventType("research.search")
FETCH = EventType("research.fetch")
CHECK = EventType("research.check")
VERIFIED = EventType.VERIFICATION_VERIFIED
SUSPICIOUS = EventType.VERIFICATION_SUSPICIOUS
UNKNOWN = EventType.VERIFICATION_UNKNOWN

RESEARCH_LOG_TYPES = frozenset({SEARCH, FETCH, CHECK})
VERIFICATION_EVENT = {
    "verified": VERIFIED,
    "suspicious": SUSPICIOUS,
    "unknown": UNKNOWN,
}


SHORT_VALUE_LEN = 12
"""Values this short only match as whole words, so a name like "Ana" doesn't hit "Analysis"."""


class LeakDetected(RuntimeError):
    """A sensitive value was about to be written. The message names the target, never the value."""


class LeakGuard:
    """Holds the case's sensitive values in memory and rejects any write that contains one."""

    def __init__(self) -> None:
        self._patterns: list[re.Pattern[str]] = []

    def add(self, values: Iterable[str]) -> None:
        for value in values:
            value = value.strip()
            if not value:
                continue
            # Match the value as written and as it appears inside JSON strings.
            escaped = json.dumps(value, ensure_ascii=False)[1:-1]
            for form in {value, escaped}:
                pattern = re.escape(form)
                if len(value) <= SHORT_VALUE_LEN:
                    pattern = rf"(?<!\w){pattern}(?!\w)"
                self._patterns.append(re.compile(pattern, re.IGNORECASE))

    def check(self, target: str, payload: Any) -> None:
        text = json.dumps(payload, default=str, ensure_ascii=False)
        if any(p.search(text) for p in self._patterns):
            raise LeakDetected(f"sensitive value found in {target}")


class EventLog:
    """Writes research events for one job, checking each against the guard."""

    def __init__(
        self, guard: LeakGuard, *, user_id: str, case_id: str | None, job_id: str
    ) -> None:
        self.guard = guard
        self.user_id = user_id
        self.case_id = case_id
        self.job_id = job_id

    async def emit(
        self, event_type: str, summary_en: str, data: dict[str, Any] | None = None
    ) -> str:
        self.guard.check(
            f"event {event_type}", {"summary_en": summary_en, "data": data}
        )
        event = await db_events.append_event(
            Event(
                event_id=new_id("event"),
                created_at=utcnow(),
                type=EventType(event_type),
                source=SOURCE,
                user_id=self.user_id,
                case_id=self.case_id,
                job_id=self.job_id,
                summary_en=summary_en,
                data=data or {},
            )
        )
        return event.event_id
