"""The real line (`twilio_line.py`) on a fake REST API and fake media streams: the
number it dials, callbacks in any order, streams that come and go, and hang-ups."""

import asyncio

import pytest
from app.db.errors import UnverifiedNumber
from app.phone.fakes import FakeNumberSource
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    AgencyUnreachable,
    Heard,
    LineEvent,
)
from app.phone.ports import LineClosed
from app.phone.twilio_line import LineRegistry, LineTiming, LineUrls, TwilioTelephony

OFFICIAL = "+18005550100"
SID = "CA123"
FAST = LineTiming(stream_wait_s=0.2, gone_grace_s=0.05, say_margin_s=0.05)


class FakeCalls:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.updates: list[str] = []
        self.completed: list[str] = []
        self.call_status = "in-progress"
        self.on_update: list[object] = []
        self.fail_create = False

    async def create(self, *, to: str, twiml: str, status_callback: str) -> str:
        if self.fail_create:
            raise TimeoutError
        self.created.append({"to": to, "twiml": twiml, "status": status_callback})
        return SID

    async def update_twiml(self, sid: str, twiml: str) -> None:
        self.updates.append(twiml)

    async def complete(self, sid: str) -> None:
        self.completed.append(sid)

    async def status(self, sid: str) -> str:
        return self.call_status


class FakeStream:
    def __init__(self, *, plays: bool = True) -> None:
        self.said: list[str] = []
        self.interrupted = 0
        self.closed = False
        self._plays = plays

    async def speak(self, text: str) -> None:
        self.said.append(text)
        if not self._plays:
            await asyncio.Event().wait()  # Twilio never sends the mark back

    async def interrupt(self) -> None:
        self.interrupted += 1

    async def close(self) -> None:
        self.closed = True


class Line:
    def __init__(self, *, verified: bool = True) -> None:
        self.calls = FakeCalls()
        self.registry = LineRegistry()
        numbers = FakeNumberSource(verified={"case_1": OFFICIAL} if verified else {})
        self.line = TwilioTelephony(
            numbers,
            self.calls,
            LineUrls("https://agent.example.app"),
            registry=self.registry,
            timing=FAST,
        )

    async def dialed(self) -> "Line":
        await self.line.dial_agency("call_1", "case_1")
        return self

    async def events(self) -> list[LineEvent]:
        """Everything the line said, once it's hung up."""
        await self.line.hang_up()
        return [event async for event in self.line.events()]


# Dialing (rule 2)


async def test_dials_the_verified_number_and_registers_the_line() -> None:
    line = await Line().dialed()

    [created] = line.calls.created
    assert created["to"] == OFFICIAL
    assert "wss://agent.example.app/phone/calls/call_1/stream" in created["twiml"]
    assert created["status"] == "https://agent.example.app/phone/calls/call_1/status"
    assert line.registry.get("call_1") is line.line


async def test_an_unverified_case_is_never_dialed() -> None:
    line = Line(verified=False)
    with pytest.raises(UnverifiedNumber):
        await line.line.dial_agency("call_1", "case_1")
    assert line.calls.created == []
    assert line.registry.get("call_1") is None


async def test_a_failed_dial_leaves_no_line_registered() -> None:
    line = Line()
    line.calls.fail_create = True
    with pytest.raises(TimeoutError):
        await line.line.dial_agency("call_1", "case_1")
    assert line.registry.get("call_1") is None


# Callbacks and streams, in any order


async def test_answered_once_whichever_comes_first() -> None:
    line = await Line().dialed()
    line.line.on_status(SID, "ringing")
    assert line.line.attach_stream(FakeStream(), SID) == 1
    line.line.on_status(SID, "in-progress")

    assert await line.events() == [AgencyAnswered()]


async def test_busy_is_unreachable_and_nothing_after_it_counts() -> None:
    line = await Line().dialed()
    line.line.on_status(SID, "busy")
    line.line.on_status(SID, "completed")
    line.line.on_status(SID, "in-progress")

    assert await line.events() == [AgencyUnreachable(reason="busy")]
    assert line.calls.completed == []  # nothing to hang up


async def test_the_agency_hanging_up_is_reported_once() -> None:
    line = await Line().dialed()
    line.line.on_status(SID, "in-progress")
    line.line.on_status(SID, "completed")
    line.line.on_status(SID, "completed")

    assert await line.events() == [AgencyAnswered(), AgencyHungUp()]
    with pytest.raises(LineClosed):
        await line.line.say("hello")


async def test_another_calls_sid_is_ignored() -> None:
    line = await Line().dialed()
    line.line.on_status("CA999", "completed")
    assert line.line.attach_stream(FakeStream(), "CA999") is None

    assert await line.events() == []


async def test_a_stream_that_ends_unasked_ends_the_call() -> None:
    line = await Line().dialed()
    seq = line.line.attach_stream(FakeStream(), SID)
    assert seq is not None
    line.line.detach_stream(seq)
    await asyncio.sleep(0.1)  # no `completed` callback within the grace

    assert await line.events() == [AgencyAnswered(), AgencyHungUp()]


# say


async def test_say_waits_for_the_stream_and_speaks_on_it() -> None:
    line = await Line().dialed()
    stream = FakeStream()
    saying = asyncio.create_task(line.line.say("two"))
    await asyncio.sleep(0.01)
    line.line.attach_stream(stream, SID)
    await saying

    assert stream.said == ["two"]


async def test_say_with_no_stream_gives_up_the_line() -> None:
    line = await Line().dialed()
    with pytest.raises(LineClosed):
        await line.line.say("two")


async def test_say_carries_on_if_twilio_never_confirms_playback() -> None:
    line = await Line().dialed()
    line.line.attach_stream(FakeStream(plays=False), SID)
    await asyncio.wait_for(line.line.say("two"), timeout=2)


async def test_cancelling_say_stops_the_audio() -> None:
    line = await Line().dialed()
    stream = FakeStream(plays=False)
    line.line.attach_stream(stream, SID)
    saying = asyncio.create_task(line.line.say("Hello, this is an assistant."))
    await asyncio.sleep(0.01)
    saying.cancel()
    with pytest.raises(asyncio.CancelledError):
        await saying

    assert stream.interrupted == 1


# press_keys (C37): a new stream


def _reconnect_on_update(line: Line, new: FakeStream, old_seq: int) -> None:
    async def update(sid: str, twiml: str) -> None:
        line.calls.updates.append(twiml)

        async def swap() -> None:
            await asyncio.sleep(0.01)
            new_seq = line.line.attach_stream(new, SID)
            line.line.detach_stream(old_seq)  # the old close comes after the new start
            assert new_seq == old_seq + 1

        asyncio.get_running_loop().create_task(swap())

    line.calls.update_twiml = update  # type: ignore[method-assign]


async def test_keys_go_out_over_rest_and_the_line_carries_on() -> None:
    line = await Line().dialed()
    old = line.line.attach_stream(FakeStream(), SID)
    assert old is not None
    new = FakeStream()
    _reconnect_on_update(line, new, old)

    await line.line.press_keys("2")
    line.line.emit(Heard(text="Scheduling. For an interview, press 1."))
    await line.line.say("one")
    await asyncio.sleep(0.1)  # past the grace: the old stream's close didn't count

    [twiml] = line.calls.updates
    assert '<Play digits="w2"' in twiml and "/phone/calls/call_1/stream" in twiml
    assert new.said == ["one"]
    assert await line.events() == [
        AgencyAnswered(),
        Heard(text="Scheduling. For an interview, press 1."),
    ]


async def test_no_new_stream_and_the_call_is_gone_means_the_agency_hung_up() -> None:
    line = await Line().dialed()
    line.line.attach_stream(FakeStream(), SID)
    line.calls.call_status = "completed"

    with pytest.raises(LineClosed):
        await line.line.press_keys("2")

    assert await line.events() == [AgencyAnswered(), AgencyHungUp()]
    assert line.calls.completed == []


async def test_no_new_stream_on_a_live_call_hangs_up() -> None:
    line = await Line().dialed()
    line.line.attach_stream(FakeStream(), SID)

    with pytest.raises(LineClosed):
        await line.line.press_keys("2")

    assert line.calls.completed == [SID]
    assert [event async for event in line.line.events()] == [AgencyAnswered()]


# Hanging up and the bridge


async def test_hang_up_is_safe_twice_and_closes_everything() -> None:
    line = await Line().dialed()
    stream = FakeStream()
    line.line.attach_stream(stream, SID)

    await line.line.hang_up()
    await line.line.hang_up()

    assert line.calls.completed == [SID]
    assert stream.closed
    assert line.registry.get("call_1") is None
    assert line.line.attach_stream(FakeStream(), SID) is None
    with pytest.raises(LineClosed):
        await line.line.press_keys("2")


async def test_the_bridge_is_phase_3() -> None:
    line = await Line().dialed()
    with pytest.raises(NotImplementedError):
        await line.line.ring_user("call_1", "user_9")
    with pytest.raises(NotImplementedError):
        await line.line.connect_user()
