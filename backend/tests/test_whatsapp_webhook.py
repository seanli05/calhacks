import base64
from collections.abc import AsyncIterator, Callable, Iterator

import httpx
import pytest
from app.main import app
from app.relay.media import get_media_client
from app.settings import Settings, get_settings
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

PUBLIC_BASE_URL = "https://example.ngrok.app"
ACCOUNT_SID = "ACtest"
AUTH_TOKEN = "test-token"
MEDIA_URL = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/MM1/Media/ME1"
CDN_URL = "https://cdn.example.com/signed-object"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def make_client() -> Iterator[Callable[[Handler], TestClient]]:
    settings = Settings(
        _env_file=None,
        twilio_account_sid=ACCOUNT_SID,
        twilio_auth_token=AUTH_TOKEN,
        public_base_url=PUBLIC_BASE_URL,
    )

    def _make(handler: Handler) -> TestClient:
        async def fake_media_client() -> AsyncIterator[httpx.AsyncClient]:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                yield client

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_media_client] = fake_media_client
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request to {request.url}")


def not_found(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


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


def test_text_message_is_echoed(make_client: Callable[[Handler], TestClient]) -> None:
    client = make_client(no_network)
    form = twilio_form()

    response = client.post("/whatsapp", data=form, headers=sign(form))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Message>Echo: hola</Message>" in response.text


def test_bad_signature_is_rejected(
    make_client: Callable[[Handler], TestClient],
) -> None:
    client = make_client(no_network)
    form = twilio_form()

    assert client.post("/whatsapp", data=form).status_code == 403
    tampered = twilio_form(Body="other")
    assert (
        client.post("/whatsapp", data=tampered, headers=sign(form)).status_code == 403
    )


def test_photo_is_downloaded_with_twilio_auth(
    make_client: Callable[[Handler], TestClient],
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == MEDIA_URL:
            return httpx.Response(307, headers={"Location": CDN_URL})
        return httpx.Response(200, content=b"\xff\xd8fakejpeg" * 300)

    client = make_client(handler)
    form = twilio_form(
        Body="", NumMedia="1", MediaUrl0=MEDIA_URL, MediaContentType0="image/jpeg"
    )

    response = client.post("/whatsapp", data=form, headers=sign(form))

    assert response.status_code == 200
    assert "Got your image/jpeg (3 KB)" in response.text

    expected_auth = (
        "Basic " + base64.b64encode(f"{ACCOUNT_SID}:{AUTH_TOKEN}".encode()).decode()
    )
    twilio_request, cdn_request = seen
    assert twilio_request.headers["Authorization"] == expected_auth
    assert "Authorization" not in cdn_request.headers


@pytest.mark.parametrize("failure", [not_found, timeout])
def test_media_failure_gets_friendly_reply(
    make_client: Callable[[Handler], TestClient], failure: Handler
) -> None:
    client = make_client(failure)
    form = twilio_form(
        NumMedia="1", MediaUrl0=MEDIA_URL, MediaContentType0="image/jpeg"
    )

    response = client.post("/whatsapp", data=form, headers=sign(form))

    assert response.status_code == 200
    assert "download that" in response.text
