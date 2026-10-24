"""The case list, the case view, and call transcripts."""

import logging

from fastapi import APIRouter
from pydantic import ValidationError

from app.api.case_views import (
    appointment_of,
    call_summary,
    fast_result_of,
    first_document,
    page_media_ids,
)
from app.api.common import LangQuery, found, localize, mask, resolve_language
from app.api.models import (
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

logger = logging.getLogger(__name__)

router = APIRouter()

# Never sent as refs: the date of birth at all, the location only in `appointment`.
_HIDDEN_REFS = {"date_of_birth", "interview_location"}


@router.get("/users/{user_id}/cases")
async def list_cases(user_id: str, lang: LangQuery = None) -> list[CaseSummary]:
    lang = await resolve_language(user_id, lang)
    summaries = []
    for case in await reads.list_active_cases(user_id):
        calls = await reads.list_calls(case.id)
        pages = page_media_ids(await first_document(case))
        summaries.append(
            CaseSummary(
                id=case.id,
                doc_type=case.doc_type,
                stage=await reads.case_progress(case.id),
                deadline=case.deadline,
                appointment=await appointment_of(case.id, fast_result_of(case)),
                latest_call=await call_summary(calls[-1], lang) if calls else None,
                thumbnail_media_id=pages[0] if pages else None,
                created_at=case.created_at,
            )
        )
    return summaries


@router.get("/cases/{case_id}")
async def case_detail(case_id: str, lang: LangQuery = None) -> CaseDetail:
    case = found(await reads.get_case(case_id), "case")
    lang = await resolve_language(case.user_id, lang)
    fast = fast_result_of(case)
    document = await first_document(case)
    return CaseDetail(
        id=case.id,
        user_id=case.user_id,
        doc_type=case.doc_type,
        issuer=fast.issuer if fast else None,
        stage=await reads.case_progress(case.id),
        deadline=case.deadline,
        urgency=fast.urgency if fast else None,
        document_id=document.id if document else None,
        page_media_ids=page_media_ids(document),
        explanation=_maybe_localize(fast.explanation_en if fast else None, lang),
        what_is_asked=_maybe_localize(fast.what_is_asked if fast else None, lang),
        appointment=await appointment_of(case.id, fast),
        checklist=[
            ChecklistEntry(kind=item.kind, item=localize(item.item, lang))
            for item in (fast.checklist_en if fast else [])
        ],
        refs=[
            MaskedRef(name=ref.name, masked=mask(ref.value))
            for ref in await reads.list_case_refs(case.id)
            if ref.name not in _HIDDEN_REFS
        ],
        verification=_verification_info(await reads.latest_verification(case.id), lang),
        brief=_brief_info(await reads.latest_brief(case.id), lang),
        calls=[
            await call_summary(call, lang) for call in await reads.list_calls(case.id)
        ],
    )


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
