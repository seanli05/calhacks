"""Append-only event log; every component writes here (C2, C14).

Events carry IDs, never fact or document content (C27).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import Event
from app.db import tables
from app.db.engine import session


def to_row(event: Event) -> tables.Event:
    return tables.Event(
        id=event.event_id,
        created_at=event.created_at,
        type=event.type,
        source=event.source,
        user_id=event.user_id,
        case_id=event.case_id,
        call_id=event.call_id,
        job_id=event.job_id,
        summary_en=event.summary_en,
        data=event.model_dump(mode="json")["data"],
    )


def from_row(row: tables.Event) -> Event:
    return Event(
        event_id=row.id,
        created_at=row.created_at,
        type=row.type,
        source=row.source,
        user_id=row.user_id,
        case_id=row.case_id,
        call_id=row.call_id,
        job_id=row.job_id,
        summary_en=row.summary_en,
        data=row.data,
    )


def add_event(db: AsyncSession, event: Event) -> None:
    """Add to an open session, so the event commits with the change it describes."""
    db.add(to_row(event))


async def append_event(event: Event) -> Event:
    async with session() as db:
        add_event(db, event)
        await db.commit()
    return event
