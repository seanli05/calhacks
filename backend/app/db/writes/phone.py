"""Writes owned by the phone agent: calls, transcripts."""

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from app.contracts import CallReport, CallState
from app.contracts.common import BriefId, CallId, CaseId, JobId, MessageId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.ids import new_id
from app.db.tables import utcnow


async def create_call(
    case_id: CaseId, job_id: JobId, brief_id: BriefId, consent_message_id: MessageId
) -> tables.Call:
    """The phone agent mints the call ID here (C7)."""
    call = tables.Call(
        case_id=case_id,
        job_id=job_id,
        brief_id=brief_id,
        consent_message_id=consent_message_id,
    )
    async with session() as db:
        db.add(call)
        await db.commit()
        return call


async def set_call_state(
    call_id: CallId, state: CallState, twilio_call_sid: str | None = None
) -> tables.Call:
    async with session() as db:
        call = await must_get(db, tables.Call, call_id)
        call.state = state
        if twilio_call_sid is not None:
            call.twilio_call_sid = twilio_call_sid
        if state == CallState.ENDED and call.ended_at is None:
            call.ended_at = utcnow()
        await db.commit()
        return call


async def save_call_report(call_id: CallId, report: CallReport) -> tables.Call:
    async with session() as db:
        call = await must_get(db, tables.Call, call_id)
        call.report = report.model_dump(mode="json")
        call.outcome = report.outcome
        await db.commit()
        return call


async def save_transcript(
    call_id: CallId, lines: list[dict[str, Any]]
) -> tables.Transcript:
    """Create or replace the call's transcript; safe to call as the call goes on.

    Each line: `{"at": "<ISO time>", "speaker": "agent" | "agency" | "user", "text": "…"}`.
    """
    async with session() as db:
        await db.execute(
            insert(tables.Transcript)
            .values(
                id=new_id("transcript"),
                call_id=call_id,
                lines=lines,
                created_at=utcnow(),
            )
            .on_conflict_do_update(index_elements=["call_id"], set_={"lines": lines})
        )
        await db.commit()
        query = select(tables.Transcript).where(tables.Transcript.call_id == call_id)
        return (await db.execute(query)).scalar_one()
