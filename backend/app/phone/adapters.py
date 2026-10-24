"""Real adapters for the ports that exist today: the database and the relay.

Each is a pass-through to the shared helpers, so the import rule still holds: the
phone agent writes only through `app.db.writes.phone`. The `Telephony` adapter
comes with real audio (Phase 2).
"""

from collections.abc import Sequence
from typing import Any

from app.contracts import (
    AskUserReply,
    AskUserRequest,
    CallJob,
    CallReport,
    CaseBrief,
    Event,
)
from app.contracts.common import (
    BriefId,
    CallId,
    CallState,
    CaseId,
    JobId,
    TranscriptId,
    UserId,
)
from app.db import reads
from app.db.errors import NotFound
from app.db.events import append_event
from app.db.writes import phone as writes
from app.phone.guard import GUARDED_REFS
from app.phone.ports import TranscriptLine
from app.relay.ask_user import ask_user


class DbNumberSource:
    async def official_dial_number(self, case_id: CaseId) -> str:
        return await reads.official_dial_number(case_id)

    async def user_number(self, user_id: UserId) -> str:
        user = await reads.get_user(user_id)
        if user is None:
            raise NotFound(f"users {user_id} not found")
        return user.whatsapp_number


class DbCaseReader:
    async def get_brief(self, brief_id: BriefId) -> dict[str, Any]:
        """Validated against `CaseBrief` (docs/specs/case-brief.md), so a brief that
        breaks the contract (e.g. without the required `must_not_do`) stops the
        call before it dials. Returned as JSON; the runner reads it defensively."""
        row = await reads.get_brief(brief_id)
        if row is None:
            raise NotFound(f"case_briefs {brief_id} not found")
        CaseBrief.model_validate(row.brief)
        return row.brief


class DbCallStore:
    async def create_call(self, job_id: JobId, job: CallJob) -> CallId:
        call = await writes.create_call(
            job.case_id, job_id, job.brief_id, job.consent_message_id
        )
        return call.id

    async def set_state(
        self, call_id: CallId, state: CallState, twilio_call_sid: str | None = None
    ) -> None:
        await writes.set_call_state(call_id, state, twilio_call_sid)

    async def save_transcript(
        self, call_id: CallId, lines: Sequence[TranscriptLine]
    ) -> TranscriptId:
        rows = [line.model_dump(mode="json") for line in lines]
        transcript = await writes.save_transcript(call_id, rows)
        return transcript.id

    async def save_report(self, call_id: CallId, report: CallReport) -> None:
        await writes.save_call_report(call_id, report)


class DbEventLog:
    async def append(self, event: Event) -> None:
        await append_event(event)


class RelayAskUser:
    async def ask_user(self, request: AskUserRequest) -> AskUserReply:
        return await ask_user(request)


async def load_blocked_values(case_id: CaseId) -> list[str]:
    """The case's identifier values, for `GuardedTelephony` only. Never log them or
    pass them anywhere else (C35)."""
    values = []
    for name in GUARDED_REFS:
        try:
            values.append(await reads.resolve_ref(case_id, name))
        except NotFound:
            continue
    return values
