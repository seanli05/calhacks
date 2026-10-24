"""The memory page (what we know about you): profile, facts, documents, transcripts,
and the deletes behind each Delete button (C26)."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Response

from app.api.case_views import page_media_ids
from app.api.common import LangQuery, localize, resolve_language
from app.api.models import DocumentInfo, FactInfo, Memory, TranscriptInfo
from app.contracts import FactStatus
from app.db import deletes, reads, tables
from app.db.errors import NotFound

router = APIRouter()

_SHOWN_FACTS = (FactStatus.ACTIVE, FactStatus.PENDING_CONSENT)


@router.get("/users/{user_id}/memory")
async def memory(user_id: str, lang: LangQuery = None) -> Memory:
    lang = await resolve_language(user_id, lang)
    profile = await reads.get_profile(user_id)
    case_of = {
        document_id: case
        for case in await reads.list_cases(user_id)
        for document_id in case.document_ids
    }
    return Memory(
        profile={k: str(v) for k, v in (profile.fields if profile else {}).items()},
        facts=[
            FactInfo(
                id=fact.id,
                fact=localize(fact.fact, lang),
                category=fact.category,
                source=fact.source,
                sensitivity=fact.sensitivity,
                status=fact.status,
                recorded_at=fact.recorded_at,
            )
            for fact in await reads.list_facts(user_id, _SHOWN_FACTS)
        ],
        documents=[
            _document_info(document, case_of.get(document.id))
            for document in await reads.list_documents(user_id)
        ],
        transcripts=[
            TranscriptInfo(
                id=transcript.id,
                call_id=transcript.call_id,
                case_id=case_id,
                created_at=transcript.created_at,
            )
            for transcript, case_id in await reads.list_transcripts(user_id)
        ],
    )


def _document_info(document: tables.Document, case: tables.Case | None) -> DocumentInfo:
    return DocumentInfo(
        id=document.id,
        doc_type=case.doc_type if case else None,
        case_id=case.id if case else None,
        page_media_ids=page_media_ids(document),
        created_at=document.created_at,
    )


async def _delete(helper: Callable[[str], Awaitable[object]], row_id: str) -> Response:
    try:
        await helper(row_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(fact_id: str) -> Response:
    return await _delete(deletes.delete_fact, fact_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str) -> Response:
    return await _delete(deletes.delete_document, document_id)


@router.delete("/transcripts/{transcript_id}", status_code=204)
async def delete_transcript(transcript_id: str) -> Response:
    return await _delete(deletes.delete_transcript, transcript_id)


@router.post("/users/{user_id}/delete-everything")
async def delete_everything(user_id: str) -> dict[str, int]:
    try:
        return await deletes.delete_everything(user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
