"""Twilio's ways into a live call (`phone/routes.py`): signed status callbacks and
join-gate callbacks reach the call's line; unsigned ones and unknown calls are
refused, and a gate callback for no live call hangs the applicant up."""

from collections.abc import Iterator

import pytest
from app.phone.fakes import FakeNumberSource
from app.phone.line import AgencyAnswered, UserAnswered, UserUnreachable
from app.phone.routes import router
from app.phone.twilio_line import LINES, TwilioTelephony
from app.phone.twilio_urls import LineUrls
from app.settings import Settings, get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

BASE = "https://agent.example.app"
TOKEN = "test-auth-token"
SID = "CA123"
USER_SID = "CA456"


class _Calls:
    def __init__(self) -> None:
        self.created = 0

    async def create(self, *, to: str, twiml: str, status_callback: str) -> str:
        self.created += 1
        return SID if self.created == 1 else USER_SID

    async def update_twiml(self, sid: str, twiml: str) -> None: ...
    async def complete(self, sid: str) -> None: ...
    async def end(self, sid: str) -> None: ...
    async def status(self, sid: str) -> str:
        return "completed"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    settings = Settings(public_base_url=BASE, twilio_auth_token=TOKEN)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, base_url=BASE) as test_client:
        yield test_client


def _signed(path: str, params: dict[str, str]) -> dict[str, str]:
    signature = RequestValidator(TOKEN).compute_signature(BASE + path, params)
    return {"X-Twilio-Signature": signature}


def _line() -> TwilioTelephony:
    return TwilioTelephony(
        FakeNumberSource({"case_1": "+18005550100"}, users={"user_9": "+15555550123"}),
        _Calls(),
        LineUrls(BASE),
        user_language="es",
    )


async def _rung_line() -> TwilioTelephony:
    line = _line()
    await line.dial_agency("call_route", "case_1")
    line.on_status(SID, "in-progress")
    await line.ring_user("call_route", "user_9")
    return line


async def _events(line: TwilioTelephony) -> list[object]:
    await line.hang_up()
    return [event async for event in line.events()]


async def test_a_signed_status_reaches_the_calls_line(client: TestClient) -> None:
    line = _line()
    await line.dial_agency("call_route", "case_1")
    try:
        path = "/phone/calls/call_route/status"
        params = {"CallSid": SID, "CallStatus": "in-progress"}
        response = client.post(path, data=params, headers=_signed(path, params))

        assert response.status_code == 204
        await line.hang_up()
        assert [event async for event in line.events()] == [AgencyAnswered()]
    finally:
        await line.hang_up()
    assert LINES.get("call_route") is None


def test_an_unsigned_status_is_refused(client: TestClient) -> None:
    path = "/phone/calls/call_route/status"
    params = {"CallSid": SID, "CallStatus": "completed"}
    response = client.post(path, data=params, headers={"X-Twilio-Signature": "nope"})
    assert response.status_code == 403


def test_a_status_for_no_live_call_is_accepted_and_dropped(client: TestClient) -> None:
    path = "/phone/calls/call_gone/status"
    params = {"CallSid": SID, "CallStatus": "completed"}
    response = client.post(path, data=params, headers=_signed(path, params))
    assert response.status_code == 204


def test_a_stream_for_no_live_call_is_refused(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/phone/calls/call_gone/stream"),
    ):
        pass


# The applicant's leg


async def test_a_key_press_joins_the_conference(client: TestClient) -> None:
    line = await _rung_line()
    try:
        path = "/phone/calls/call_route/user/joined"
        params = {"CallSid": USER_SID, "Digits": "5"}
        response = client.post(path, data=params, headers=_signed(path, params))

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/xml")
        assert ">bridge-call_route</Conference>" in response.text
        assert await _events(line) == [AgencyAnswered(), UserAnswered()]
    finally:
        await line.hang_up()


async def test_no_key_press_hangs_up_and_is_unreachable(client: TestClient) -> None:
    line = await _rung_line()
    try:
        path = "/phone/calls/call_route/user/missed"
        params = {"CallSid": USER_SID}
        response = client.post(path, data=params, headers=_signed(path, params))

        assert "<Hangup" in response.text
        assert await _events(line) == [
            AgencyAnswered(),
            UserUnreachable(reason="no_key_press"),
        ]
    finally:
        await line.hang_up()


async def test_a_signed_applicant_status_reaches_the_line(client: TestClient) -> None:
    line = await _rung_line()
    try:
        path = "/phone/calls/call_route/user/status"
        params = {"CallSid": USER_SID, "CallStatus": "busy"}
        response = client.post(path, data=params, headers=_signed(path, params))

        assert response.status_code == 204
        assert await _events(line) == [
            AgencyAnswered(),
            UserUnreachable(reason="busy"),
        ]
    finally:
        await line.hang_up()


@pytest.mark.parametrize("leaf", ["status", "joined", "missed"])
def test_unsigned_applicant_callbacks_are_refused(
    client: TestClient, leaf: str
) -> None:
    path = f"/phone/calls/call_route/user/{leaf}"
    params = {"CallSid": USER_SID, "CallStatus": "completed"}
    response = client.post(path, data=params, headers={"X-Twilio-Signature": "nope"})
    assert response.status_code == 403


def test_a_key_press_for_no_live_call_hangs_up(client: TestClient) -> None:
    path = "/phone/calls/call_gone/user/joined"
    params = {"CallSid": USER_SID, "Digits": "1"}
    response = client.post(path, data=params, headers=_signed(path, params))
    assert response.status_code == 200
    assert "<Hangup" in response.text


@pytest.mark.parametrize("speaker", ["user", "agent"])
def test_a_fork_for_no_live_call_or_an_unknown_speaker_is_refused(
    client: TestClient, speaker: str
) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/phone/calls/call_gone/fork/{speaker}"),
    ):
        pass
