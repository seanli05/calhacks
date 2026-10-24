"""Memory worker: claims `memory_write` jobs from Postgres, one at a time.

One at a time on purpose: each job checks new facts against the stored ones, and
two jobs for the same user running together could both save the same fact. The
backlog queued before the writer existed drains the same way, oldest first.
"""

import asyncio
import logging

from anthropic import AsyncAnthropic
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import JobType
from app.db import jobs
from app.memory.extract import FactExtractor
from app.memory.writer import MemoryDeps, handle_memory_write
from app.settings import Settings

logger = logging.getLogger(__name__)

POLL_S = 1.0


class MemoryWorker:
    def __init__(self, deps: MemoryDeps, poll_s: float = POLL_S) -> None:
        self.deps = deps
        self._poll_s = poll_s
        self._loop: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._loop is None or self._loop.done():
            self._loop = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop polling; a job cut off mid-write stays `running` in the DB."""
        if self._loop is not None:
            self._loop.cancel()
            await asyncio.gather(self._loop, return_exceptions=True)
        if self.deps.extractor is not None:
            await self.deps.extractor.close()

    async def drain(self) -> int:
        """Handle queued jobs until none is left; returns how many were claimed."""
        handled = 0
        while (job := await jobs.claim_next(JobType.MEMORY_WRITE)) is not None:
            handled += 1
            try:
                await handle_memory_write(job, self.deps)
            except Exception:
                # The handler failed the job already; keep draining.
                logger.exception(
                    "Memory job failed user_id=%s job_id=%s", job.user_id, job.id
                )
        return handled

    async def _run(self) -> None:
        logger.info("Memory worker started")
        while True:
            try:
                await self.drain()
            except (SQLAlchemyError, OSError):
                logger.exception("Memory worker: claiming memory_write failed")
            await asyncio.sleep(self._poll_s)


def real_deps(settings: Settings) -> MemoryDeps:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return MemoryDeps(extractor=FactExtractor(client, settings.model_fast))
