"""Research worker: claims research jobs from Postgres and runs each in its own task.

One background loop polls `jobs.claim_next` about once a second (there's no
notification). A failure in one job is logged with its case and job IDs and
fails only that job; the loop keeps going.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
from anthropic import AsyncAnthropic
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import JobType
from app.db import jobs, tables
from app.research.jobs import (
    ResearchDeps,
    handle_research_deep,
    handle_research_fast,
    handle_research_question,
)
from app.research.verify_cache import SEED_CACHE_DIR, VerifyCache
from app.settings import Settings

logger = logging.getLogger(__name__)

POLL_S = 1.0
HTTP_TIMEOUT_S = 10.0

Handler = Callable[[tables.Job, ResearchDeps], Awaitable[None]]
HANDLERS: dict[JobType, Handler] = {
    JobType.RESEARCH_FAST: handle_research_fast,
    JobType.RESEARCH_DEEP: handle_research_deep,
    JobType.RESEARCH_QUESTION: handle_research_question,
}


class ResearchWorker:
    def __init__(self, deps: ResearchDeps, poll_s: float = POLL_S) -> None:
        self.deps = deps
        self._poll_s = poll_s
        self._loop: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        if self._loop is None or self._loop.done():
            self._loop = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop polling and cancel jobs still running; they stay `running` in the DB."""
        tasks = [t for t in (self._loop, *self._tasks) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self) -> None:
        logger.info("Research worker started")
        while True:
            claimed = False
            for job_type in HANDLERS:
                try:
                    job = await jobs.claim_next(job_type)
                except (SQLAlchemyError, OSError):
                    logger.exception("Research worker: claiming %s failed", job_type)
                    continue
                if job is not None:
                    claimed = True
                    self._spawn(job)
            if not claimed:
                await asyncio.sleep(self._poll_s)

    def _spawn(self, job: tables.Job) -> None:
        # The loop holds tasks weakly; keep a reference until each one finishes.
        task = asyncio.create_task(self._handle(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, job: tables.Job) -> None:
        # Handlers fail their own job and log an event before re-raising the
        # unexpected; this catch only keeps one job's error from reaching the loop.
        try:
            await HANDLERS[JobType(job.type)](job, self.deps)
        except Exception:
            logger.exception(
                "Research job failed case_id=%s job_id=%s type=%s",
                job.case_id,
                job.id,
                job.type,
            )


def real_deps(settings: Settings) -> ResearchDeps:
    """The live passes, with clients that `close_deps` closes on shutdown."""
    return ResearchDeps(
        settings=settings,
        anthropic=AsyncAnthropic(api_key=settings.anthropic_api_key),
        http=httpx.AsyncClient(timeout=HTTP_TIMEOUT_S),
        seed=VerifyCache(SEED_CACHE_DIR),
    )


async def close_deps(deps: ResearchDeps) -> None:
    if deps.http is not None:
        await deps.http.aclose()
    if deps.anthropic is not None:
        await deps.anthropic.close()
