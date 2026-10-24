from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest
from app.api.feed_templates import TEMPLATES, fields_of
from app.contracts import Component, Event, EventType
from app.db import reads, tables
from app.main import app
from fastapi.testclient import TestClient

T0 = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
USER = tables.User(whatsapp_number="+15555550100", language="es")
_ids = count()


def _event(event_type: EventType, **data: Any) -> Event:
    n = next(_ids)
    return Event(
        event_id=f"event_{n}",
        created_at=T0 + timedelta(minutes=n),
        type=event_type,
        source=Component.PHONE_AGENT,
        user_id=USER.id,
        summary_en=f"summary of {event_type}",
        data=data,
    )


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    events: list[Event],
    facts: tuple[tables.Fact, ...] = (),
) -> TestClient:
    async def list_events(user_id: str, since: datetime | None = None) -> list[Event]:
        return [e for e in events if since is None or e.created_at > since]

    async def list_facts(user_id: str) -> list[tables.Fact]:
        return list(facts)

    async def get_user(user_id: str) -> tables.User:
        return USER

    async def list_documents(user_id: str) -> list[tables.Document]:
        return []

    monkeypatch.setattr(reads, "list_events", list_events)
    monkeypatch.setattr(reads, "list_facts", list_facts)
    monkeypatch.setattr(reads, "get_user", get_user)
    monkeypatch.setattr(reads, "list_documents", list_documents)
    monkeypatch.setattr(reads, "list_cases", list_documents)
    return TestClient(app)


def _texts(client: TestClient, query: str = "") -> list[dict]:
    response = client.get(f"/api/users/{USER.id}/feed{query}")
    assert response.status_code == 200
    return response.json()


def test_every_type_ends_with_a_variant_without_fields() -> None:
    for event_type, variants in TEMPLATES.items():
        assert "en" in variants and "es" in variants, event_type
        for lang_variants in variants.values():
            assert not fields_of(lang_variants[-1]), event_type


def test_template_renders_in_spanish_from_data(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _serve(monkeypatch, [_event(EventType.CALL_MENU_CHOICE, digit="2")])
    (item,) = _texts(client)
    assert item["text"] == {
        "text": "Elegimos la opción 2 del menú",
        "en": "We chose option 2 in the menu",
    }


def test_missing_data_falls_back_to_variant_without_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _serve(monkeypatch, [_event(EventType.CALL_MENU_CHOICE, heard="...")])
    (item,) = _texts(client, "?lang=en")
    assert item["text"]["text"] == "We chose an option in the menu"


def test_untemplated_type_shows_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _serve(monkeypatch, [_event(EventType.GLOSSARY_TERM_ADDED)])
    (item,) = _texts(client)
    expected = "summary of glossary.term_added"
    assert item["text"] == {"text": expected, "en": expected}


def test_fact_text_is_looked_up_at_render_time(monkeypatch: pytest.MonkeyPatch) -> None:
    fact = tables.Fact(
        user_id=USER.id,
        fact="Lives in Los Angeles County",
        category="contact",
        source="user_said",
        sensitivity="normal",
        status="active",
    )
    client = _serve(
        monkeypatch, [_event(EventType.MEMORY_FACT_SAVED, fact_id=fact.id)], (fact,)
    )
    (item,) = _texts(client)
    assert item["text"] == {
        "text": "Guardamos: Vives en el condado de Los Ángeles",
        "en": "Saved: Lives in Los Angeles County",
    }
    assert item["deleted_at"] is None


def test_deleted_fact_renders_with_deleted_at_and_without_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _event(EventType.MEMORY_FACT_SAVED, fact_id="fact_gone")
    deleted = _event(EventType.FACT_DELETED, fact_id="fact_gone")
    client = _serve(monkeypatch, [saved, deleted])
    first, second = _texts(client)
    assert first["text"]["text"] == "Guardamos un dato sobre ti"
    assert first["deleted_at"] == deleted.created_at.isoformat().replace("+00:00", "Z")
    assert second["text"]["text"] == "Borraste un dato"
    assert second["deleted_at"] is None


def test_since_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [_event(EventType.CONSENT_REQUESTED), _event(EventType.CONSENT_GIVEN)]
    client = _serve(monkeypatch, events)
    since = events[0].created_at.isoformat().replace("+00:00", "Z")
    assert [i["id"] for i in _texts(client, f"?since={since}")] == [events[1].event_id]
