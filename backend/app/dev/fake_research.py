"""A fake research agent (person 2's Goal 4.4): claims `research_fast` and
`research_deep` jobs and finishes them from the contract fixtures after short delays,
so letter → explanation → verdict can be tried before person 3's research agent is
on `main`.

It stands in for research, so it writes research rows (case, refs, R1, verification,
brief) through `writes.research`, like the fake call does. The only other module of
person 2's that imports it is `fake_call.py`.

Safety (rule 2): the fixture's official phone is USCIS's real number, and this fake
never uses it. The verification it saves carries our own mock agency line
(`TWILIO_MOCK_AGENCY_NUMBER`), or no phone when that isn't set, in which case
`official_dial_number` refuses the case.

It claims from the shared queue, so it would also take other people's research jobs:
run it only when no real research worker is running against the same database.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import (
    Component,
    DeepResult,
    Event,
    EventType,
    FastResult,
    JobType,
    ResearchDeepJob,
    ResearchFastJob,
    Verification,
)
from app.contracts.common import CaseId, JobId, PhoneE164, UserId
from app.db import jobs, reads, tables
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow
from app.db.writes import research
from app.settings import get_settings

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "contracts"


@dataclass(frozen=True)
class Pacing:
    """Seconds each pass takes, and between polls of an empty queue."""

    fast_s: float = 5.0
    deep_s: float = 10.0
    poll_s: float = 1.0


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResearch:
    def __init__(self, official_phone: PhoneE164 | None, pacing: Pacing | None = None):
        self._official_phone = official_phone
        self._pacing = pacing or Pacing()
        self._loop: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, run_for_s: float) -> bool:
        """Start claiming jobs for `run_for_s` seconds; False if already running."""
        if self.is_running():
            return False
        self._loop = asyncio.create_task(self._run(run_for_s))
        return True

    def is_running(self) -> bool:
        return self._loop is not None and not self._loop.done()

    async def _run(self, run_for_s: float) -> None:
        logger.info("Fake research started for %.0f s", run_for_s)
        deadline = time.monotonic() + run_for_s
        while time.monotonic() < deadline:
            claimed = False
            for job_type in (JobType.RESEARCH_FAST, JobType.RESEARCH_DEEP):
                try:
                    job = await jobs.claim_next(job_type)
                except (SQLAlchemyError, OSError):
                    logger.exception("Fake research: claiming %s failed", job_type)
                    continue
                if job is not None:
                    claimed = True
                    self._spawn(self._handle(job))
            if not claimed:
                await asyncio.sleep(self._pacing.poll_s)
        logger.info("Fake research stopped")

    def _spawn(self, coro: Any) -> None:
        # The loop holds tasks weakly; keep a reference until each one finishes.
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, job: tables.Job) -> None:
        try:
            if job.type == JobType.RESEARCH_FAST:
                await self._fast(job)
            else:
                await self._deep(job)
        except (SQLAlchemyError, OSError, ValidationError) as exc:
            logger.exception("Fake research failed job_id=%s", job.id)
            await jobs.fail(job.id, f"fake research failed ({type(exc).__name__})")

    async def _fast(self, job: tables.Job) -> None:
        payload = ResearchFastJob.model_validate(job.payload)
        emit = _Emitter(payload.user_id, payload.case_id, job.id)
        await emit(EventType.RESEARCH_FAST_STARTED, "Started reading the letter (fake)")
        await asyncio.sleep(self._pacing.fast_s)

        result = FastResult.model_validate(
            {**_fixture("fast_result.json"), "case_id": payload.case_id}
        )
        if await reads.get_case(payload.case_id) is None:
            await research.create_case(
                payload.case_id, payload.user_id, payload.document_ids
            )
            await emit(EventType.CASE_CREATED, "Opened a case for the letter (fake)")
        refs = [fact.ref for fact in result.key_facts if fact.ref]
        if result.appointment is not None and result.appointment.location_ref:
            refs.append(result.appointment.location_ref)
        for ref in refs:
            name = ref.removeprefix("<ref:").removesuffix(">")
            await research.put_ref(payload.case_id, name, f"[dev] fake {name}")
        await research.save_fast_result(payload.case_id, result)
        await jobs.enqueue(
            ResearchDeepJob(
                case_id=payload.case_id,
                user_id=payload.user_id,
                document_ids=payload.document_ids,
            ),
            Component.RESEARCH_AGENT,
            payload.user_id,
            payload.case_id,
        )
        await jobs.finish(job.id, result)
        await emit(
            EventType.RESEARCH_FAST_DONE,
            "Finished reading the letter (fake): ok",
            status=result.status,
            doc_type=result.doc_type,
        )

    async def _deep(self, job: tables.Job) -> None:
        payload = ResearchDeepJob.model_validate(job.payload)
        emit = _Emitter(payload.user_id, payload.case_id, job.id)
        await emit(
            EventType.RESEARCH_DEEP_STARTED, "Started checking the letter (fake)"
        )
        await asyncio.sleep(self._pacing.deep_s)

        fixture = DeepResult.model_validate(
            {**_fixture("deep_result.json"), "case_id": payload.case_id}
        )
        verification = Verification(
            **{
                **fixture.verification.model_dump(),
                "official_phone": self._official_phone,
            }
        )
        await research.save_verification(payload.case_id, verification)
        await emit(
            EventType.VERIFICATION_VERIFIED,
            "Confirmed the letter against the official site (fake)",
            source="uscis.gov",
        )
        brief = await research.save_brief(
            payload.case_id,
            {
                "call_goal_en": fixture.call_goal_en,
                "questions_to_ask": [
                    "Is the interview still scheduled for this date and time?",
                    "What should I do if my interpreter can't come?",
                ],
            },
            "[dev] fake research brief",
        )
        result = fixture.model_copy(
            update={"verification": verification, "brief_id": brief.id}
        )
        await jobs.finish(job.id, result)
        await emit(EventType.RESEARCH_DEEP_DONE, "Finished checking the letter (fake)")


class _Emitter:
    """Logs events the way research will: each carries the case and the job."""

    def __init__(self, user_id: UserId, case_id: CaseId, job_id: JobId) -> None:
        self._user_id = user_id
        self._case_id = case_id
        self._job_id = job_id

    async def __call__(
        self, event_type: EventType, summary_en: str, **data: Any
    ) -> None:
        await append_event(
            Event(
                event_id=new_id("event"),
                created_at=utcnow(),
                type=event_type,
                source=Component.RESEARCH_AGENT,
                user_id=self._user_id,
                case_id=self._case_id,
                job_id=self._job_id,
                summary_en=summary_en,
                data=data,
            )
        )


@lru_cache
def get_fake_research() -> FakeResearch:
    return FakeResearch(get_settings().twilio_mock_agency_number or None)
