"""Listening in (`listen_audio.py`, `listen_leg.py`, the line, the routes): the user
hears the call muted on a leg of its own, hanging up there leaves the agency call
alone, and a person picking up moves that leg into the bridge without a new ring."""

import asyncio
import base64
import json
from collections.abc import Iterator
from typing import Any

import pytest
from app.phone import control
from app.phone.call_lines import LISTEN_PROMPTS, LISTENING_NOW
from app.phone.fakes import FakeNumberSource
from app.phone.line import (
    AgencyAnswered,
    HangUpRequested,
    LineEvent,
    ListenEnded,
    ListenRequested,
    ListenStarted,
    UserAnswered,
    UserLeft,
)
from app.phone.listen_audio import ListenMixer, ListenSink
from app.phone.routes import router
from app.phone.twilio_line import LINES, LineRegistry, LineTiming, TwilioTelephony
from app.phone.twilio_urls import LineUrls
from app.settings import Settings, get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

BASE = "https://agent.example.app"
TOKEN = "test-auth-token"
OFFICIAL = "+18005550100"
APPLICANT = "+15555550123"
SID = "CA100"
LISTEN_SID = "CA200"
FAST = LineTiming(stream_wait_s=0.2, gone_grace_s=0.05, say_margin_s=0.05)


def _pcm(*samples: int) -> bytes:
    return b"".join(s.to_bytes(2, "little", signed=True) for s in samples)


class RecordingSink:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def send(self, pcm: bytes) -> None:
        self.chunks.append(pcm)


class FakeCalls:
    def __init__(self) -> None:
        self.sids = [SID, LISTEN_SID, "CA300", "CA400"]
        self.created: list[dict[str, str]] = []
        self.updates: list[tuple[str, str]] = []
        self.completed: list[str] = []
        self.ended: list[str] = []
        self.fail_create = False
        self.fail_update = False

    async def create(
        self, *, to: str, twiml: str, status_callback: str, ring_s: int = 30
    ) -> str:
        if self.fail_create:
            raise TimeoutError
        self.created.append(
            {"to": to, "twiml": twiml, "status": status_callback, "ring_s": ring_s}
        )
        return self.sids[len(self.created) - 1]

    async def update_twiml(self, sid: str, twiml: str) -> None:
        if self.fail_update:
            raise TimeoutError
        self.updates.append((sid, twiml))

    async def complete(self, sid: str) -> None:
        self.completed.append(sid)

    async def end(self, sid: str) -> None:
        self.ended.append(sid)

    async def status(self, sid: str) -> str:
        return "in-progress"


class FakeStream:
    async def speak(self, text: str) -> None: ...
    async def interrupt(self) -> None: ...
    async def close(self) -> None: ...


class Line:
    def __init__(
        self, registry: LineRegistry | None = None, *, join_gate: bool = True
    ) -> None:
        self.calls = FakeCalls()
        self.line = TwilioTelephony(
            FakeNumberSource({"case_1": OFFICIAL}, users={"user_9": APPLICANT}),
            self.calls,
            LineUrls(BASE),
            user_language="es",
            registry=registry or LineRegistry(),
            timing=FAST,
            join_gate=join_gate,
        )

    async def answered(self, call_id: str = "call_1") -> "Line":
        await self.line.dial_agency(call_id, "case_1")
        assert self.line.attach_stream(FakeStream(), SID) is not None
        return self

    async def ringing(self) -> "Line":
        await self.answered()
        assert self.line.request_listen_in() == "ringing"
        await self.line.listen_in("call_1", "user_9")
        return self

    async def listening(self) -> tuple["Line", RecordingSink]:
        await self.ringing()
        self.line.listen_pressed_key(LISTEN_SID)
        sink = RecordingSink()
        assert self.line.attach_listener(sink, LISTEN_SID)  # type: ignore[arg-type]
        return self, sink

    async def events(self) -> list[LineEvent]:
        await self.line.hang_up()
        return [event async for event in self.line.events()]


# The mixer


def test_agent_speech_is_paced_by_the_agency_frames() -> None:
    mixer = ListenMixer()
    sink = RecordingSink()
    mixer.attach(sink)  # type: ignore[arg-type]
    mixer.agent_audio(_pcm(100, 200, 300))  # arrives faster than it plays

    mixer.agency_audio(_pcm(1, 1))
    mixer.agency_audio(_pcm(1, 1))
    mixer.agency_audio(_pcm(1, 1))

    assert sink.chunks == [_pcm(101, 201), _pcm(301, 1), _pcm(1, 1)]


def test_an_interruption_drops_what_the_agent_hadnt_said() -> None:
    mixer = ListenMixer()
    sink = RecordingSink()
    mixer.attach(sink)  # type: ignore[arg-type]
    mixer.agent_audio(_pcm(500, 500, 500, 500))
    mixer.agency_audio(_pcm(0, 0))
    mixer.interrupt()
    mixer.agency_audio(_pcm(7, 7))

    assert sink.chunks == [_pcm(500, 500), _pcm(7, 7)]


def test_nothing_is_kept_while_no_one_listens() -> None:
    mixer = ListenMixer()
    mixer.agent_audio(_pcm(500, 500))
    mixer.agency_audio(_pcm(1, 1))
    sink = RecordingSink()
    mixer.attach(sink)  # type: ignore[arg-type]
    mixer.agency_audio(_pcm(2, 2))

    assert sink.chunks == [_pcm(2, 2)]  # the earlier speech isn't replayed


def test_buffered_agent_speech_is_capped() -> None:
    mixer = ListenMixer(max_agent_s=0.0005)  # 4 samples at 8 kHz
    sink = RecordingSink()
    mixer.attach(sink)  # type: ignore[arg-type]
    mixer.agent_audio(_pcm(1, 2, 3, 4, 5, 6))
    mixer.agency_audio(_pcm(0, 0, 0, 0, 0, 0))

    assert sink.chunks == [_pcm(1, 2, 3, 4, 0, 0)]


class FakeWebsocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


async def test_the_sink_sends_twilio_media_and_drops_when_behind() -> None:
    websocket = FakeWebsocket()
    sink = ListenSink(websocket, "MZ1", max_chunks=2)  # type: ignore[arg-type]
    for _ in range(3):
        sink.send(_pcm(0, 0))
    assert sink.dropped == 1

    writer = asyncio.create_task(sink.run())
    await asyncio.sleep(0.05)
    writer.cancel()
    await asyncio.gather(writer, return_exceptions=True)

    assert len(websocket.sent) == 2
    [first, _] = websocket.sent
    assert first["event"] == "media"
    assert first["streamSid"] == "MZ1"
    assert len(base64.b64decode(first["media"]["payload"])) == 2  # μ-law, 1 B/sample


# The listen leg on the line


async def test_a_request_rings_the_users_own_number_behind_a_gate() -> None:
    line = await Line().ringing()

    listen = line.calls.created[1]
    assert listen["to"] == APPLICANT
    assert LISTEN_PROMPTS["es"].text in listen["twiml"]
    assert f"{BASE}/phone/calls/call_1/listen/joined" in listen["twiml"]
    assert listen["status"] == f"{BASE}/phone/calls/call_1/listen/status"
    assert listen["ring_s"] == 15
    assert line.line.request_listen_in() == "already_listening"
    assert await line.events() == [AgencyAnswered(), ListenRequested()]


async def test_with_no_gate_the_listen_leg_is_the_stream_itself() -> None:
    line = await Line(join_gate=False).ringing()

    twiml = line.calls.created[1]["twiml"]
    assert "<Gather" not in twiml and LISTEN_PROMPTS["es"].text not in twiml
    assert LISTENING_NOW["es"].text in twiml
    assert "wss://agent.example.app/phone/calls/call_1/listen/stream" in twiml
    assert line.calls.created[1]["ring_s"] == 15


async def test_with_no_gate_picking_up_starts_listening_once() -> None:
    """Whichever comes first, the callback or the stream."""
    by_callback = await Line(join_gate=False).ringing()
    by_callback.line.on_listen_status(LISTEN_SID, "in-progress")
    sink = RecordingSink()
    assert by_callback.line.attach_listener(sink, LISTEN_SID)  # type: ignore[arg-type]
    by_callback.line.on_listen_status(LISTEN_SID, "in-progress")

    by_stream = await Line(join_gate=False).ringing()
    other = RecordingSink()
    assert not by_stream.line.attach_listener(other, "CA999")  # type: ignore[arg-type]
    assert by_stream.line.attach_listener(other, LISTEN_SID)  # type: ignore[arg-type]
    by_stream.line.on_listen_status(LISTEN_SID, "in-progress")

    by_callback.line.listen_mixer.agency_audio(_pcm(3, 3))
    assert sink.chunks == [_pcm(3, 3)]
    for line in (by_callback, by_stream):
        events = await line.events()
        assert events[1:3] == [ListenRequested(), ListenStarted()]
        assert events.count(ListenStarted()) == 1


async def test_with_no_gate_a_listener_who_picked_up_moves_into_the_bridge() -> None:
    line = await Line(join_gate=False).ringing()
    line.line.on_listen_status(LISTEN_SID, "in-progress")
    await line.line.ring_user("call_1", "user_9")

    assert len(line.calls.created) == 2  # no second ring
    assert line.calls.updates[-1][0] == LISTEN_SID
    assert UserAnswered() in await line.events()


async def test_with_the_gate_picking_up_alone_doesnt_start_listening() -> None:
    line = await Line().ringing()
    line.line.on_listen_status(LISTEN_SID, "in-progress")
    sink = RecordingSink()
    assert not line.line.attach_listener(sink, LISTEN_SID)  # type: ignore[arg-type]
    assert ListenStarted() not in await line.events()


async def test_a_key_press_streams_the_call_to_the_user() -> None:
    line = await Line().ringing()
    twiml = line.line.listen_pressed_key(LISTEN_SID)

    assert "wss://agent.example.app/phone/calls/call_1/listen/stream" in twiml
    sink = RecordingSink()
    assert not line.line.attach_listener(sink, "CA999")  # type: ignore[arg-type]
    assert line.line.attach_listener(sink, LISTEN_SID)  # type: ignore[arg-type]
    line.line.listen_mixer.agency_audio(_pcm(3, 3))
    assert sink.chunks == [_pcm(3, 3)]
    assert (await line.events())[-1] == ListenStarted()


async def test_the_user_hanging_up_leaves_the_agency_call_alone() -> None:
    line, sink = await Line().listening()
    line.line.on_listen_status(LISTEN_SID, "completed")
    line.line.on_listen_status(LISTEN_SID, "completed")  # late repeat

    line.line.listen_mixer.agency_audio(_pcm(1, 1))
    assert sink.chunks == []
    await line.line.say("two")  # the agent still has its line
    assert line.calls.completed == []
    # And they can ask again.
    assert line.line.request_listen_in() == "ringing"
    events = await line.events()
    assert events[1:] == [
        ListenRequested(),
        ListenStarted(),
        ListenEnded(reason="hung_up"),
        ListenRequested(),
    ]


@pytest.mark.parametrize(
    ("status", "reason"),
    [("no-answer", "no_answer"), ("busy", "busy"), ("completed", "no_key_press")],
)
async def test_a_listen_leg_that_never_joins_ends(status: str, reason: str) -> None:
    line = await Line().ringing()
    line.line.on_listen_status(LISTEN_SID, status)
    assert (await line.events())[-1] == ListenEnded(reason=reason)


async def test_no_key_at_the_listen_gate_hangs_up() -> None:
    line = await Line().ringing()
    assert "<Hangup" in line.line.listen_missed_gate(LISTEN_SID)
    assert "<Hangup" in line.line.listen_pressed_key(LISTEN_SID)  # too late now
    assert (await line.events())[-1] == ListenEnded(reason="no_key_press")


async def test_a_failed_ring_ends_the_listen_request() -> None:
    line = await Line().answered()
    line.line.request_listen_in()
    line.calls.fail_create = True
    await line.line.listen_in("call_1", "user_9")

    assert line.line.request_listen_in() == "ringing"
    assert ListenEnded(reason="failed") in await line.events()


async def test_a_person_picking_up_moves_the_listener_into_the_bridge() -> None:
    line, sink = await Line().listening()
    await line.line.ring_user("call_1", "user_9")

    assert len(line.calls.created) == 2  # no second ring
    sid, twiml = line.calls.updates[-1]
    assert sid == LISTEN_SID
    assert ">bridge-call_1</Conference>" in twiml
    assert "/phone/calls/call_1/fork/user" in twiml
    line.line.listen_mixer.agency_audio(_pcm(1, 1))
    assert sink.chunks == []
    await line.line.connect_user()
    assert line.line.request_listen_in() == "rep_on_line"
    # The leg's callbacks still come to the listen URL; now they're the applicant's.
    line.line.on_listen_status(LISTEN_SID, "completed")
    events = await line.events()
    assert events[-2:] == [UserAnswered(), UserLeft()]


async def test_a_listener_still_at_the_gate_is_ended_and_rung_for_the_bridge() -> None:
    line = await Line().ringing()
    await line.line.ring_user("call_1", "user_9")

    assert LISTEN_SID in line.calls.ended
    assert len(line.calls.created) == 3
    assert ListenEnded(reason="failed") in await line.events()


async def test_a_failed_move_ends_the_listener_and_rings_instead() -> None:
    line, _ = await Line().listening()
    line.calls.fail_update = True
    await line.line.ring_user("call_1", "user_9")

    assert LISTEN_SID in line.calls.ended
    assert line.calls.created[-1]["status"].endswith("/user/status")


async def test_a_request_once_the_call_is_over_or_bridged_is_refused() -> None:
    line = Line()
    assert line.line.request_listen_in() == "call_over"  # not dialed yet
    await line.answered()
    await line.line.ring_user("call_1", "user_9")
    assert line.line.request_listen_in() == "rep_on_line"
    await line.line.hang_up()
    assert line.line.request_listen_in() == "call_over"


async def test_hanging_up_ends_the_listen_leg() -> None:
    line, _ = await Line().listening()
    await line.events()
    assert line.calls.ended == [LISTEN_SID]
    assert line.line.request_listen_in() == "call_over"
    assert line.calls.completed == [SID]


async def test_request_listen_in_finds_the_live_line() -> None:
    assert control.request_listen_in("call_nobody") == "call_over"
    line = Line(registry=LINES)
    await line.answered("call_listen_api")
    try:
        assert control.request_listen_in("call_listen_api") == "ringing"
    finally:
        await line.line.hang_up()


# Hanging up on request


async def test_a_hang_up_request_goes_to_the_runner_as_an_event() -> None:
    line = Line()
    assert line.line.request_hang_up() == "call_over"  # not dialed yet
    await line.answered()
    assert line.line.request_hang_up() == "ending"
    assert line.calls.completed == []  # the runner hangs up, not the request
    assert await line.events() == [AgencyAnswered(), HangUpRequested()]
    assert line.line.request_hang_up() == "call_over"


async def test_request_hang_up_finds_the_live_line() -> None:
    assert control.request_hang_up("call_nobody") == "call_over"
    line = Line(registry=LINES)
    await line.answered("call_hang_up_api")
    try:
        assert control.request_hang_up("call_hang_up_api") == "ending"
    finally:
        await line.line.hang_up()


# The routes


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    settings = Settings(public_base_url=BASE, twilio_auth_token=TOKEN)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, base_url=BASE) as test_client:
        yield test_client


def _post(client: TestClient, path: str, params: dict[str, str]) -> Any:
    signature = RequestValidator(TOKEN).compute_signature(BASE + path, params)
    return client.post(path, data=params, headers={"X-Twilio-Signature": signature})


async def test_signed_listen_callbacks_reach_the_line(client: TestClient) -> None:
    line = Line(registry=LINES)
    await line.answered("call_route_listen")
    line.line.request_listen_in()
    await line.line.listen_in("call_route_listen", "user_9")
    base = "/phone/calls/call_route_listen/listen"
    try:
        joined = _post(client, f"{base}/joined", {"CallSid": LISTEN_SID})
        assert "/listen/stream" in joined.text
        # They hear that it worked before the call plays (a quiet menu was silence).
        said = joined.text.index("<Say")
        assert said < joined.text.index("<Connect>")
        status = _post(
            client, f"{base}/status", {"CallSid": LISTEN_SID, "CallStatus": "completed"}
        )
        assert status.status_code == 204
        assert (await line.events())[-1] == ListenEnded(reason="hung_up")
    finally:
        await line.line.hang_up()


@pytest.mark.parametrize("leaf", ["status", "joined", "missed"])
def test_unsigned_listen_callbacks_are_refused(client: TestClient, leaf: str) -> None:
    response = client.post(f"/phone/calls/call_x/listen/{leaf}", data={"CallSid": "x"})
    assert response.status_code == 403


def test_a_listen_key_press_for_no_live_call_hangs_up(client: TestClient) -> None:
    response = _post(client, "/phone/calls/call_gone/listen/joined", {"CallSid": "x"})
    assert "<Hangup" in response.text
