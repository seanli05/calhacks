"""Live end to end: the demo letter through the real worker, database, model and web.

Runs only with RESEARCH_E2E=1 and TEST_DATABASE_URL (a Neon branch, never the
shared database): it drops and rebuilds the tables there, makes real model calls
and fetches from the web. Dev-only, so it writes as the orchestrator to create its
input. Takes a few minutes.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from app.contracts import (
    CaseBrief,
    Component,
    FastResult,
    JobStatus,
    JobType,
    QuestionAnswer,
    ResearchFastJob,
    ResearchQuestionJob,
)
from app.db import jobs, reads, tables
from app.db.engine import get_engine, session
from app.db.ids import new_id
from app.db.progress import CaseStage
from app.db.schema import create_all, drop_all
from app.db.writes import orchestrator
from app.main import app
from app.research.worker import ResearchWorker, close_deps, real_deps
from app.settings import Settings, get_settings, to_asyncpg_url
from sqlmodel import select

TEST_DATABASE_URL = Settings().test_database_url
LETTER = (
    Path(__file__).resolve().parents[1]
    / "fixtures/research/letters/i797c_asylum_interview"
)
EXPECTED = json.loads((LETTER / "expected.json").read_text())
DEMO_DIAL = "+15555550100"
USER_NUMBER = "+15555550123"
DEEP_WAIT_S = 240.0
QUESTION_WAIT_S = 90.0
DECLINES = {
    "not_confirmed",
    "declined_legal_advice",
    "declined_asylum_claim",
    "out_of_scope",
}

pytestmark = pytest.mark.skipif(
    os.environ.get("RESEARCH_E2E") != "1" or not TEST_DATABASE_URL,
    reason="RESEARCH_E2E=1 and TEST_DATABASE_URL not set",
)


@pytest.fixture(autouse=True)
async def test_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    shared_host = urlsplit(Settings().async_database_url).hostname
    test_host = urlsplit(to_asyncpg_url(TEST_DATABASE_URL)).hostname
    if test_host == shared_host:
        pytest.exit("TEST_DATABASE_URL points at the shared database; refusing.")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", TEST_DATABASE_URL)
    monkeypatch.setenv("DEMO_DIAL_NUMBER", "")
    get_settings.cache_clear()
    get_engine.cache_clear()
    await drop_all()
    await create_all()
    yield
    await get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


async def _case_jobs(case_id: str) -> list[tables.Job]:
    async with session() as db:
        query = (
            select(tables.Job)
            .where(tables.Job.case_id == case_id)
            .order_by(tables.Job.created_at)
        )
        return list((await db.execute(query)).scalars())


async def _wait_for_job(
    case_id: str, job_type: JobType, timeout_s: float
) -> tables.Job:
    async with asyncio.timeout(timeout_s):
        while True:
            for job in await _case_jobs(case_id):
                if job.type == job_type and job.status in (
                    JobStatus.DONE,
                    JobStatus.FAILED,
                ):
                    return job
            await asyncio.sleep(2)


async def test_demo_letter_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    # The orchestrator's side: a user, the photo, a document, and H1.
    user = await orchestrator.get_or_create_user(USER_NUMBER)
    media = await orchestrator.save_media(
        user.id, "image/png", (LETTER / "page_1.png").read_bytes(), None
    )
    document = await orchestrator.create_document(user.id, [media.id])
    case_id = new_id("case")
    await jobs.enqueue(
        ResearchFastJob(
            case_id=case_id,
            user_id=user.id,
            document_ids=[document.id],
            user_language="es",
        ),
        Component.ORCHESTRATOR,
        user.id,
        case_id,
    )

    worker = ResearchWorker(real_deps(get_settings()))
    worker.start()
    try:
        deep = await _wait_for_job(case_id, JobType.RESEARCH_DEEP, DEEP_WAIT_S)
        assert deep.status == JobStatus.DONE, deep.error

        # R1, refs, verdict, brief
        assert await reads.case_progress(case_id) == CaseStage.AWAITING_CONSENT
        case = await reads.get_case(case_id)
        assert case is not None and case.fast_result is not None
        r1 = FastResult.model_validate(case.fast_result)
        assert r1.doc_type and r1.explanation_en
        assert r1.key_facts
        for fact in r1.key_facts:
            assert (fact.value is None) != (fact.ref is None)
            if fact.field in EXPECTED["sensitive_fields"]:
                assert fact.ref is not None, fact.field
        assert await reads.list_case_refs(case_id)
        brief_row = await reads.latest_brief(case_id)
        assert brief_row is not None
        brief = CaseBrief.model_validate(brief_row.brief)
        assert brief.brief_id == brief_row.id
        assert brief.call_goal_en and brief.questions_to_ask

        # Events
        events = await reads.list_events(user.id)
        by_type = {e.type: e for e in events}
        for wanted in (
            "research.fast_done",
            "research.deep_done",
            "verification.verified",
        ):
            assert wanted in by_type, wanted
        assert by_type["verification.verified"].data.get("source")
        assert all(e.user_id == user.id for e in events)

        # Demo dial override (C40), and the real verified number without it.
        verification = await reads.latest_verification(case_id)
        assert verification is not None and verification.official_phone
        assert await reads.official_dial_number(case_id) == verification.official_phone
        monkeypatch.setenv("DEMO_DIAL_NUMBER", DEMO_DIAL)
        get_settings.cache_clear()
        assert await reads.official_dial_number(case_id) == DEMO_DIAL
        monkeypatch.setenv("DEMO_DIAL_NUMBER", "")
        get_settings.cache_clear()

        # A chat question about the same case.
        await jobs.enqueue(
            ResearchQuestionJob(
                user_id=user.id,
                case_id=case_id,
                question_en="What should I bring to my asylum interview?",
            ),
            Component.ORCHESTRATOR,
            user.id,
            case_id,
        )
        question = await _wait_for_job(
            case_id, JobType.RESEARCH_QUESTION, QUESTION_WAIT_S
        )
        assert question.status == JobStatus.DONE, question.error
        answer = QuestionAnswer.model_validate(question.result)
        if answer.status == "answered":
            assert answer.sources
        else:
            assert answer.status in DECLINES
    finally:
        await worker.stop()
        await close_deps(worker.deps)

    # Nothing sensitive in any event, job, verification or brief.
    async with session() as db:
        verifications = (
            await db.execute(
                select(tables.Verification).where(
                    tables.Verification.case_id == case_id
                )
            )
        ).scalars()
        written = json.dumps(
            [e.model_dump(mode="json") for e in await reads.list_events(user.id)]
            + [[j.payload, j.result, j.error] for j in await _case_jobs(case_id)]
            + [v.result for v in verifications]
            + [brief_row.brief, brief_row.handoff_note],
            default=str,
        ).lower()
    for secret in EXPECTED["forbidden_strings"]:
        assert secret.lower() not in written, "a sensitive value leaked"

    # The dashboard API, in the same process.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        detail = await api.get(f"/api/cases/{case_id}", params={"lang": "es"})
        assert detail.status_code == 200
        body = detail.json()
        assert body["issuer"]
        assert body["verification"]["evidence"][0].startswith("https://")
        assert body["refs"] and all("•" in ref["masked"] for ref in body["refs"])
        assert body["brief"]["questions_to_ask"]

        feed = await api.get(f"/api/users/{user.id}/feed", params={"lang": "es"})
        assert feed.status_code == 200
        items = feed.json()
        assert items
        hidden = {"research.search", "research.fetch", "research.check"}
        assert not [i for i in items if i["type"] in hidden]
        untranslated = [
            i["type"] for i in items if i["text"]["text"] == i["text"]["en"]
        ]
        assert not untranslated, untranslated
