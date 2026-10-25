"""The fake research agent (Goal 4.4) on fakes, end to end from a letter."""

import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from app.contracts import (
    DeepResult,
    EventType,
    FastResult,
    JobStatus,
    JobType,
)
from app.dev.fake_research import FakeResearch, Pacing
from app.main import app
from app.orchestrator.letters import Letters
from app.orchestrator.pipe import InboundPipe
from app.settings import Settings, get_settings
from fastapi.testclient import TestClient
from whatsapp_fakes import FakeDB, inbound, use_spanish, wait_for_batches

MOCK_AGENCY = "+15005550006"
FIXTURE_PHONE = "+18003755283"


async def until(condition: Callable[[], bool]) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    pytest.fail("condition never became true")


async def test_fake_research_finishes_both_passes_from_a_letter(
    pipe: InboundPipe, letters: Letters, db: FakeDB, research_db: dict[str, Any]
) -> None:
    user = await use_spanish(db)
    await pipe.handle(inbound(photos=1))
    await wait_for_batches()
    [fast_job] = db.jobs_of(JobType.RESEARCH_FAST)

    fake = FakeResearch(MOCK_AGENCY, Pacing(fast_s=0.01, deep_s=0.01, poll_s=0.01))
    assert fake.start(run_for_s=1)
    assert not fake.start(run_for_s=1)
    await until(
        lambda: any(
            j.status == JobStatus.DONE for j in db.jobs_of(JobType.RESEARCH_DEEP)
        )
    )

    # The fast pass: the orchestrator's case_id, refs never in the result.
    [case] = db.cases
    r1 = FastResult.model_validate(db.jobs[fast_job.id].result)
    assert case.id == r1.case_id == fast_job.case_id
    assert case.document_ids == [db.documents[0].id]
    assert set(research_db["refs"]) == {
        "receipt_number",
        "a_number",
        "interview_location",
    }
    # The deep pass: our mock agency line, never the fixture's real USCIS number.
    [deep_job] = db.jobs_of(JobType.RESEARCH_DEEP)
    r2 = DeepResult.model_validate(db.jobs[deep_job.id].result)
    assert r2.verification.official_phone == MOCK_AGENCY
    assert research_db["verifications"][0].official_phone == MOCK_AGENCY
    assert FIXTURE_PHONE not in str(db.jobs[deep_job.id].result)
    assert r2.brief_id == research_db["briefs"][0].id
    assert {e.type for e in db.events} >= {
        EventType.CASE_CREATED,
        EventType.RESEARCH_FAST_DONE,
        EventType.VERIFICATION_VERIFIED,
        EventType.RESEARCH_DEEP_DONE,
    }
    assert all(e.user_id == user.id and e.case_id == case.id for e in db.events)

    # The orchestrator noticed: the letter is now found through its case row.
    await asyncio.sleep(0.05)
    assert await letters.active_letter(user.id) == db.documents[0].id


async def test_fake_research_without_a_mock_line_saves_no_phone(
    db: FakeDB, research_db: dict[str, Any], letters: Letters
) -> None:
    user = await use_spanish(db)
    await letters.start(user.id, "doc_1")

    fake = FakeResearch(None, Pacing(fast_s=0.01, deep_s=0.01, poll_s=0.01))
    fake.start(run_for_s=1)
    await until(lambda: bool(research_db["verifications"]))

    assert research_db["verifications"][0].official_phone is None


@pytest.fixture
def client_with() -> Iterator[Callable[[bool], TestClient]]:
    def _make(dev_endpoints: bool) -> TestClient:
        settings = Settings(_env_file=None, dev_endpoints=dev_endpoints)
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_fake_research_endpoint_is_off_by_default(
    client_with: Callable[[bool], TestClient],
) -> None:
    assert client_with(False).post("/dev/fake-research").status_code == 404


def test_fake_research_endpoint_refuses_requests_through_ngrok(
    client_with: Callable[[bool], TestClient],
) -> None:
    response = client_with(True).post(
        "/dev/fake-research", headers={"X-Forwarded-For": "3.84.5.205"}
    )
    assert response.status_code == 403
