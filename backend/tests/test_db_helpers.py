"""DB helper tests against a real Postgres. They run only when TEST_DATABASE_URL is
set, and it must not be the shared database: the tables are dropped and rebuilt."""

import asyncio
import secrets
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import pytest
from app.contracts import (
    CallState,
    Component,
    Event,
    EventType,
    FactSource,
    FactStatus,
    FastResult,
    GlossaryLookupJob,
    JobType,
    MessageDirection,
    MessageSender,
    ResearchFastJob,
    Sensitivity,
    Verification,
)
from app.db import deletes, jobs, reads, reset, tables
from app.db.engine import get_engine, session
from app.db.errors import UnverifiedNumber
from app.db.events import append_event
from app.db.ids import new_id
from app.db.messages import append_message
from app.db.progress import CaseStage
from app.db.schema import create_all, drop_all
from app.db.tables import utcnow
from app.db.writes import memory, orchestrator, phone, research
from app.settings import Settings, get_settings, to_asyncpg_url

TEST_DATABASE_URL = Settings().test_database_url

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set"
)

_schema_ready = False


@pytest.fixture(autouse=True)
async def test_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    global _schema_ready
    shared_host = urlsplit(Settings().async_database_url).hostname
    test_host = urlsplit(to_asyncpg_url(TEST_DATABASE_URL)).hostname
    if test_host == shared_host:
        pytest.exit("TEST_DATABASE_URL points at the shared database; refusing.")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", TEST_DATABASE_URL)
    get_settings.cache_clear()
    get_engine.cache_clear()
    if not _schema_ready:
        await drop_all()
        await create_all()
        _schema_ready = True
    yield
    # Each test runs on its own event loop; pooled connections can't cross loops.
    await get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _event(event_type: EventType, user_id: str, **ids: str) -> Event:
    return Event(
        event_id=new_id("event"),
        created_at=utcnow(),
        type=event_type,
        source=Component.ORCHESTRATOR,
        user_id=user_id,
        summary_en=str(event_type),
        **ids,
    )


def _verification(status: str, phone: str | None = "+15555550199") -> Verification:
    return Verification(
        status=status,
        official_phone=phone,
        letter_phone_matches=None,
        evidence=[],
        red_flags=[],
    )


async def _user_and_case() -> tuple[tables.User, tables.Case]:
    user = await orchestrator.get_or_create_user(f"+1555{secrets.randbelow(10**7):07d}")
    case = await research.create_case(new_id("case"), user.id, [])
    return user, case


async def test_get_or_create_user_is_idempotent() -> None:
    first = await orchestrator.get_or_create_user("+15555550111")
    second = await orchestrator.get_or_create_user("+15555550111")
    assert first.id == second.id


async def test_official_dial_number_refuses_unless_verified() -> None:
    _, case = await _user_and_case()
    with pytest.raises(UnverifiedNumber):
        await reads.official_dial_number(case.id)
    for status in ("pending", "suspicious", "unknown"):
        await research.save_verification(case.id, _verification(status))
        with pytest.raises(UnverifiedNumber):
            await reads.official_dial_number(case.id)
    await research.save_verification(case.id, _verification("verified"))
    assert await reads.official_dial_number(case.id) == "+15555550199"
    # The latest verdict wins: a later suspicious one takes the number away.
    await research.save_verification(case.id, _verification("suspicious"))
    with pytest.raises(UnverifiedNumber):
        await reads.official_dial_number(case.id)


async def test_official_dial_number_refuses_verified_without_phone() -> None:
    _, case = await _user_and_case()
    await research.save_verification(case.id, _verification("verified", phone=None))
    with pytest.raises(UnverifiedNumber):
        await reads.official_dial_number(case.id)


async def test_case_progress_through_the_demo() -> None:
    user, case = await _user_and_case()
    assert await reads.case_progress(case.id) == CaseStage.RECEIVED

    fast = await jobs.enqueue(
        ResearchFastJob(
            case_id=case.id, user_id=user.id, document_ids=[], user_language="es"
        ),
        Component.ORCHESTRATOR,
        user.id,
        case.id,
    )
    assert await reads.case_progress(case.id) == CaseStage.EXPLAINING

    result = FastResult(case_id=case.id, status="ok")
    await research.save_fast_result(case.id, result)
    await jobs.finish(fast.id, result)
    assert await reads.case_progress(case.id) == CaseStage.CHECKING

    await research.save_verification(case.id, _verification("verified"))
    assert await reads.case_progress(case.id) == CaseStage.AWAITING_CONSENT

    brief = await research.save_brief(case.id, {}, "note")
    yes = await append_message(
        user.id, MessageDirection.IN, MessageSender.USER, "SÍ", "es"
    )
    call = await phone.create_call(case.id, fast.id, brief.id, yes.id)
    assert await reads.case_progress(case.id) == CaseStage.CALLING
    await phone.set_call_state(call.id, CallState.HOLD)
    assert await reads.case_progress(case.id) == CaseStage.ON_HOLD
    await phone.set_call_state(call.id, CallState.CONNECTED)
    assert await reads.case_progress(case.id) == CaseStage.CONNECTED
    ended = await phone.set_call_state(call.id, CallState.ENDED)
    assert ended.ended_at is not None
    assert await reads.case_progress(case.id) == CaseStage.CALL_ENDED

    assert case.id in {c.id for c in await reads.list_active_cases(user.id)}
    await append_event(_event(EventType.CASE_CLOSED, user.id, case_id=case.id))
    assert await reads.case_progress(case.id) == CaseStage.CLOSED
    assert case.id not in {c.id for c in await reads.list_active_cases(user.id)}


async def test_claim_next_never_hands_one_job_to_two_claimers() -> None:
    user, case = await _user_and_case()
    enqueued = {
        (
            await jobs.enqueue(
                GlossaryLookupJob(term=f"term {i}", language="es", case_id=case.id),
                Component.RESEARCH_AGENT,
                user.id,
                case.id,
            )
        ).id
        for i in range(3)
    }
    claims = await asyncio.gather(
        *(jobs.claim_next(JobType.GLOSSARY_LOOKUP) for _ in range(8))
    )
    claimed = [job.id for job in claims if job is not None]
    assert len(claimed) == len(set(claimed)) == 3
    assert set(claimed) == enqueued
    assert all(job.status == "running" for job in claims if job is not None)
    payload = jobs.payload_of(next(job for job in claims if job is not None))
    assert isinstance(payload, GlossaryLookupJob)


SECRET_FACT = "Fled because of political persecution"


async def test_deletes_leave_only_ids_in_events() -> None:
    user, case = await _user_and_case()
    fact = await memory.add_fact(
        user.id,
        SECRET_FACT,
        "immigration",
        FactSource.USER_SAID,
        Sensitivity.SENSITIVE,
        FactStatus.PENDING_CONSENT,
    )
    media = await orchestrator.save_media(user.id, "image/jpeg", b"page one")
    document = await orchestrator.create_document(user.id, [media.id])
    await research.put_ref(case.id, "a_number", "A212345678")

    await deletes.delete_fact(fact.id)
    await deletes.delete_document(document.id)
    assert await reads.list_facts(user.id) == []
    assert await reads.get_document(document.id) is None
    assert await reads.get_media(media.id) is None

    counts = await deletes.delete_everything(user.id)
    assert counts["cases"] == 1 and counts["case_refs"] == 1
    assert await reads.get_case(case.id) is None
    assert await reads.get_user(user.id) is not None

    events = await reads.list_events(user.id)
    assert [e.type for e in events] == [
        EventType.FACT_DELETED,
        EventType.DOCUMENT_DELETED,
        EventType.USER_DELETED_ALL,
    ]
    assert events[0].data == {"fact_id": fact.id}
    dumped = " ".join(e.model_dump_json() for e in events)
    assert SECRET_FACT not in dumped
    assert "A212345678" not in dumped and "page one" not in dumped


async def test_list_events_since_is_exclusive() -> None:
    user, _ = await _user_and_case()
    first = await append_event(_event(EventType.CONSENT_REQUESTED, user.id))
    second = await append_event(_event(EventType.CONSENT_GIVEN, user.id))
    since = await reads.list_events(user.id, since=first.created_at)
    assert [e.event_id for e in since] == [second.event_id]


async def test_resolve_ref_accepts_placeholder() -> None:
    _, case = await _user_and_case()
    await research.put_ref(case.id, "receipt_number", "ZLA2690012345")
    assert await reads.resolve_ref(case.id, "<ref:receipt_number>") == "ZLA2690012345"
    async with session() as db:
        assert await db.get(tables.CaseRef, (case.id, "receipt_number")) is not None


async def test_seed_builds_a_case_awaiting_consent() -> None:
    case_id = await reset.seed()
    assert await reads.case_progress(case_id) == CaseStage.AWAITING_CONSENT
    assert await reads.resolve_ref(case_id, "a_number") == "A212345678"
