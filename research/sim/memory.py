# SIM: replace with person 1's Postgres-backed DB helpers when person 1 lands them
"""In-memory Store for solo runs and tests."""

import uuid
from datetime import UTC, datetime
from typing import Any

from research.models import CaseBrief, Verification
from research.sim.store import CaseRecord, Document, Event, Job, JobStatus, JobType


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class InMemoryStore:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.cases: dict[str, CaseRecord] = {}
        self.verifications: dict[str, tuple[str, Verification]] = {}
        self.case_briefs: dict[str, CaseBrief] = {}
        self.case_refs: dict[tuple[str, str], str] = {}
        self.jobs: dict[str, Job] = {}
        self.events: list[Event] = []

    async def get_document(self, document_id: str) -> Document:
        return self.documents[document_id]

    async def get_case(self, case_id: str) -> CaseRecord:
        return self.cases[case_id]

    async def insert_case(self, case: CaseRecord) -> None:
        self.cases[case.case_id] = case

    async def insert_verification(
        self, case_id: str, verification: Verification
    ) -> str:
        ver_id = _new_id("ver")
        self.verifications[ver_id] = (case_id, verification)
        return ver_id

    async def insert_case_brief(self, brief: CaseBrief) -> None:
        self.case_briefs[brief.brief_id] = brief

    async def insert_case_ref(self, case_id: str, field: str, value: str) -> str:
        self.case_refs[(case_id, field)] = value
        return f"<ref:{field}>"

    async def create_job(
        self, job_type: JobType, payload: dict[str, Any], case_id: str | None = None
    ) -> str:
        job_id = _new_id("job")
        self.jobs[job_id] = Job(
            job_id=job_id,
            type=job_type,
            status="queued",
            case_id=case_id,
            payload=payload,
        )
        return job_id

    async def update_job(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        job = self.jobs[job_id]
        self.jobs[job_id] = job.model_copy(
            update={"status": status, "result": result, "error": error}
        )

    async def add_event(
        self,
        event_type: str,
        source: str,
        summary_en: str,
        *,
        case_id: str | None = None,
        call_id: str | None = None,
        job_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        event_id = _new_id("event")
        self.events.append(
            Event(
                event_id=event_id,
                created_at=datetime.now(UTC),
                type=event_type,
                source=source,
                case_id=case_id,
                call_id=call_id,
                job_id=job_id,
                summary_en=summary_en,
                data=data or {},
            )
        )
        return event_id
