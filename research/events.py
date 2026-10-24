"""Research event types and the guarded event writer.

Events carry IDs and non-sensitive fields only (C27). Every write goes through
`LeakGuard` first, so a sensitive value for the case can't reach `events` or a
job row.
"""

import json
from collections.abc import Iterable
from typing import Any

from research.sim.store import Store

SOURCE = "research_agent"

FAST_STARTED = "research.fast_started"
FAST_SLOW = "research.fast_slow"
FAST_DONE = "research.fast_done"
FAST_FAILED = "research.fast_failed"
DEEP_STARTED = "research.deep_started"
DEEP_DONE = "research.deep_done"
DEEP_FAILED = "research.deep_failed"
SEARCH = "research.search"
FETCH = "research.fetch"
CHECK = "research.check"
VERIFIED = "verification.verified"
SUSPICIOUS = "verification.suspicious"
UNKNOWN = "verification.unknown"

RESEARCH_LOG_TYPES = frozenset({SEARCH, FETCH, CHECK})
VERIFICATION_EVENT = {
    "verified": VERIFIED,
    "suspicious": SUSPICIOUS,
    "unknown": UNKNOWN,
}


class LeakDetected(RuntimeError):
    """A sensitive value was about to be written. The message names the target, never the value."""


class LeakGuard:
    """Holds the case's sensitive values in memory and rejects any write that contains one."""

    def __init__(self) -> None:
        self._values: set[str] = set()

    def add(self, values: Iterable[str]) -> None:
        self._values.update(v for v in values if v)

    def check(self, target: str, payload: Any) -> None:
        text = json.dumps(payload, default=str, ensure_ascii=False)
        for value in self._values:
            escaped = json.dumps(value, ensure_ascii=False)[1:-1]
            if value in text or escaped in text:
                raise LeakDetected(f"sensitive value found in {target}")


class EventLog:
    """Writes research events for one job, checking each against the guard."""

    def __init__(
        self, store: Store, guard: LeakGuard, *, case_id: str | None, job_id: str
    ) -> None:
        self.store = store
        self.guard = guard
        self.case_id = case_id
        self.job_id = job_id

    async def emit(
        self, event_type: str, summary_en: str, data: dict[str, Any] | None = None
    ) -> str:
        self.guard.check(
            f"event {event_type}", {"summary_en": summary_en, "data": data}
        )
        return await self.store.add_event(
            event_type,
            SOURCE,
            summary_en,
            case_id=self.case_id,
            job_id=self.job_id,
            data=data,
        )
