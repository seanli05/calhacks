"""Building blocks the case list and the case view share: R1, the appointment, the
letter's pages, and call summaries."""

import asyncio
import logging

from pydantic import ValidationError

from app.api.common import localize
from app.api.models import Appointment, CallReportInfo, CallSummary
from app.contracts import CallReport, Event, EventType, FastResult
from app.db import reads, tables
from app.db.errors import NotFound

logger = logging.getLogger(__name__)


def fast_result_of(case: tables.Case) -> FastResult | None:
    """R1 from `cases.fast_result`; None until research has written a valid one."""
    if case.fast_result is None:
        return None
    try:
        return FastResult.model_validate(case.fast_result)
    except ValidationError as exc:
        logger.warning("case %s: invalid fast_result (%s)", case.id, exc)
        return None


async def appointment_of(case_id: str, fast: FastResult | None) -> Appointment | None:
    if fast is None or fast.appointment is None:
        return None
    location = None
    if fast.appointment.location_ref:
        try:
            location = await reads.resolve_ref(case_id, fast.appointment.location_ref)
        except NotFound:
            location = None
    return Appointment(
        date=fast.appointment.date, time=fast.appointment.time, location=location
    )


async def first_document(case: tables.Case) -> tables.Document | None:
    """The case's letter; None once it's deleted."""
    if not case.document_ids:
        return None
    return await reads.get_document(case.document_ids[0])


def page_media_ids(document: tables.Document | None) -> list[str]:
    if document is None:
        return []
    return [page["media_id"] for page in document.pages if "media_id" in page]


def _report_of(call: tables.Call, lang: str) -> CallReportInfo | None:
    if call.report is None:
        return None
    try:
        report = CallReport.model_validate(call.report)
    except ValidationError as exc:
        logger.warning("call %s: invalid report (%s)", call.id, exc)
        return None
    return CallReportInfo(
        outcome=report.outcome,
        reference_number=report.reference_number,
        rep_name=report.rep_name,
        next_steps=[localize(step, lang) for step in report.next_steps_en],
        new_deadlines=report.new_deadlines,
        followup_needed=report.followup_needed,
    )


CallReads = tuple[tables.Call, Event | None, tables.Transcript | None]


async def call_reads(call: tables.Call) -> CallReads:
    """What a call summary needs from the database: the first hold event and the
    transcript. Kept apart from `build_call_summary` so it can run before the
    language is known."""
    on_hold, transcript = await asyncio.gather(
        reads.first_event(call.id, EventType.CALL_ON_HOLD),
        reads.get_transcript(call.id),
    )
    return call, on_hold, transcript


async def call_summary(call: tables.Call, lang: str) -> CallSummary:
    return build_call_summary(await call_reads(call), lang)


def build_call_summary(fetched: CallReads, lang: str) -> CallSummary:
    call, on_hold, transcript = fetched
    return CallSummary(
        id=call.id,
        state=call.state,
        outcome=call.outcome,
        started_at=call.started_at,
        ended_at=call.ended_at,
        hold_started_at=on_hold.created_at if on_hold else None,
        report=_report_of(call, lang),
        transcript_id=transcript.id if transcript else None,
    )
