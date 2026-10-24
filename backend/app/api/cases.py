"""The case list, the case view, and call transcripts."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.case_views import (
    CallReads,
    appointment_of,
    build_call_summary,
    call_reads,
    call_summary,
    fast_result_of,
    first_document,
    page_media_ids,
)
from app.api.common import LangQuery, found, localize, mask, resolve_language
from app.api.models import (
    Appointment,
    BriefInfo,
    CaseDetail,
    CaseSummary,
    ChecklistEntry,
    Localized,
    MaskedRef,
    Transcript,
    TranscriptLine,
    VerificationInfo,
)
from app.contracts import Verification
from app.db import reads, tables
from app.db.errors import NotFound

logger = logging.getLogger(__name__)

router = APIRouter()

# Never sent as refs: the date of birth at all, the location only in `appointment`.
_HIDDEN_REFS = {"date_of_birth", "interview_location"}


@router.get("/users/{user_id}/cases")
async def list_cases(user_id: str, lang: LangQuery = None) -> list[CaseSummary]:
    lang, cases = await asyncio.gather(
        resolve_language(user_id, lang), reads.list_active_cases(user_id)
    )
    return list(await asyncio.gather(*(_case_summary(case, lang) for case in cases)))


async def _case_summary(case: tables.Case, lang: str) -> CaseSummary:
    calls, document, stage, appointment = await asyncio.gather(
        reads.list_calls(case.id),
        first_document(case),
        reads.case_progress(case.id),
        appointment_of(case.id, fast_result_of(case)),
    )
    pages = page_media_ids(document)
    return CaseSummary(
        id=case.id,
        doc_type=case.doc_type,
        stage=stage,
        deadline=case.deadline,
        appointment=appointment,
        latest_call=await call_summary(calls[-1], lang) if calls else None,
        thumbnail_media_id=pages[0] if pages else None,
        created_at=case.created_at,
    )


@router.get("/cases/{case_id}")
async def case_detail(case_id: str, lang: LangQuery = None) -> CaseDetail:
    """Every read starts at once: those that need only `case_id` run alongside
    `get_case` and the reads that need the case row."""
    try:
        (
            (case, lang, document, appointment),
            stage,
            refs,
            verification,
            brief,
            calls,
        ) = await asyncio.gather(
            _case_with_dependents(case_id, lang),
            reads.case_progress(case_id),
            reads.list_case_refs(case_id),
            reads.latest_verification(case_id),
            reads.latest_brief(case_id),
            _calls(case_id),
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    fast = fast_result_of(case)
    return CaseDetail(
        id=case.id,
        user_id=case.user_id,
        doc_type=case.doc_type,
        issuer=fast.issuer if fast else None,
        stage=stage,
        deadline=case.deadline,
        urgency=fast.urgency if fast else None,
        document_id=document.id if document else None,
        page_media_ids=page_media_ids(document),
        explanation=_maybe_localize(fast.explanation_en if fast else None, lang),
        what_is_asked=_maybe_localize(fast.what_is_asked if fast else None, lang),
        appointment=appointment,
        checklist=[
            ChecklistEntry(kind=item.kind, item=localize(item.item, lang))
            for item in (fast.checklist_en if fast else [])
        ],
        refs=[
            MaskedRef(name=ref.name, masked=mask(ref.value))
            for ref in refs
            if ref.name not in _HIDDEN_REFS
        ],
        verification=_verification_info(verification, lang),
        brief=_brief_info(brief, lang),
        calls=[build_call_summary(fetched, lang) for fetched in calls],
    )


async def _case_with_dependents(
    case_id: str, lang: str | None
) -> tuple[tables.Case, str, tables.Document | None, Appointment | None]:
    case = await reads.get_case(case_id)
    if case is None:
        raise NotFound(f"cases {case_id} not found")
    lang, document, appointment = await asyncio.gather(
        resolve_language(case.user_id, lang),
        first_document(case),
        appointment_of(case.id, fast_result_of(case)),
    )
    return case, lang, document, appointment


async def _calls(case_id: str) -> list[CallReads]:
    calls = await reads.list_calls(case_id)
    return list(await asyncio.gather(*(call_reads(call) for call in calls)))


@router.get("/calls/{call_id}/transcript")
async def transcript(call_id: str) -> Transcript:
    row = found(await reads.get_transcript(call_id), "transcript")
    lines = []
    for line in row.lines:
        try:
            lines.append(TranscriptLine.model_validate(line))
        except ValidationError as exc:
            logger.warning("transcript %s: skipping invalid line (%s)", row.id, exc)
    return Transcript(id=row.id, call_id=row.call_id, lines=lines)


def _maybe_localize(en: str | None, lang: str) -> Localized | None:
    return localize(en, lang) if en else None


def _verification_info(
    row: tables.Verification | None, lang: str
) -> VerificationInfo | None:
    if row is None:
        return None
    try:
        result = Verification.model_validate(row.result)
    except ValidationError as exc:
        logger.warning("verification %s: invalid result (%s)", row.id, exc)
        return VerificationInfo(status=row.status, evidence=[], red_flags=[])
    return VerificationInfo(
        status=row.status,
        evidence=result.evidence,
        red_flags=[localize(flag, lang) for flag in result.red_flags],
    )


def _brief_info(row: tables.CaseBrief | None, lang: str) -> BriefInfo | None:
    """The brief's shape is still provisional (contracts/brief.py), so read the two
    fields we show defensively."""
    if row is None:
        return None
    goal = row.brief.get("call_goal_en")
    questions = row.brief.get("questions_to_ask")
    return BriefInfo(
        call_goal=localize(goal, lang) if isinstance(goal, str) and goal else None,
        questions_to_ask=[
            localize(q, lang)
            for q in (questions if isinstance(questions, list) else [])
            if isinstance(q, str)
        ],
    )
