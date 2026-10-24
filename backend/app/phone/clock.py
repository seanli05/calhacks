"""The real clock, and timeouts that run on any `Clock` (including `FakeClock`)."""

import asyncio
from collections.abc import Awaitable
from datetime import datetime

from app.db.tables import utcnow
from app.phone.ports import Clock


class SystemClock:
    def now(self) -> datetime:
        return utcnow()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def with_timeout[T](clock: Clock, awaitable: Awaitable[T], seconds: float) -> T:
    """`asyncio.wait_for` on `clock` time. Raises `TimeoutError`. On a timeout (or
    if we're cancelled) the awaitable is cancelled and allowed to finish cleaning
    up before this returns."""
    task = asyncio.ensure_future(awaitable)
    timer = asyncio.ensure_future(clock.sleep(seconds))
    try:
        await asyncio.wait((task, timer), return_when=asyncio.FIRST_COMPLETED)
    finally:
        timer.cancel()
        if not task.done():
            task.cancel()
            await asyncio.wait((task,))
    if task.cancelled():
        raise TimeoutError(f"timed out after {seconds} s")
    return task.result()
