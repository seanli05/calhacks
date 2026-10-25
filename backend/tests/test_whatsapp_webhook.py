import base64
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from app.main import app
from app.orchestrator.pipe import get_pipe
from app.relay.inbound import InboundMessage
from app.relay.media import MediaDownloadError, download_media
from app.relay.whatsapp import TwilioWhatsApp
from app.settings import Settings, get_settings
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

PUBLIC_BASE_URL = "https://example.ngrok.app"
ACCOUNT_SID = "ACtest"
AUTH_TOKEN = "test-token"
MEDIA_URL = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM1/Media/ME1"
CDN_URL = "https://cdn.example.com/signed-object"

SETTINGS = Settings(
    _env_file=None,
    twilio_account_sid=ACCOUNT_SID,
    twilio_auth_token=AUTH_TOKEN,
    public_base_url=PUBLIC_BASE_URL,
)


class RecordingPipe:
    def __init__(self) -> None:
        self.handled: list[InboundMessage] = []

    async def handle(self, message: InboundMessage) -> None:
        self.handled.append(message)


@pytest.fixture
def pipe() -> Iterator[RecordingPipe]:
    recording = RecordingPipe()
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_pipe] = lambda: recording
    yield recording
    app.dependency_overrides.clear()


@pytest.fixture
def client(pipe: RecordingPipe) -> TestClient:
    return TestClient(app)


def twilio_form(**overrides: str) -> dict[str, str]:
    form = {
        "MessageSid": "SM123",
        "From": "whatsapp:+15105550123",
        "To": "whatsapp:+14155238886",
        "Body": "hola",
        "NumMedia": "0",
    }
    form.update(overrides)
    return form


def sign(form: dict[str, str]) -> dict[str, str]:
    signature = RequestValidator(AUTH_TOKEN).compute_signature(
        f"{PUBLIC_BASE_URL}/whatsapp", form
    )
    return {"X-Twilio-Signature": signature}


def test_message_is_acked_with_empty_twiml_and_queued(
    client: TestClient, pipe: RecordingPipe
) -> None:
    form = twilio_form()

    response = client.post("/whatsapp", data=form, headers=sign(form))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Message>" not in response.text
    [message] = pipe.handled
    assert message.text == "hola"
    assert message.whatsapp_number == "+15105550123"


def test_every_media_item_is_parsed(client: TestClient, pipe: RecordingPipe) -> None:
    form = twilio_form(
        Body="",
        NumMedia="2",
        MediaUrl0=MEDIA_URL,
        MediaContentType0="image/jpeg",
        MediaUrl1=MEDIA_URL + "2",
        MediaContentType1="application/pdf",
    )

    assert client.post("/whatsapp", data=form, headers=sign(form)).status_code == 200

    [message] = pipe.handled
    assert [item.content_type for item in message.media] == [
        "image/jpeg",
        "application/pdf",
    ]
    assert all(item.is_letter_page for item in message.media)


def test_bad_signature_is_rejected(client: TestClient, pipe: RecordingPipe) -> None:
    form = twilio_form()

    assert client.post("/whatsapp", data=form).status_code == 403
    tampered = twilio_form(Body="other")
    assert (
        client.post("/whatsapp", data=tampered, headers=sign(form)).status_code == 403
    )
    assert pipe.handled == []


def test_malformed_form_is_rejected(client: TestClient, pipe: RecordingPipe) -> None:
    form = twilio_form(NumMedia="lots")

    assert client.post("/whatsapp", data=form, headers=sign(form)).status_code == 400
    assert pipe.handled == []


async def test_media_is_downloaded_with_twilio_auth_only_to_twilio() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == MEDIA_URL:
            return httpx.Response(307, headers={"Location": CDN_URL})
        return httpx.Response(200, content=b"\xff\xd8fakejpeg")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        media = await download_media(http, MEDIA_URL, "image/jpeg", "SM1", SETTINGS)

    assert media.data == b"\xff\xd8fakejpeg"
    expected_auth = (
        "Basic " + base64.b64encode(f"{ACCOUNT_SID}:{AUTH_TOKEN}".encode()).decode()
    )
    twilio_request, cdn_request = seen
    assert twilio_request.headers["Authorization"] == expected_auth
    assert "Authorization" not in cdn_request.headers


def _not_found(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize("failure", [_not_found, _timeout])
async def test_media_failure_raises_without_the_url(
    failure: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(failure)) as http:
        with pytest.raises(MediaDownloadError) as caught:
            await download_media(http, MEDIA_URL, "image/jpeg", "SM1", SETTINGS)

    assert MEDIA_URL not in str(caught.value)


# The typing indicator (Twilio public beta)


async def test_typing_indicator_failure_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Best effort: a sandbox without the beta, or Twilio down, must not break a
    reply."""
    calls: list[dict[str, Any]] = []

    async def post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        twilio_account_sid="AC123",
        twilio_auth_token="token",
    )
    whatsapp = TwilioWhatsApp(settings)

    await whatsapp.typing("SM1")
    await whatsapp.typing("SM2")

    assert [c["json"] for c in calls] == [
        {"channel": "WHATSAPP", "messageId": "SM1"},
        {"channel": "WHATSAPP", "messageId": "SM2"},
    ]
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1
