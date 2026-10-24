"""Twilio's ways into a live call (`phone/routes.py`): signed status callbacks reach
the call's line; unsigned ones and unknown calls are refused."""

from collections.abc import Iterator

import pytest
from app.phone.fakes import FakeNumberSource
from app.phone.line import AgencyAnswered
from app.phone.routes import router
from app.phone.twilio_line import LINES, LineUrls, TwilioTelephony
from app.settings import Settings, get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

BASE = "https://agent.example.app"
TOKEN = "test-auth-token"
SID = "CA123"


class _Calls:
    async def create(self, *, to: str, twiml: str, status_callback: str) -> str:
        return SID

    async def update_twiml(self, sid: str, twiml: str) -> None: ...
    async def complete(self, sid: str) -> None: ...
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


async def test_a_signed_status_reaches_the_calls_line(client: TestClient) -> None:
    line = TwilioTelephony(
        FakeNumberSource({"case_1": "+18005550100"}), _Calls(), LineUrls(BASE)
    )
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
