"""Writes owned by the research agent: cases, briefs, verifications, case_refs."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.contracts import CaseBrief, FastResult, Verification
from app.contracts.common import CaseId, DocumentId, UserId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.tables import utcnow


async def create_case(
    case_id: CaseId, user_id: UserId, document_ids: Sequence[DocumentId]
) -> tables.Case:
    """`case_id` was minted by the orchestrator in H1 (schema resolution 1).
    Idempotent: returns the existing case when the fast pass runs again for it
    (C39, after the user answers a `needs_user_input` question)."""
    async with session() as db:
        existing = await db.get(tables.Case, case_id)
        if existing is not None:
            return existing
        case = tables.Case(id=case_id, user_id=user_id, document_ids=list(document_ids))
        db.add(case)
        await db.commit()
        return case


async def save_fast_result(case_id: CaseId, result: FastResult) -> tables.Case:
    async with session() as db:
        case = await must_get(db, tables.Case, case_id)
        case.fast_result = result.model_dump(mode="json")
        case.doc_type = result.doc_type
        case.deadline = result.deadline
        case.updated_at = utcnow()
        await db.commit()
        return case


async def save_verification(
    case_id: CaseId, verification: Verification
) -> tables.Verification:
    """Adds a row; the latest one is the case's verdict."""
    row = tables.Verification(
        case_id=case_id,
        status=verification.status,
        official_phone=verification.official_phone,
        result=verification.model_dump(mode="json"),
    )
    async with session() as db:
        db.add(row)
        await db.commit()
        return row


async def save_brief(
    case_id: CaseId,
    brief: CaseBrief | dict[str, Any],
    handoff_note: str | None = None,
) -> tables.CaseBrief:
    """A `CaseBrief` names its own row (`brief_id`, so R2 can point at it before
    this returns) and carries its handoff note. A plain dict, from dev tools and
    tests, gets a new ID and needs `handoff_note`."""
    if isinstance(brief, CaseBrief):
        if brief.case_id != case_id:
            raise ValueError(f"brief {brief.brief_id} is for {brief.case_id}")
        row = tables.CaseBrief(
            id=brief.brief_id,
            case_id=case_id,
            brief=brief.model_dump(mode="json"),
            handoff_note=handoff_note or brief.handoff_note,
        )
    else:
        if handoff_note is None:
            raise ValueError("a dict brief needs a handoff_note")
        row = tables.CaseBrief(case_id=case_id, brief=brief, handoff_note=handoff_note)
    async with session() as db:
        db.add(row)
        await db.commit()
        return row


async def put_ref(case_id: CaseId, name: str, value: str) -> None:
    """Store the real value behind `<ref:name>` (C11). Overwrites a re-read value."""
    async with session() as db:
        await db.execute(
            insert(tables.CaseRef)
            .values(case_id=case_id, name=name, value=value, created_at=utcnow())
            .on_conflict_do_update(
                index_elements=["case_id", "name"], set_={"value": value}
            )
        )
        await db.commit()
