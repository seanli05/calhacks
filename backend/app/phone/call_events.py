"""One call's event writer: fills the C14 envelope so the runner passes only what's new."""

from dataclasses import dataclass, replace
from typing import Any

from app.contracts import Component, Event, EventType
from app.contracts.common import CallId, CaseId, JobId, UserId
from app.db.ids import new_id
from app.phone.ports import Clock, EventLog


@dataclass(frozen=True)
class CallEvents:
    """Not a port: the same code runs over the real and the fake `EventLog`.
    `call_id` is None until `create_call`; use `for_call` once it exists."""

    log: EventLog
    clock: Clock
    user_id: UserId
    case_id: CaseId
    job_id: JobId
    call_id: CallId | None = None

    def for_call(self, call_id: CallId) -> "CallEvents":
        return replace(self, call_id=call_id)

    async def append(
        self, event_type: EventType, summary_en: str, **data: Any
    ) -> Event:
        """IDs and short fields only in `data`; never identifiers or fact text (C27)."""
        event = Event(
            event_id=new_id("event"),
            created_at=self.clock.now(),
            type=event_type,
            source=Component.PHONE_AGENT,
            user_id=self.user_id,
            case_id=self.case_id,
            call_id=self.call_id,
            job_id=self.job_id,
            summary_en=summary_en,
            data=data,
        )
        await self.log.append(event)
        return event
