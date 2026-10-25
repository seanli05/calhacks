"""The real line (`twilio_line.py`) on a fake REST API and fake media streams: the
number it dials, callbacks in any order, streams that come and go, and hang-ups."""

import asyncio

import pytest
from app.db.errors import UnverifiedNumber
from app.phone.call_lines import JOIN_PROMPTS
from app.phone.fakes import FakeNumberSource
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    AgencyUnreachable,
    Heard,
    LineEvent,
    Overheard,
    UserAnswered,
    UserLeft,
    UserUnreachable,
)
from app.phone.ports import LineClosed
from app.phone.twilio_line import LineRegistry, LineTiming, TwilioTelephony
from app.phone.twilio_urls import LineUrls

OFFICIAL = "+18005550100"
APPLICANT = "+15555550123"
SID = "CA123"
USER_SID = "CA456"
FAST = LineTiming(stream_wait_s=0.2, gone_grace_s=0.05, say_margin_s=0.05)


class FakeCalls:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.updates: list[str] = []
        self.completed: list[str] = []
        self.ended: list[str] = []
        self.call_status = "in-progress"
        self.on_update: list[object] = []
        self.fail_create = False

    async def create(self, *, to: str, twiml: str, status_callback: str) -> str:
        if self.fail_create:
            raise TimeoutError
        self.created.append({"to": to, "twiml": twiml, "status": status_callback})
        return SID if len(self.created) == 1 else USER_SID

    async def update_twiml(self, sid: str, twiml: str) -> None:
        self.updates.append(twiml)

    async def complete(self, sid: str) -> None:
        self.completed.append(sid)

    async def end(self, sid: str) -> None:
        self.ended.append(sid)

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
    def __init__(
        self, *, verified: bool = True, language: str = "es", join_gate: bool = True
    ) -> None:
        self.calls = FakeCalls()
        self.registry = LineRegistry()
        numbers = FakeNumberSource(
            verified={"case_1": OFFICIAL} if verified else {},
            users={"user_9": APPLICANT},
        )
        self.line = TwilioTelephony(
            numbers,
            self.calls,
            LineUrls("https://agent.example.app"),
            user_language=language,
            registry=self.registry,
            timing=FAST,
            join_gate=join_gate,
        )

    async def dialed(self) -> "Line":
        await self.line.dial_agency("call_1", "case_1")
        return self

    async def answered(self) -> tuple["Line", int]:
        """Dialed, with the agency on the stream; returns the stream's number."""
        await self.dialed()
        seq = self.line.attach_stream(FakeStream(), SID)
        assert seq is not None
        return self, seq

    async def rung(self) -> tuple["Line", int]:
        line, seq = await self.answered()
        await line.line.ring_user("call_1", "user_9")
        return line, seq

    async def bridged(self) -> tuple["Line", int]:
        line, seq = await self.rung()
        line.line.user_pressed_key(USER_SID)
        await line.line.connect_user()
        line.line.detach_stream(seq)  # moving the leg ends its stream
        return line, seq

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


# The bridge: ringing the applicant (C6), the join gate, and the conference


async def test_ring_user_calls_the_users_own_number_with_a_join_gate() -> None:
    line, _ = await Line().rung()

    _, user_leg = line.calls.created
    assert user_leg["to"] == APPLICANT
    assert user_leg["status"] == (
        "https://agent.example.app/phone/calls/call_1/user/status"
    )
    twiml = user_leg["twiml"]
    assert JOIN_PROMPTS["es"].text in twiml and 'language="es-US"' in twiml
    assert 'action="https://agent.example.app/phone/calls/call_1/user/joined"' in twiml
    assert "/phone/calls/call_1/user/missed</Redirect>" in twiml
    assert "record" not in twiml.lower()  # C29


async def test_the_join_gate_speaks_the_users_language() -> None:
    line, _ = await Line(language="en").rung()
    assert JOIN_PROMPTS["en"].text in line.calls.created[1]["twiml"]


async def test_a_language_with_no_prompt_falls_back_to_english() -> None:
    line, _ = await Line(language="fa").rung()
    assert JOIN_PROMPTS["en"].text in line.calls.created[1]["twiml"]


async def test_a_failed_ring_is_unreachable_not_a_crash() -> None:
    line, _ = await Line().answered()
    line.calls.fail_create = True

    await line.line.ring_user("call_1", "user_9")

    assert await line.events() == [
        AgencyAnswered(),
        UserUnreachable(reason="failed"),
    ]


async def test_a_key_press_joins_the_conference_and_reports_the_answer() -> None:
    line, _ = await Line().rung()

    twiml = line.line.user_pressed_key(USER_SID)

    assert "<Conference" in twiml and ">bridge-call_1</Conference>" in twiml
    assert 'endConferenceOnExit="true"' in twiml and 'beep="false"' in twiml
    assert 'url="wss://agent.example.app/phone/calls/call_1/fork/user"' in twiml
    assert 'track="inbound_track"' in twiml
    assert "record" not in twiml.lower()  # C29
    assert await line.events() == [AgencyAnswered(), UserAnswered()]


async def test_no_key_press_is_unreachable_once() -> None:
    line, _ = await Line().rung()

    twiml = line.line.user_missed_gate(USER_SID)
    line.line.on_user_status(USER_SID, "completed")

    assert "<Hangup" in twiml
    assert await line.events() == [
        AgencyAnswered(),
        UserUnreachable(reason="no_key_press"),
    ]


async def test_picking_up_and_putting_down_without_a_key_is_unreachable() -> None:
    line, _ = await Line().rung()
    line.line.on_user_status(USER_SID, "in-progress")  # picked up: maybe voicemail
    line.line.on_user_status(USER_SID, "completed")

    assert await line.events() == [
        AgencyAnswered(),
        UserUnreachable(reason="no_key_press"),
    ]


@pytest.mark.parametrize(
    ("status", "reason"),
    [("busy", "busy"), ("no-answer", "no_answer"), ("failed", "failed")],
)
async def test_a_user_leg_that_never_connects_is_unreachable(
    status: str, reason: str
) -> None:
    line, _ = await Line().rung()
    line.line.on_user_status(USER_SID, "ringing")
    line.line.on_user_status(USER_SID, status)

    assert await line.events() == [AgencyAnswered(), UserUnreachable(reason=reason)]


async def test_a_key_press_too_late_hangs_up_the_applicant() -> None:
    line, _ = await Line().rung()
    line.line.user_missed_gate(USER_SID)  # or the runner's backstop gave up

    assert "<Hangup" in line.line.user_pressed_key(USER_SID)
    assert UserAnswered() not in await line.events()


async def test_a_key_press_after_the_agency_left_hangs_up_the_applicant() -> None:
    line, _ = await Line().rung()
    line.line.on_status(SID, "completed")

    assert "<Hangup" in line.line.user_pressed_key(USER_SID)
    assert await line.events() == [AgencyAnswered(), AgencyHungUp()]


async def test_another_sid_cant_press_for_the_applicant() -> None:
    line, _ = await Line().rung()
    assert "<Hangup" in line.line.user_pressed_key("CA999")
    line.line.on_user_status("CA999", "busy")
    assert await line.events() == [AgencyAnswered()]


# No join gate (PHONE_JOIN_GATE=false, the demo): picking up joins


async def test_with_no_gate_the_applicant_leg_is_the_conference_itself() -> None:
    line, _ = await Line(join_gate=False).rung()

    twiml = line.calls.created[1]["twiml"]
    assert "<Gather" not in twiml and JOIN_PROMPTS["es"].text not in twiml
    assert ">bridge-call_1</Conference>" in twiml
    assert 'url="wss://agent.example.app/phone/calls/call_1/fork/user"' in twiml
    assert "record" not in twiml.lower()  # C29


async def test_with_no_gate_picking_up_joins_once_whichever_comes_first() -> None:
    by_callback, _ = await Line(join_gate=False).rung()
    by_callback.line.on_user_status(USER_SID, "in-progress")
    assert by_callback.line.attach_fork("user", USER_SID)
    by_callback.line.on_user_status(USER_SID, "in-progress")

    by_fork, _ = await Line(join_gate=False).rung()
    assert by_fork.line.attach_fork("user", USER_SID)
    by_fork.line.on_user_status(USER_SID, "in-progress")

    for line in (by_callback, by_fork):
        assert await line.events() == [AgencyAnswered(), UserAnswered()]


async def test_with_no_gate_another_sid_cant_join_for_the_applicant() -> None:
    line, _ = await Line(join_gate=False).rung()
    assert not line.line.attach_fork("user", SID)
    line.line.on_user_status("CA999", "in-progress")
    assert await line.events() == [AgencyAnswered()]


async def test_with_no_gate_the_agency_leaving_first_keeps_the_applicant_out() -> None:
    line, _ = await Line(join_gate=False).rung()
    line.line.on_status(SID, "completed")
    assert not line.line.attach_fork("user", USER_SID)
    assert UserAnswered() not in await line.events()


@pytest.mark.parametrize(
    ("status", "reason"), [("busy", "busy"), ("no-answer", "no_answer")]
)
async def test_with_no_gate_a_missed_ring_is_still_unreachable(
    status: str, reason: str
) -> None:
    line, _ = await Line(join_gate=False).rung()
    line.line.on_user_status(USER_SID, status)
    assert await line.events() == [AgencyAnswered(), UserUnreachable(reason=reason)]


async def test_with_the_gate_picking_up_alone_doesnt_join() -> None:
    line, _ = await Line().rung()
    line.line.on_user_status(USER_SID, "in-progress")
    assert not line.line.attach_fork("user", USER_SID)
    assert await line.events() == [AgencyAnswered()]


async def test_with_no_gate_connect_user_bridges_after_pick_up() -> None:
    line, _ = await Line(join_gate=False).rung()
    line.line.on_user_status(USER_SID, "in-progress")
    await line.line.connect_user()
    assert ">bridge-call_1</Conference>" in line.calls.updates[-1]


# Ringing again after a missed ring (RunnerConfig.user_ring_attempts)

SECOND_SID = "CA789"


async def _rung_again(line: Line) -> None:
    """Ring a second time; the fake hands the new leg `SECOND_SID`."""
    created = len(line.calls.created)
    real_create = line.calls.create

    async def create(*, to: str, twiml: str, status_callback: str) -> str:
        await real_create(to=to, twiml=twiml, status_callback=status_callback)
        return SECOND_SID

    line.calls.create = create  # type: ignore[method-assign]
    await line.line.ring_user("call_1", "user_9")
    assert len(line.calls.created) == created + 1


async def test_a_missed_ring_can_ring_again_and_the_second_leg_joins() -> None:
    line, _ = await Line().rung()
    line.line.on_user_status(USER_SID, "no-answer")
    await _rung_again(line)

    assert line.calls.created[2]["to"] == APPLICANT
    assert "<Conference" in line.line.user_pressed_key(SECOND_SID)
    assert await line.events() == [
        AgencyAnswered(),
        UserUnreachable(reason="no_answer"),
        UserAnswered(),
    ]


async def test_callbacks_from_the_first_ring_dont_count_after_the_second() -> None:
    line, _ = await Line().rung()
    line.line.on_user_status(USER_SID, "busy")
    await _rung_again(line)

    line.line.on_user_status(USER_SID, "completed")  # late, from the first leg
    assert "<Hangup" in line.line.user_pressed_key(USER_SID)
    assert not line.line.attach_fork("user", USER_SID)
    line.line.on_user_status(SECOND_SID, "no-answer")

    assert await line.events() == [
        AgencyAnswered(),
        UserUnreachable(reason="busy"),
        UserUnreachable(reason="no_answer"),
    ]


async def test_ringing_again_ends_a_first_leg_still_ringing() -> None:
    """The runner's backstop gave up on a leg Twilio never reported on."""
    line, _ = await Line().rung()
    await _rung_again(line)
    assert line.calls.ended == [USER_SID]


async def test_no_second_ring_once_the_applicant_joined() -> None:
    line, _ = await Line().rung()
    line.line.user_pressed_key(USER_SID)
    with pytest.raises(RuntimeError):
        await line.line.ring_user("call_1", "user_9")


async def test_with_no_gate_the_second_leg_joins_on_pick_up() -> None:
    line, _ = await Line(join_gate=False).rung()
    line.line.on_user_status(USER_SID, "no-answer")
    await _rung_again(line)

    line.line.on_user_status(USER_SID, "in-progress")  # stale: ignored
    assert line.line.attach_fork("user", SECOND_SID)
    assert await line.events() == [
        AgencyAnswered(),
        UserUnreachable(reason="no_answer"),
        UserAnswered(),
    ]


async def test_connect_user_moves_the_agency_leg_into_the_conference() -> None:
    line, _ = await Line().bridged()
    await asyncio.sleep(0.1)  # past the grace: the stream's close isn't a hang-up

    [twiml] = line.calls.updates
    assert ">bridge-call_1</Conference>" in twiml
    assert 'url="wss://agent.example.app/phone/calls/call_1/fork/agency"' in twiml
    assert await line.events() == [AgencyAnswered(), UserAnswered()]


async def test_the_agent_is_silent_once_the_applicant_is_on() -> None:
    line, _ = await Line().bridged()
    with pytest.raises(LineClosed):
        await line.line.say("hello")
    with pytest.raises(LineClosed):
        await line.line.press_keys("1")
    assert line.line.attach_stream(FakeStream(), SID) is None


async def test_connect_user_needs_the_applicant_to_have_joined() -> None:
    line, _ = await Line().rung()
    with pytest.raises(RuntimeError):
        await line.line.connect_user()
    assert line.calls.updates == []


async def test_after_the_bridge_either_side_leaving_is_reported() -> None:
    line, _ = await Line().bridged()
    line.line.on_user_status(USER_SID, "completed")
    line.line.on_status(SID, "completed")

    assert await line.events() == [
        AgencyAnswered(),
        UserAnswered(),
        UserLeft(),
        AgencyHungUp(),
    ]


async def test_forks_are_taken_only_from_each_joined_leg() -> None:
    line, _ = await Line().rung()
    assert not line.line.attach_fork("user", USER_SID)  # no key pressed yet
    line.line.user_pressed_key(USER_SID)
    assert line.line.attach_fork("user", USER_SID)
    assert not line.line.attach_fork("agency", SID)  # not moved in yet
    await line.line.connect_user()
    assert line.line.attach_fork("agency", SID)
    assert not line.line.attach_fork("agency", USER_SID)
    assert not line.line.attach_fork("user", SID)

    line.line.emit(Overheard(speaker="agency", text="Your reference number is"))
    assert Overheard(speaker="agency", text="Your reference number is") in (
        await line.events()
    )
    assert not line.line.attach_fork("user", USER_SID)  # hung up


async def test_hang_up_ends_both_legs() -> None:
    line, _ = await Line().bridged()
    await line.line.hang_up()
    await line.line.hang_up()

    assert line.calls.completed == [SID]
    assert line.calls.ended == [USER_SID]


async def test_hang_up_leaves_an_applicant_leg_thats_already_over() -> None:
    line, _ = await Line().rung()
    line.line.on_user_status(USER_SID, "no-answer")
    await line.line.hang_up()

    assert line.calls.ended == []
