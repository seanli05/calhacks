"""Noticing when the jobs the orchestrator queued finish (Plan.md → Jobs, C13).

Nothing notifies us when a handler finishes a job, so one watcher task per job polls
`reads.get_job` about once a second until the job is `done` or `failed`, then hands
it to the caller's reaction. The same pattern as the call-status watcher. Reactions
run in the watcher's task, outside the pipe's per-number lock (whatsapp-pipe.md,
concern 8), so a slow reaction never holds up the user's next message.

Watchers live in memory: a server restart stops them, and the jobs they were watching
finish unnoticed.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

from sqlalchemy.exc import SQLAlchemyError

from app.contracts import JobStatus
from app.contracts.common import JobId
from app.db import reads, tables

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0
# A job that never finishes (its handler crashed mid-run, say) stops being watched
# after this. Long enough for a call job's longest hold.
MAX_WATCH_S = 3 * 60 * 60.0

OnJob = Callable[[tables.Job], Awaitable[None]]

_FINISHED = {JobStatus.DONE, JobStatus.FAILED}


class JobWatcher:
    def __init__(
        self, poll_interval_s: float = POLL_INTERVAL_S, max_watch_s: float = MAX_WATCH_S
    ) -> None:
        self._poll_interval_s = poll_interval_s
        self._max_watch_s = max_watch_s
        self._tasks: dict[JobId, asyncio.Task[None]] = {}

    def watch(
        self,
        job_id: JobId,
        on_finished: OnJob,
        *,
        slow_after_s: float | None = None,
        on_slow: OnJob | None = None,
    ) -> None:
        """Call `on_finished(job)` once the job is done or failed. If it's still
        running after `slow_after_s`, call `on_slow(job)` once first. Watching a job
        twice does nothing."""
        if job_id in self._tasks:
            return
        task = asyncio.create_task(
            self._run(job_id, on_finished, slow_after_s, on_slow)
        )
        self._tasks[job_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job_id, None))

    def is_watching(self, job_id: JobId) -> bool:
        return job_id in self._tasks

    async def _run(
        self,
        job_id: JobId,
        on_finished: OnJob,
        slow_after_s: float | None,
        on_slow: OnJob | None,
    ) -> None:
        started = time.monotonic()
        slow_at = started + slow_after_s if slow_after_s is not None else None
        while time.monotonic() - started < self._max_watch_s:
            try:
                job = await reads.get_job(job_id)
            except (SQLAlchemyError, OSError):
                logger.exception("Reading job failed job_id=%s", job_id)
                job = None
            else:
                if job is None:
                    logger.error("Watched job not found job_id=%s", job_id)
                    return
            if job is not None and job.status in _FINISHED:
                await _react(on_finished, job)
                return
            if job is not None and slow_at is not None and time.monotonic() >= slow_at:
                slow_at = None
                await _react(on_slow, job)
            await asyncio.sleep(self._poll_interval_s)
        logger.warning("Stopped watching job_id=%s (never finished)", job_id)


async def _react(reaction: OnJob | None, job: tables.Job) -> None:
    """Run a reaction, logging a failure with the job's IDs."""
    if reaction is None:
        return
    try:
        await reaction(job)
    except (SQLAlchemyError, OSError):
        logger.exception(
            "Reacting to job failed job_id=%s type=%s status=%s",
            job.id,
            job.type,
            job.status,
        )


@lru_cache
def get_job_watcher() -> JobWatcher:
    return JobWatcher()
