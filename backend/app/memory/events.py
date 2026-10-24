"""The memory writer's events: IDs only, never the fact's text (C27)."""

from app.contracts import Component, Event, EventType
from app.contracts.common import CaseId, FactId, JobId, UserId
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow


async def fact_event(
    event_type: EventType,
    user_id: UserId,
    fact_id: FactId,
    summary_en: str,
    *,
    case_id: CaseId | None = None,
    job_id: JobId | None = None,
) -> None:
    await append_event(
        Event(
            event_id=new_id("event"),
            created_at=utcnow(),
            type=event_type,
            source=Component.MEMORY_WRITER,
            user_id=user_id,
            case_id=case_id,
            job_id=job_id,
            summary_en=summary_en,
            data={"fact_id": fact_id},
        )
    )
