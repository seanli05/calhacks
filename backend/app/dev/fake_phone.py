"""A fake phone worker (person 2's Goal 6 checkpoint): claims `call` jobs the
orchestrator queues after a YES and plays the fake call's script on them, then
finishes each with the contract fixture's call report. So consent → call → status →
summary can be tried on a phone before person 4's call loop is on `main`.

Like the fake call, it stands in for the phone agent and writes its rows (call,
transcript, report) through `writes.phone`.

Safety (rules 2 and 4): it never dials anything. It still checks
`official_dial_number` before "calling", as the real agent must, and fails the job
if the case has no verified number. The call row points at the user's real YES (the
job's `consent_message_id`).

It claims from the shared queue, so it would also take real call jobs: run it only
when no real phone agent is running against the same database.
"""

import asyncio
import json
import logging
import time
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import CallJob, CallReport, JobType
from app.db import jobs, reads, tables
from app.db.errors import UnverifiedNumber
from app.db.writes import phone
from app.dev.fake_call import Emitter, Pacing, play_call
from app.dev.fake_research import FIXTURES
from app.relay.ask_user import AskUser, get_ask_user

logger = logging.getLogger(__name__)

POLL_S = 1.0


class FakePhone:
    def __init__(
        self, ask_user: AskUser, pacing: Pacing | None = None, poll_s: float = POLL_S
    ) -> None:
        self._ask_user = ask_user
        self._pacing = pacing or Pacing()
        self._poll_s = poll_s
        self._loop: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, run_for_s: float) -> bool:
        """Start claiming call jobs for `run_for_s` seconds; False if already
        running."""
        if self.is_running():
            return False
        self._loop = asyncio.create_task(self._run(run_for_s))
        return True

    def is_running(self) -> bool:
        return self._loop is not None and not self._loop.done()

    async def _run(self, run_for_s: float) -> None:
        logger.info("Fake phone started for %.0f s", run_for_s)
        deadline = time.monotonic() + run_for_s
        while time.monotonic() < deadline:
            try:
                job = await jobs.claim_next(JobType.CALL)
            except (SQLAlchemyError, OSError):
                logger.exception("Fake phone: claiming a call job failed")
                job = None
            if job is None:
                await asyncio.sleep(self._poll_s)
                continue
            task = asyncio.create_task(self._handle(job))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        logger.info("Fake phone stopped")

    async def _handle(self, job: tables.Job) -> None:
        try:
            await self._call(job)
        except (SQLAlchemyError, OSError, ValidationError) as exc:
            logger.exception("Fake phone failed job_id=%s", job.id)
            await jobs.fail(job.id, f"fake phone failed ({type(exc).__name__})")

    async def _call(self, job: tables.Job) -> None:
        payload = CallJob.model_validate(job.payload)
        try:
            await reads.official_dial_number(payload.case_id)
        except UnverifiedNumber as exc:
            logger.error("Fake phone refused job_id=%s: %s", job.id, exc)
            await jobs.fail(job.id, "no verified official number (rule 2)")
            return
        call = await phone.create_call(
            payload.case_id, job.id, payload.brief_id, payload.consent_message_id
        )
        logger.info("Fake phone call job_id=%s call_id=%s", job.id, call.id)
        emit = Emitter(payload.user_id, payload.case_id, call.id)
        await play_call(emit, call.id, self._ask_user, self._pacing)
        transcript = await phone.save_transcript(
            call.id, [{"speaker": "agent", "text": "[dev] fake call, nothing dialed"}]
        )
        fixture = json.loads((FIXTURES / "call_report.json").read_text("utf-8"))
        report = CallReport.model_validate(
            {
                **fixture,
                "call_id": call.id,
                "case_id": payload.case_id,
                "transcript_id": transcript.id,
            }
        )
        await phone.save_call_report(call.id, report)
        await jobs.finish(job.id, report)


@lru_cache
def get_fake_phone() -> FakePhone:
    return FakePhone(get_ask_user())
