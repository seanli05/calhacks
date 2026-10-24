import asyncio

import pytest
from app.contracts import JobType
from app.db import tables
from app.research import worker
from app.research.worker import ResearchWorker

from research.fakes import fake_deps


def _job(job_type: JobType, job_id: str) -> tables.Job:
    return tables.Job(
        id=job_id, type=job_type, created_by="test", user_id="user_1", payload={}
    )


async def test_worker_runs_each_type_and_survives_a_failing_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = {
        JobType.RESEARCH_FAST: [_job(JobType.RESEARCH_FAST, "job_bad")],
        JobType.RESEARCH_DEEP: [_job(JobType.RESEARCH_DEEP, "job_deep")],
        JobType.RESEARCH_QUESTION: [_job(JobType.RESEARCH_QUESTION, "job_q")],
    }
    ran: list[str] = []
    done = asyncio.Event()

    async def claim_next(job_type: JobType) -> tables.Job | None:
        return queue[job_type].pop() if queue[job_type] else None

    async def failing(job: tables.Job, _: object) -> None:
        ran.append(job.id)
        raise RuntimeError("one bad job")

    async def ok(job: tables.Job, _: object) -> None:
        ran.append(job.id)
        if len(ran) == 3:
            done.set()

    monkeypatch.setattr("app.db.jobs.claim_next", claim_next)
    monkeypatch.setitem(worker.HANDLERS, JobType.RESEARCH_FAST, failing)
    monkeypatch.setitem(worker.HANDLERS, JobType.RESEARCH_DEEP, ok)
    monkeypatch.setitem(worker.HANDLERS, JobType.RESEARCH_QUESTION, ok)

    research_worker = ResearchWorker(fake_deps(), poll_s=0.01)
    research_worker.start()
    await asyncio.wait_for(done.wait(), 1)
    await research_worker.stop()

    assert sorted(ran) == ["job_bad", "job_deep", "job_q"]
