"""User-initiated deletes (C26): the one exception to one-writer-per-table.

Each delete commits together with a `*.deleted` event that carries IDs only (C27),
so the feed can show "(deleted [date])" where the content used to be.
"""

from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.contracts import Component, Event, EventType
from app.contracts.common import DocumentId, FactId, TranscriptId, UserId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.events import add_event
from app.db.ids import new_id
from app.db.tables import utcnow


def _deleted_event(
    event_type: EventType,
    user_id: UserId,
    summary_en: str,
    data: dict[str, Any],
    **ids: str | None,
) -> Event:
    return Event(
        event_id=new_id("event"),
        created_at=utcnow(),
        type=event_type,
        source=Component.DELETE_HELPER,
        user_id=user_id,
        summary_en=summary_en,
        data=data,
        **ids,
    )


async def delete_fact(fact_id: FactId) -> None:
    async with session() as db:
        fact = await must_get(db, tables.Fact, fact_id)
        await db.delete(fact)
        add_event(
            db,
            _deleted_event(
                EventType.FACT_DELETED,
                fact.user_id,
                "User deleted a fact",
                {"fact_id": fact_id},
            ),
        )
        await db.commit()


async def delete_document(document_id: DocumentId) -> None:
    """Deletes the letter and its page images."""
    async with session() as db:
        document = await must_get(db, tables.Document, document_id)
        media_ids = [page["media_id"] for page in document.pages]
        await _delete_where(db, tables.Media, tables.Media.id.in_(media_ids))
        await db.delete(document)
        add_event(
            db,
            _deleted_event(
                EventType.DOCUMENT_DELETED,
                document.user_id,
                "User deleted a letter",
                {"document_id": document_id, "media_ids": media_ids},
            ),
        )
        await db.commit()


async def delete_transcript(transcript_id: TranscriptId) -> None:
    async with session() as db:
        transcript = await must_get(db, tables.Transcript, transcript_id)
        call = await must_get(db, tables.Call, transcript.call_id)
        case = await must_get(db, tables.Case, call.case_id)
        await db.delete(transcript)
        add_event(
            db,
            _deleted_event(
                EventType.TRANSCRIPT_DELETED,
                case.user_id,
                "User deleted a call transcript",
                {"transcript_id": transcript_id},
                case_id=case.id,
                call_id=call.id,
            ),
        )
        await db.commit()


async def _delete_where(db: AsyncSession, model: type[Any], *where: Any) -> int:
    # No in-session sync: these sessions hold no loaded rows of the target table.
    result = await db.execute(
        delete(model).where(*where).execution_options(synchronize_session=False)
    )
    return result.rowcount


async def delete_everything(user_id: UserId) -> dict[str, int]:
    """Erase the user's rows in every table except `events` and `users`, then log
    `user.deleted_all`. Returns how many rows each table lost."""
    async with session() as db:
        await must_get(db, tables.User, user_id)
        case_ids = select(tables.Case.id).where(tables.Case.user_id == user_id)
        call_ids = select(tables.Call.id).where(tables.Call.case_id.in_(case_ids))
        # Children before parents, so no foreign key is left dangling.
        counts = {
            "questions": await _delete_where(
                db, tables.Question, tables.Question.user_id == user_id
            ),
            "transcripts": await _delete_where(
                db, tables.Transcript, tables.Transcript.call_id.in_(call_ids)
            ),
            "calls": await _delete_where(
                db, tables.Call, tables.Call.case_id.in_(case_ids)
            ),
            "case_refs": await _delete_where(
                db, tables.CaseRef, tables.CaseRef.case_id.in_(case_ids)
            ),
            "case_briefs": await _delete_where(
                db, tables.CaseBrief, tables.CaseBrief.case_id.in_(case_ids)
            ),
            "verifications": await _delete_where(
                db, tables.Verification, tables.Verification.case_id.in_(case_ids)
            ),
            "cases": await _delete_where(
                db, tables.Case, tables.Case.user_id == user_id
            ),
            "jobs": await _delete_where(db, tables.Job, tables.Job.user_id == user_id),
            "messages": await _delete_where(
                db, tables.Message, tables.Message.user_id == user_id
            ),
            "facts": await _delete_where(
                db, tables.Fact, tables.Fact.user_id == user_id
            ),
            "profile": await _delete_where(
                db, tables.Profile, tables.Profile.user_id == user_id
            ),
            "documents": await _delete_where(
                db, tables.Document, tables.Document.user_id == user_id
            ),
            "media": await _delete_where(
                db, tables.Media, tables.Media.user_id == user_id
            ),
        }
        add_event(
            db,
            _deleted_event(
                EventType.USER_DELETED_ALL,
                user_id,
                "User deleted everything we knew about them",
                {"counts": counts},
            ),
        )
        await db.commit()
        return counts
