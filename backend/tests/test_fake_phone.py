"""The fake phone worker (Goal 6 checkpoint) on fakes: a YES through the pipe, the
scripted call with its ask_user question, the status messages, and the summary."""

import asyncio
import time
from typing import Any

import pytest
from app.contracts import CallReport, JobStatus, JobType, VerificationStatus
from app.db import tables
from app.dev.fake_call import Pacing
from app.dev.fake_phone import FakePhone
from app.orchestrator.consent import ConsentGate
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.pipe import InboundPipe
from app.relay.ask_user import AskUser
from whatsapp_fakes import FakeDB, inbound, use_spanish

PACING = Pacing(step_s=0.02, on_hold_count=2, ask_timeout_s=5)


@pytest.fixture
def phone_db(db: FakeDB, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fakes for the phone writes; returns what was written."""
    written: dict[str, Any] = {"reports": [], "transcripts": []}

    async def create_call(case_id: str, *ids: str) -> tables.Call:
        call = tables.Call(
            case_id=case_id, job_id=ids[0], brief_id=ids[1], consent_message_id=ids[2]
        )
        db.calls[call.id] = call
        return call

    async def set_call_state(call_id: str, state: str) -> None:
        db.calls[call_id].state = state

    async def save_transcript(call_id: str, lines: list) -> tables.Transcript:
        transcript = tables.Transcript(call_id=call_id, lines=lines)
        written["transcripts"].append(transcript)
        return transcript

    async def save_call_report(call_id: str, report: CallReport) -> None:
        written["reports"].append(report)

    for name, fake in [
        ("create_call", create_call),
        ("set_call_state", set_call_state),
        ("save_transcript", save_transcript),
        ("save_call_report", save_call_report),
    ]:
        monkeypatch.setattr(f"app.db.writes.phone.{name}", fake)
    for name in ("claim_next", "finish", "fail"):
        monkeypatch.setattr(f"app.db.jobs.{name}", getattr(db, name))
    monkeypatch.setattr("app.dev.fake_call.append_event", db.append_event)
    return written


async def until(condition: Any, timeout_s: float = 3.0) -> None:
    """Wait on a deadline, not a count: on Windows a busy loop runs sub-15 ms sleeps
    at once, so counted waits end early."""
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("condition never became true")
        await asyncio.sleep(0.01)


async def test_yes_to_summary_on_the_fake_phone(
    db: FakeDB,
    pipe: InboundPipe,
    ask_user: AskUser,
    consent: ConsentGate,
    job_watcher: JobWatcher,
    phone_db: dict[str, Any],
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    assert await consent.request(user, case.id) is None
    await pipe.handle(inbound("1"))
    [job] = db.jobs_of(JobType.CALL)

    # Keep a reference: the loop holds tasks weakly.
    fake_phone = FakePhone(ask_user, PACING, poll_s=0.01)
    fake_phone.start(5)
    await until(lambda: "ask_user.menu_choice" in db.outbound_templates())
    await pipe.handle(inbound("2"))
    await until(lambda: not job_watcher.is_watching(job.id))

    [call] = db.calls.values()
    assert call.consent_message_id == job.payload["consent_message_id"]
    assert db.jobs[job.id].status == JobStatus.DONE
    [report] = phone_db["reports"]
    assert report.call_id == call.id
    templates = db.outbound_templates()
    assert templates[templates.index("consent.request") :] == [
        "consent.request",
        "consent.given",
        "call.dialing",
        "ask_user.menu_choice",
        "call.on_hold",  # one: the 10-minute rule drops the second
        "call.human_detected",
        None,  # the summary, free text from the orchestrator
    ]
    assert "R-55821" in db.messages[-1].body_original


async def test_fake_phone_refuses_a_case_without_a_verified_number(
    db: FakeDB, ask_user: AskUser, phone_db: dict[str, Any]
) -> None:
    """Rule 2 holds even in the fake: no verified number, no call."""
    user = await use_spanish(db)
    case = db.add_verified_case(user, status=VerificationStatus.UNKNOWN)
    job = tables.Job(
        type=JobType.CALL,
        created_by="orchestrator",
        user_id=user.id,
        case_id=case.id,
        payload={
            "job": "call",
            "case_id": case.id,
            "user_id": user.id,
            "brief_id": "brief_1",
            "user_language": "es",
            "consent_at": "2026-10-25T10:02:00Z",
            "consent_message_id": "msg_1",
            "max_hold_minutes": 60,
        },
    )
    db.jobs[job.id] = job

    fake_phone = FakePhone(ask_user, PACING, poll_s=0.01)
    fake_phone.start(1)
    await until(lambda: db.jobs[job.id].status == JobStatus.FAILED)

    assert db.calls == {}
