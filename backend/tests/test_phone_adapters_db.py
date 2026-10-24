"""The phone agent's DB adapters against a real Postgres. Like test_db_helpers, they
run only when TEST_DATABASE_URL is set; they reuse its schema fixture."""

from datetime import UTC, datetime

import pytest
from app.contracts import CallJob, Component, EventType, MessageDirection, MessageSender
from app.contracts.common import CallState
from app.db import jobs, reads
from app.db.errors import NotFound, UnverifiedNumber
from app.db.messages import append_message
from app.db.writes import research
from app.phone.adapters import (
    DbCallStore,
    DbCaseReader,
    DbEventLog,
    DbNumberSource,
    load_blocked_values,
)
from app.phone.call_events import CallEvents
from app.phone.clock import SystemClock
from app.phone.ports import TranscriptLine
from test_db_helpers import TEST_DATABASE_URL, _user_and_case, _verification, test_db

__all__ = ["test_db"]  # the autouse schema fixture, imported for its side effect

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set"
)


async def test_adapters_run_a_call_through_the_db() -> None:
    user, case = await _user_and_case()
    numbers = DbNumberSource()
    with pytest.raises(UnverifiedNumber):
        await numbers.official_dial_number(case.id)
    await research.save_verification(case.id, _verification("verified"))
    assert await numbers.official_dial_number(case.id) == "+15555550199"
    assert await numbers.user_number(user.id) == user.whatsapp_number

    brief = await research.save_brief(case.id, {"call_goal_en": "Confirm"}, "note")
    assert await DbCaseReader().get_brief(brief.id) == {"call_goal_en": "Confirm"}
    with pytest.raises(NotFound):
        await DbCaseReader().get_brief("brief_missing")

    yes = await append_message(
        user.id, MessageDirection.IN, MessageSender.USER, "SÍ", "es"
    )
    job = CallJob(
        case_id=case.id,
        user_id=user.id,
        brief_id=brief.id,
        user_language="es",
        consent_at=datetime.now(UTC),
        consent_message_id=yes.id,
        max_hold_minutes=60,
    )
    job_row = await jobs.enqueue(job, Component.ORCHESTRATOR, user.id, case.id)
    store = DbCallStore()
    call_id = await store.create_call(job_row.id, job)
    await store.set_state(call_id, CallState.MENU, twilio_call_sid="CA123")
    line = TranscriptLine(at=datetime.now(UTC), speaker="agency", text="Hello")
    transcript_id = await store.save_transcript(call_id, [line])
    call = await reads.get_call(call_id)
    assert (call.state, call.twilio_call_sid) == (CallState.MENU, "CA123")
    assert (await reads.get_transcript(call_id)).id == transcript_id

    events = CallEvents(DbEventLog(), SystemClock(), user.id, case.id, job_row.id)
    await events.for_call(call_id).append(EventType.CALL_DIALING, "Calling USCIS")
    assert [e.type for e in await reads.list_events(user.id)] == [
        EventType.CALL_DIALING
    ]


async def test_load_blocked_values_skips_missing_refs() -> None:
    _, case = await _user_and_case()
    await research.put_ref(case.id, "a_number", "A212345678")
    await research.put_ref(case.id, "interview_location", "Tustin")
    assert await load_blocked_values(case.id) == ["A212345678"]
