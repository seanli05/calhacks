"""The job queue (C13). The creator enqueues; the handler claims, then finishes or fails.

`claim_next` uses `FOR UPDATE SKIP LOCKED`, so two workers polling the same type
never get the same job.
"""

from typing import Any

from pydantic import BaseModel, TypeAdapter
from sqlmodel import select

from app.contracts import Component, JobPayload, JobStatus, JobType
from app.contracts.common import CaseId, JobId, UserId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.tables import utcnow

_payload_adapter: TypeAdapter[JobPayload] = TypeAdapter(JobPayload)


def payload_of(job: tables.Job) -> JobPayload:
    """The job's payload as its contract model (ResearchFastJob, CallJob, …)."""
    return _payload_adapter.validate_python(job.payload)


async def enqueue(
    payload: JobPayload,
    created_by: Component,
    user_id: UserId,
    case_id: CaseId | None = None,
) -> tables.Job:
    job = tables.Job(
        type=JobType(payload.job),
        created_by=created_by,
        user_id=user_id,
        case_id=case_id,
        payload=payload.model_dump(mode="json"),
    )
    async with session() as db:
        db.add(job)
        await db.commit()
        return job


async def claim_next(job_type: JobType) -> tables.Job | None:
    """Mark the oldest queued job of this type running and return it, or None."""
    async with session() as db:
        query = (
            select(tables.Job)
            .where(tables.Job.type == job_type, tables.Job.status == JobStatus.QUEUED)
            .order_by(tables.Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = (await db.execute(query)).scalar_one_or_none()
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        await db.commit()
        return job


async def finish(job_id: JobId, result: BaseModel | dict[str, Any]) -> tables.Job:
    async with session() as db:
        job = await must_get(db, tables.Job, job_id)
        job.status = JobStatus.DONE
        job.result = (
            result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        )
        job.finished_at = utcnow()
        await db.commit()
        return job


async def fail(job_id: JobId, error: str) -> tables.Job:
    async with session() as db:
        job = await must_get(db, tables.Job, job_id)
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = utcnow()
        await db.commit()
        return job
