"""Shared reads. Any component may call these; none of them writes."""

import re
from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.contracts import (
    Event,
    EventType,
    FactStatus,
    JobType,
    QuestionStatus,
    VerificationStatus,
)
from app.contracts.common import (
    BriefId,
    CallId,
    CaseId,
    DocumentId,
    JobId,
    LanguageCode,
    MediaId,
    UserId,
)
from app.db import tables
from app.db.engine import session
from app.db.errors import NotFound, UnverifiedNumber
from app.db.events import from_row
from app.db.progress import CaseStage, compute_stage

_REF = re.compile(r"^<ref:([a-z_]+)>$")


async def _get(model: type[Any], key: Any) -> Any:
    async with session() as db:
        return await db.get(model, key)


async def get_user(user_id: UserId) -> tables.User | None:
    """Also how the phone agent gets the number to ring the user on (C6, C29)."""
    return await _get(tables.User, user_id)


async def get_user_by_number(whatsapp_number: str) -> tables.User | None:
    async with session() as db:
        query = select(tables.User).where(
            tables.User.whatsapp_number == whatsapp_number
        )
        return (await db.execute(query)).scalar_one_or_none()


async def get_profile(user_id: UserId) -> tables.Profile | None:
    return await _get(tables.Profile, user_id)


async def list_facts(
    user_id: UserId, statuses: Collection[FactStatus] | None = None
) -> list[tables.Fact]:
    """All the user's facts, oldest first; pass `statuses` to filter."""
    async with session() as db:
        query = select(tables.Fact).where(tables.Fact.user_id == user_id)
        if statuses is not None:
            query = query.where(tables.Fact.status.in_(list(statuses)))
        query = query.order_by(tables.Fact.recorded_at)
        return list((await db.execute(query)).scalars())


async def get_document(document_id: DocumentId) -> tables.Document | None:
    return await _get(tables.Document, document_id)


async def get_media(media_id: MediaId) -> tables.Media | None:
    return await _get(tables.Media, media_id)


async def get_case(case_id: CaseId) -> tables.Case | None:
    return await _get(tables.Case, case_id)


async def get_brief(brief_id: BriefId) -> tables.CaseBrief | None:
    return await _get(tables.CaseBrief, brief_id)


async def get_call(call_id: CallId) -> tables.Call | None:
    return await _get(tables.Call, call_id)


async def get_transcript(call_id: CallId) -> tables.Transcript | None:
    async with session() as db:
        query = select(tables.Transcript).where(tables.Transcript.call_id == call_id)
        return (await db.execute(query)).scalar_one_or_none()


async def get_job(job_id: JobId) -> tables.Job | None:
    return await _get(tables.Job, job_id)


def _closed_case_ids() -> Any:
    return select(tables.Event.case_id).where(
        tables.Event.type == EventType.CASE_CLOSED, tables.Event.case_id.is_not(None)
    )


async def list_active_cases(user_id: UserId) -> list[tables.Case]:
    """Every case without a `case.closed` event (C22), newest first."""
    async with session() as db:
        query = (
            select(tables.Case)
            .where(
                tables.Case.user_id == user_id,
                tables.Case.id.not_in(_closed_case_ids()),
            )
            .order_by(tables.Case.created_at.desc())
        )
        return list((await db.execute(query)).scalars())


async def _latest_verification(
    db: AsyncSession, case_id: CaseId
) -> tables.Verification | None:
    query = (
        select(tables.Verification)
        .where(tables.Verification.case_id == case_id)
        .order_by(tables.Verification.created_at.desc())
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


async def latest_verification(case_id: CaseId) -> tables.Verification | None:
    async with session() as db:
        return await _latest_verification(db, case_id)


async def _latest_job_status(
    db: AsyncSession, case_id: CaseId, job_type: JobType
) -> str | None:
    query = (
        select(tables.Job.status)
        .where(tables.Job.case_id == case_id, tables.Job.type == job_type)
        .order_by(tables.Job.created_at.desc())
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


async def case_progress(case_id: CaseId) -> CaseStage:
    """The case's stage, computed from its jobs, verdict, and calls (C17)."""
    async with session() as db:
        case = await db.get(tables.Case, case_id)
        if case is None:
            raise NotFound(f"cases {case_id} not found")
        closed_query = _closed_case_ids().where(tables.Event.case_id == case_id)
        closed = (await db.execute(closed_query.limit(1))).first() is not None
        call_query = (
            select(tables.Call.state)
            .where(tables.Call.case_id == case_id)
            .order_by(tables.Call.started_at.desc())
            .limit(1)
        )
        call_state = (await db.execute(call_query)).scalar_one_or_none()
        verification = await _latest_verification(db, case_id)
        fast_job = await _latest_job_status(db, case_id, JobType.RESEARCH_FAST)
        deep_job = await _latest_job_status(db, case_id, JobType.RESEARCH_DEEP)
    return compute_stage(
        closed=closed,
        latest_call_state=call_state,
        latest_verification=verification.status if verification else None,
        fast_job=fast_job,
        deep_job=deep_job,
        fast_result=(case.fast_result or {}).get("status"),
    )


async def official_dial_number(case_id: CaseId) -> str:
    """The only number the phone agent may dial (product rule 2): the latest
    verification's official phone, and only if that verification is `verified`."""
    verification = await latest_verification(case_id)
    if verification is None or verification.status != VerificationStatus.VERIFIED:
        status = verification.status if verification else "none"
        raise UnverifiedNumber(f"case {case_id} is not verified (latest: {status})")
    if not verification.official_phone:
        raise UnverifiedNumber(f"case {case_id} is verified but has no official phone")
    return verification.official_phone


async def resolve_ref(case_id: CaseId, name: str) -> str:
    """The real value behind `<ref:name>` (C11). Accepts `name` or `<ref:name>`."""
    match = _REF.match(name)
    key = match.group(1) if match else name
    ref = await _get(tables.CaseRef, (case_id, key))
    if ref is None:
        raise NotFound(f"ref {key} not found for case {case_id}")
    return ref.value


async def list_events(user_id: UserId, since: datetime | None = None) -> list[Event]:
    """The user's events after `since` (exclusive), oldest first. The dashboard feed
    polls this with the last `created_at` it has."""
    async with session() as db:
        query = select(tables.Event).where(tables.Event.user_id == user_id)
        if since is not None:
            query = query.where(tables.Event.created_at > since)
        query = query.order_by(tables.Event.created_at, tables.Event.id)
        return [from_row(row) for row in (await db.execute(query)).scalars()]


async def list_messages(user_id: UserId) -> list[tables.Message]:
    async with session() as db:
        query = (
            select(tables.Message)
            .where(tables.Message.user_id == user_id)
            .order_by(tables.Message.created_at)
        )
        return list((await db.execute(query)).scalars())


async def get_open_question(user_id: UserId) -> tables.Question | None:
    """The newest open ask_user question, so an inbound reply can find it."""
    async with session() as db:
        query = (
            select(tables.Question)
            .where(
                tables.Question.user_id == user_id,
                tables.Question.status == QuestionStatus.OPEN,
            )
            .order_by(tables.Question.created_at.desc())
            .limit(1)
        )
        return (await db.execute(query)).scalar_one_or_none()


async def get_glossary(language: LanguageCode) -> list[tables.GlossaryTerm]:
    async with session() as db:
        query = (
            select(tables.GlossaryTerm)
            .where(tables.GlossaryTerm.language == language)
            .order_by(tables.GlossaryTerm.term)
        )
        return list((await db.execute(query)).scalars())


async def first_user() -> tables.User | None:
    """The oldest user: the seeded demo user on a freshly reset database."""
    async with session() as db:
        query = select(tables.User).order_by(tables.User.created_at).limit(1)
        return (await db.execute(query)).scalar_one_or_none()


async def list_cases(user_id: UserId) -> list[tables.Case]:
    """Every case, closed ones included, newest first."""
    async with session() as db:
        query = (
            select(tables.Case)
            .where(tables.Case.user_id == user_id)
            .order_by(tables.Case.created_at.desc())
        )
        return list((await db.execute(query)).scalars())


async def list_calls(case_id: CaseId) -> list[tables.Call]:
    """The case's calls, oldest first."""
    async with session() as db:
        query = (
            select(tables.Call)
            .where(tables.Call.case_id == case_id)
            .order_by(tables.Call.started_at)
        )
        return list((await db.execute(query)).scalars())


async def latest_brief(case_id: CaseId) -> tables.CaseBrief | None:
    async with session() as db:
        query = (
            select(tables.CaseBrief)
            .where(tables.CaseBrief.case_id == case_id)
            .order_by(tables.CaseBrief.created_at.desc())
            .limit(1)
        )
        return (await db.execute(query)).scalar_one_or_none()


async def list_case_refs(case_id: CaseId) -> list[tables.CaseRef]:
    """Real values. Callers outside the agents must mask them before showing."""
    async with session() as db:
        query = (
            select(tables.CaseRef)
            .where(tables.CaseRef.case_id == case_id)
            .order_by(tables.CaseRef.name)
        )
        return list((await db.execute(query)).scalars())


async def list_documents(user_id: UserId) -> list[tables.Document]:
    async with session() as db:
        query = (
            select(tables.Document)
            .where(tables.Document.user_id == user_id)
            .order_by(tables.Document.created_at)
        )
        return list((await db.execute(query)).scalars())


async def list_transcripts(
    user_id: UserId,
) -> list[tuple[tables.Transcript, CaseId]]:
    """The user's transcripts with the case each call belongs to, oldest first."""
    async with session() as db:
        query = (
            select(tables.Transcript, tables.Call.case_id)
            .join(tables.Call, tables.Call.id == tables.Transcript.call_id)
            .join(tables.Case, tables.Case.id == tables.Call.case_id)
            .where(tables.Case.user_id == user_id)
            .order_by(tables.Transcript.created_at)
        )
        return [(row[0], row[1]) for row in (await db.execute(query)).all()]


async def latest_event(call_id: CallId, event_type: EventType) -> Event | None:
    async with session() as db:
        query = (
            select(tables.Event)
            .where(tables.Event.call_id == call_id, tables.Event.type == event_type)
            .order_by(tables.Event.created_at.desc())
            .limit(1)
        )
        row = (await db.execute(query)).scalar_one_or_none()
        return from_row(row) if row else None
