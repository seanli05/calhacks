from collections.abc import Iterator

import pytest
from app.db import reads, tables
from app.main import app
from app.settings import Settings, get_settings
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def _settings(**values: str) -> Settings:
    return Settings(_env_file=None, **values)


def test_config_strips_whatsapp_prefix_and_builds_join_message(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_settings] = lambda: _settings(
        twilio_whatsapp_from="whatsapp:+14155238886",
        twilio_sandbox_join_code="purple-tiger",
    )
    assert client.get("/api/config").json() == {
        "whatsapp_number": "+14155238886",
        "sandbox_join_message": "join purple-tiger",
    }


def test_config_without_join_code(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _settings()
    assert client.get("/api/config").json()["sandbox_join_message"] is None


def test_demo_returns_first_user_and_newest_case(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tables.User(whatsapp_number="+15555550100", language="es")
    newest = tables.Case(user_id=user.id)

    async def first_user() -> tables.User:
        return user

    async def list_active_cases(user_id: str) -> list[tables.Case]:
        return [newest]

    monkeypatch.setattr(reads, "first_user", first_user)
    monkeypatch.setattr(reads, "list_active_cases", list_active_cases)
    assert client.get("/api/demo").json() == {
        "user_id": user.id,
        "case_id": newest.id,
    }


def test_unknown_user_and_media_are_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(_: str) -> None:
        return None

    monkeypatch.setattr(reads, "get_user", nothing)
    monkeypatch.setattr(reads, "get_media", nothing)
    assert client.get("/api/users/user_x").status_code == 404
    assert client.get("/api/media/media_x").status_code == 404


def test_media_returns_bytes_with_content_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = tables.Media(user_id="user_1", content_type="image/png", data=b"\x89PNG")

    async def get_media(_: str) -> tables.Media:
        return row

    monkeypatch.setattr(reads, "get_media", get_media)
    response = client.get(f"/api/media/{row.id}")
    assert response.content == b"\x89PNG"
    assert response.headers["content-type"] == "image/png"
