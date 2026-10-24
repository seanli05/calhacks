"""The API end to end on a freshly seeded database. Runs only when TEST_DATABASE_URL
is set; like test_db_helpers.py, it drops every table there first."""

from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx
import pytest
from app.db import reset
from app.db.engine import get_engine
from app.db.schema import create_all, drop_all
from app.main import app
from app.settings import Settings, get_settings, to_asyncpg_url

TEST_DATABASE_URL = Settings().test_database_url

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set"
)


@pytest.fixture
async def api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    shared_host = urlsplit(Settings().async_database_url).hostname
    if urlsplit(to_asyncpg_url(TEST_DATABASE_URL)).hostname == shared_host:
        pytest.exit("TEST_DATABASE_URL points at the shared database; refusing.")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", TEST_DATABASE_URL)
    get_settings.cache_clear()
    get_engine.cache_clear()
    await drop_all()
    await create_all()
    # In-process ASGI, so the routes share this test's event loop and pool.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


async def test_seeded_case_end_to_end(api: httpx.AsyncClient) -> None:
    case_id = await reset.seed()
    demo = (await api.get("/api/demo")).json()
    assert demo["case_id"] == case_id

    response = await api.get(f"/api/cases/{case_id}")
    assert response.status_code == 200
    case = response.json()
    assert case["stage"] == "awaiting_consent"
    assert {r["name"]: r["masked"] for r in case["refs"]} == {
        "a_number": "•••• 5678",
        "receipt_number": "•••• 2345",
    }
    for secret in ("ZLA2690012345", "A212345678", "1988-03-14"):
        assert secret not in response.text
    assert case["appointment"]["location"].startswith("Los Angeles Asylum Office")
    assert len(case["checklist"]) == 3 and case["calls"] == []

    image = await api.get(f"/api/media/{case['page_media_ids'][0]}")
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")

    user_id = case["user_id"]
    feed = (await api.get(f"/api/users/{user_id}/feed")).json()
    texts = [item["text"]["text"] for item in feed]
    assert texts[0] == "Recibimos tu carta"
    assert "Guardamos: Prefieres mensajes de voz" in texts
    assert "Confirmamos que la carta es real (uscis.gov)" in texts
    assert texts[-1] == "Te preguntamos si quieres que llamemos a USCIS"

    suggestions = (await api.get(f"/api/users/{user_id}/suggestions")).json()
    assert [s["kind"] for s in suggestions] == ["countdown", "glossary", "checklist"]
    memory = (await api.get(f"/api/users/{user_id}/memory")).json()
    assert len(memory["facts"]) == 3 and memory["documents"][0]["case_id"] == case_id
    messages = (await api.get(f"/api/users/{user_id}/messages")).json()
    assert messages[0]["media_ids"] == case["page_media_ids"]

    fact_id = memory["facts"][0]["id"]
    assert (await api.delete(f"/api/facts/{fact_id}")).status_code == 204
    assert (await api.delete(f"/api/facts/{fact_id}")).status_code == 404
    feed = (await api.get(f"/api/users/{user_id}/feed")).json()
    deleted = [item for item in feed if item["deleted_at"]]
    assert [item["text"]["text"] for item in deleted] == ["Guardamos un dato sobre ti"]


async def test_after_call_seed_has_report_and_transcript(
    api: httpx.AsyncClient,
) -> None:
    case_id = await reset.seed(after_call=True)
    case = (await api.get(f"/api/cases/{case_id}?lang=en")).json()
    assert case["stage"] == "call_ended"
    (call,) = case["calls"]
    assert call["outcome"] == "resolved" and call["hold_started_at"]
    assert call["report"]["rep_name"] == "Officer Lee"
    transcript = (await api.get(f"/api/calls/{call['id']}/transcript")).json()
    assert transcript["id"] == call["transcript_id"]
    assert transcript["lines"][0]["speaker"] == "agency"

    feed = (await api.get(f"/api/users/{case['user_id']}/feed?lang=en")).json()
    texts = [item["text"]["text"] for item in feed]
    assert "We chose option 2 in the menu" in texts
    assert "You said yes to the call" in texts
    assert texts[-1] == "The call ended after 14 min"
