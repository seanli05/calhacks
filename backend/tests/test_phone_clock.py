"""Virtual time and clock-based timeouts: what the call's 30 s, 60 min, and
ask_user timers run on."""

import asyncio
import time

import pytest
from app.phone.clock import with_timeout
from app.phone.fakes import FakeClock


async def test_advance_wakes_sleepers_in_deadline_order() -> None:
    clock = FakeClock()
    start = clock.now()
    woke: list[tuple[str, float]] = []

    async def sleeper(name: str, seconds: float) -> None:
        await clock.sleep(seconds)
        woke.append((name, (clock.now() - start).total_seconds()))

    tasks = [asyncio.create_task(sleeper(n, s)) for n, s in [("b", 30), ("a", 10)]]
    await clock.advance(20)
    assert woke == [("a", 10)]
    await clock.advance(20)
    assert woke == [("a", 10), ("b", 30)]
    assert (clock.now() - start).total_seconds() == 40
    await asyncio.gather(*tasks)


async def test_run_skips_a_long_hold_instantly() -> None:
    clock = FakeClock()

    async def hold() -> str:
        await clock.sleep(60 * 60)
        return "done"

    started = time.monotonic()
    assert await clock.run(hold()) == "done"
    assert time.monotonic() - started < 1


async def test_run_reports_a_stuck_task() -> None:
    clock = FakeClock()
    never = asyncio.Event()
    with pytest.raises(RuntimeError, match="stuck"):
        await clock.run(never.wait())


async def test_with_timeout_returns_the_result_in_time() -> None:
    clock = FakeClock()

    async def quick() -> int:
        await clock.sleep(5)
        return 7

    assert await clock.run(with_timeout(clock, quick(), 30)) == 7


async def test_with_timeout_cancels_and_lets_the_task_clean_up() -> None:
    clock = FakeClock()
    cleaned_up = False

    async def slow() -> None:
        nonlocal cleaned_up
        try:
            await clock.sleep(60)
        finally:
            cleaned_up = True

    with pytest.raises(TimeoutError):
        await clock.run(with_timeout(clock, slow(), 30))
    assert cleaned_up
    assert clock.now().minute == 0 and clock.now().second == 30


async def test_with_timeout_cancels_the_task_when_cancelled_itself() -> None:
    clock = FakeClock()
    inner_cancelled = False

    async def slow() -> None:
        nonlocal inner_cancelled
        try:
            await clock.sleep(60)
        except asyncio.CancelledError:
            inner_cancelled = True
            raise

    outer = asyncio.create_task(with_timeout(clock, slow(), 30))
    await clock.advance(1)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    assert inner_cancelled
