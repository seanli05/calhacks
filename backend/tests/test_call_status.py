"""Call-status messages (P2, C36) on fakes: the fixed rules, the watcher that applies
them, and the guards on the dev endpoint that starts a fake call."""

import asyncio
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import pytest
from app.contracts import CallJob, CallState, CaseBrief, Component, Event, EventType
from app.db import tables
from app.db.ids import new_id
from app.db.tables import utcnow
from app.dev.fake_call import Pacing, run_fake_call
from app.main import app
from app.orchestrator.call_status import CallStatusWatcher, StatusRules
from app.relay.ask_user import AskUser
from app.settings import Settings, get_settings
from fastapi.testclient import TestClient
from whatsapp_fakes import FakeDB, FakeWhatsApp, use_spanish

T0 = datetime(2026, 10, 25, 10, 0, tzinfo=utcnow().tzinfo)


def event(
    event_type: EventType,
    at: datetime = T0,
    call_id: str = "call_1",
    user_id: str = "user_1",
) -> Event:
    return Event(
        event_id=new_id("event"),
        created_at=at,
        type=event_type,
        source=Component.PHONE_AGENT,
        user_id=user_id,
        call_id=call_id,
        summary_en=str(event_type),
    )


# The rules


def test_human_detected_is_always_sent() -> None:
    rules = StatusRules()
    assert rules.template_for(event(EventType.CALL_HUMAN_DETECTED)) == (
        "call.human_detected"
    )
    assert rules.template_for(event(EventType.CALL_HUMAN_DETECTED)) == (
        "call.human_detected"
    )


@pytest.mark.parametrize(
    "event_type", [EventType.CALL_DIALING, EventType.CALL_USER_UNREACHABLE]
)
def test_dialing_and_unreachable_are_sent_once_per_call(event_type: EventType) -> None:
    rules = StatusRules()
    assert rules.template_for(event(event_type)) == str(event_type)
    assert rules.template_for(event(event_type)) is None
    assert rules.template_for(event(event_type, call_id="call_2")) == str(event_type)


def test_on_hold_at_most_once_every_ten_minutes_per_call() -> None:
    rules = StatusRules()
    on_hold = EventType.CALL_ON_HOLD
    assert rules.template_for(event(on_hold, T0)) == "call.on_hold"
    assert rules.template_for(event(on_hold, T0 + timedelta(minutes=9))) is None
    assert rules.template_for(event(on_hold, T0 + timedelta(minutes=10))) == (
        "call.on_hold"
    )
    # Another call keeps its own clock.
    assert rules.template_for(event(on_hold, T0, call_id="call_2")) == "call.on_hold"


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.CALL_MENU_HEARD,
        EventType.CALL_MENU_CHOICE,
        EventType.CALL_ASK_USER,
        EventType.CALL_USER_JOINED,
        EventType.CALL_ENDED,
    ],
)
def test_other_call_events_stay_on_the_dashboard(event_type: EventType) -> None:
    assert StatusRules().template_for(event(event_type)) is None


# The watcher


async def wait_until_stopped(watcher: CallStatusWatcher, user_id: str) -> None:
    for _ in range(200):
        if not watcher.is_watching(user_id):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("watcher didn't stop")


async def test_watcher_relays_a_call_and_stops_at_call_ended(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    watcher = CallStatusWatcher(whatsapp, poll_interval_s=0.01)
    start = utcnow()
    db.events.append(event(EventType.CALL_DIALING, start, user_id=user.id))
    db.events.append(event(EventType.CALL_ASK_USER, start, user_id=user.id))

    watcher.watch(user.id, since=start - timedelta(seconds=1))
    watcher.watch(user.id, since=start)  # already watching: no second watcher
    for minute, event_type in enumerate(
        [
            EventType.CALL_ON_HOLD,
            EventType.CALL_ON_HOLD,
            EventType.CALL_ON_HOLD,
            EventType.CALL_HUMAN_DETECTED,
            EventType.CALL_ENDED,
            EventType.CALL_ON_HOLD,  # after the end: not relayed
        ],
        start=1,
    ):
        await asyncio.sleep(0.02)
        at = start + timedelta(minutes=minute)
        db.events.append(event(event_type, at, user_id=user.id))
    await wait_until_stopped(watcher, user.id)

    assert db.outbound_templates() == [
        "call.dialing",
        "call.on_hold",
        "call.human_detected",
    ]
    assert whatsapp.sent[0] == "Estoy llamando a USCIS ahora."


async def test_watcher_ignores_events_before_it_started(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    watcher = CallStatusWatcher(whatsapp, poll_interval_s=0.01)
    start = utcnow()
    earlier = start - timedelta(seconds=1)  # a previous call
    db.events.append(event(EventType.CALL_DIALING, earlier, user_id=user.id))
    db.events.append(event(EventType.CALL_ENDED, earlier, user_id=user.id))

    watcher.watch(user.id, since=start)
    db.events.append(
        event(EventType.CALL_ENDED, start + timedelta(seconds=1), user_id=user.id)
    )
    await wait_until_stopped(watcher, user.id)

    assert db.outbound_templates() == []


# The dev endpoint


@pytest.fixture
def client_with() -> Iterator[Callable[[bool], TestClient]]:
    def _make(dev_endpoints: bool) -> TestClient:
        settings = Settings(_env_file=None, dev_endpoints=dev_endpoints)
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_fake_call_endpoint_is_off_by_default(
    client_with: Callable[[bool], TestClient],
) -> None:
    response = client_with(False).post(
        "/dev/fake-call", json={"number": "+15105550123"}
    )
    assert response.status_code == 404


def test_fake_call_endpoint_refuses_requests_through_ngrok(
    client_with: Callable[[bool], TestClient],
) -> None:
    response = client_with(True).post(
        "/dev/fake-call",
        json={"number": "+15105550123"},
        headers={"X-Forwarded-For": "3.84.5.205"},
    )
    assert response.status_code == 403


# The fake call itself


async def test_fake_call_plays_the_script_and_never_leaves_a_runnable_job(
    db: FakeDB, whatsapp: FakeWhatsApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs the dev fake end to end on fakes: no user answer, so ask_user times out."""
    user = await use_spanish(db)
    job_status: dict[str, str] = {}

    async def create_case(case_id: str, user_id: str, documents: list) -> tables.Case:
        case = tables.Case(id=case_id, user_id=user_id)
        db.cases.append(case)
        return case

    async def save_brief(
        case_id: str, brief: CaseBrief, note: str | None = None
    ) -> tables.CaseBrief:
        return tables.CaseBrief(
            id=brief.brief_id,
            case_id=case_id,
            brief=brief.model_dump(mode="json"),
            handoff_note=note or brief.handoff_note,
        )

    async def enqueue(payload: CallJob, *args: object) -> tables.Job:
        job = tables.Job(type=payload.job, created_by="orchestrator", user_id=user.id)
        job_status[job.id] = "queued"
        return job

    async def fail(job_id: str, error: str) -> None:
        job_status[job_id] = "failed"

    async def create_call(case_id: str, *ids: str) -> tables.Call:
        call = tables.Call(
            case_id=case_id, job_id=ids[0], brief_id=ids[1], consent_message_id=ids[2]
        )
        db.calls[call.id] = call
        return call

    async def set_call_state(call_id: str, state: str) -> None:
        db.calls[call_id].state = state

    monkeypatch.setattr("app.db.writes.research.create_case", create_case)
    monkeypatch.setattr("app.db.writes.research.save_brief", save_brief)
    monkeypatch.setattr("app.db.jobs.enqueue", enqueue)
    monkeypatch.setattr("app.db.jobs.fail", fail)
    monkeypatch.setattr("app.db.writes.phone.create_call", create_call)
    monkeypatch.setattr("app.db.writes.phone.set_call_state", set_call_state)
    monkeypatch.setattr("app.dev.fake_call.append_message", db.append_message)
    monkeypatch.setattr("app.dev.fake_call.append_event", db.append_event)

    watcher = CallStatusWatcher(whatsapp, poll_interval_s=0.01)
    await run_fake_call(
        user,
        AskUser(whatsapp),
        watcher,
        Pacing(step_s=0.05, on_hold_count=3, ask_timeout_s=1),
    )
    await wait_until_stopped(watcher, user.id)

    assert list(job_status.values()) == ["failed"]
    [call] = db.calls.values()
    assert call.state == CallState.ENDED
    assert db.event_types()[-2:] == [EventType.CALL_ENDED, EventType.CASE_CLOSED]
    assert all(e.call_id == call.id for e in db.events)
    assert db.outbound_templates() == [
        None,  # the "[dev] fake call" note the consent pointer references
        "call.dialing",
        "ask_user.menu_choice",
        "call.on_hold",
        "call.human_detected",
    ]
