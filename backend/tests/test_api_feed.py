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


def test_research_step_log_is_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _event(EventType.RESEARCH_DEEP_STARTED),
        _event(EventType.RESEARCH_SEARCH),
        _event(EventType.RESEARCH_FETCH),
        _event(EventType.RESEARCH_CHECK),
        _event(EventType.RESEARCH_DEEP_DONE),
    ]
    client = _serve(monkeypatch, events)
    assert [item["type"] for item in _texts(client)] == [
        "research.deep_started",
        "research.deep_done",
    ]


def test_every_research_type_is_templated_or_hidden() -> None:
    from app.api.feed_templates import HIDDEN

    research = {t for t in EventType if t.startswith("research.")}
    assert research <= set(TEMPLATES) | HIDDEN


def test_steps_come_with_the_task_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _event(EventType.RESEARCH_DEEP_STARTED),
        _event(EventType.RESEARCH_SEARCH, query="USCIS contact center phone"),
        _event(
            EventType.RESEARCH_FETCH,
            url="https://www.uscis.gov/contactcenter/",
            final_url="https://www.uscis.gov/contactcenter/",
            status=200,
        ),
        _event(EventType.RESEARCH_CHECK, check="scam_rules", red_flags=[]),
        _event(
            EventType.RESEARCH_CHECK,
            check="letter_phone",
            state="conflict",
            evidence=["never shown"],
        ),
        _event(EventType.CALL_MENU_HEARD, phase="menu", action="press"),
        _event(EventType.RESEARCH_DEEP_DONE),
    ]
    items = _texts(_serve(monkeypatch, events), "?steps=true")
    steps = [item["step"] for item in items]
    assert steps[0] is None and steps[-1] is None
    search, fetch, scam, phone, menu = steps[1:6]
    assert search["action"] == {"text": "Buscando", "en": "Searching"}
    assert search["detail"] == '"USCIS contact center phone"'
    assert fetch["detail"] == "uscis.gov/contactcenter"
    assert fetch["ok"] is True
    assert scam["result"]["text"] == "0 alertas"
    assert scam["ok"] is True
    assert phone["result"]["en"] == "doesn't match"
    assert phone["ok"] is False
    assert "never shown" not in str(items)
    assert menu["result"]["text"] == "marcar"


def test_steps_say_why(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _event(
            EventType.RESEARCH_CHECK,
            check="letter_read",
            status="ok",
            doc_type="uscis_i797c",
        ),
        _event(EventType.RESEARCH_CHECK, check="private_values", count=3),
        _event(EventType.RESEARCH_CHECK, check="urgency", urgency="high", dates=2),
        _event(
            EventType.RESEARCH_CHECK,
            check="scam_rules",
            red_flags=["This letter asks for gift cards. USCIS never asks for that."],
        ),
        _event(EventType.RESEARCH_CHECK, check="letter_phone", state="match"),
        _event(
            EventType.RESEARCH_CHECK,
            check="verdict",
            status="verified",
            official_phone_found=True,
        ),
        _event(
            EventType.CALL_MENU_HEARD,
            phase="menu",
            action="press",
            reading_reason_en="Lists numbered options",
            reason_en="Option 2 is for scheduled interviews",
        ),
    ]
    steps = [
        item["step"] for item in _texts(_serve(monkeypatch, events), "?steps=true")
    ]
    read, private, urgency, scam, phone, verdict, menu = steps
    assert read["result"]["en"] == "read" and read["reason"] == "Read as: uscis i797c."
    assert (
        private["result"]["en"] == "3 set aside" and "placeholders" in private["reason"]
    )
    assert urgency["result"]["en"] == "high"
    assert urgency["reason"] == "Based on 2 dates on the letter."
    assert scam["reason"].startswith("This letter asks for gift cards.")
    assert "listed for the issuer" in phone["reason"]
    assert "official phone number was found" in verdict["reason"]
    assert (
        menu["reason"]
        == "Lists numbered options. Option 2 is for scheduled interviews."
    )


def test_reasons_are_masked_at_the_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _event(
            EventType.CALL_MENU_HEARD,
            phase="menu",
            action="say",
            reading_reason_en="Asked for 123-456-789",
            reason_en="Said <ref:receipt_number>",
        ),
        _event(EventType.RESEARCH_CHECK, check="issuer", state="match", evidence=["x"]),
    ]
    menu, issuer = (
        item["step"] for item in _texts(_serve(monkeypatch, events), "?steps=true")
    )
    assert menu["reason"] == "Asked for [number]. Said [hidden]."
    assert issuer["reason"] and "x" not in issuer["reason"].split()


def test_a_failed_lookup_is_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _event(EventType.RESEARCH_SEARCH, error="max_uses_exceeded"),
        _event(
            EventType.RESEARCH_FETCH, url="https://example.com/x", refused="off-list"
        ),
        _event(
            EventType.RESEARCH_FETCH,
            url="https://www.uscis.gov/contactcenter",
            final_url="https://www.uscis.gov/contactcenter",
            status=403,
        ),
    ]
    search, fetch, denied = (
        item["step"] for item in _texts(_serve(monkeypatch, events), "?steps=true")
    )
    assert (denied["ok"], denied["result"]["en"]) == (False, "failed")
    assert (search["ok"], search["result"]["en"]) == (False, "failed")
    assert (fetch["ok"], fetch["result"]["en"], fetch["detail"]) == (
        False,
        "blocked",
        "example.com/x",
    )


def test_a_language_without_templates_goes_through_the_translator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import translations

    monkeypatch.setattr(translations, "cached", lambda en, lang: f"[{lang}] {en}")
    events = [
        _event(EventType.CONSENT_GIVEN),
        _event(EventType.RESEARCH_SEARCH, query="USCIS phone"),
    ]
    consent, search = _texts(_serve(monkeypatch, events), "?lang=fa&steps=true")
    assert consent["text"] == {
        "text": "[fa] You said yes to the call",
        "en": "You said yes to the call",
    }
    assert search["step"]["action"]["text"] == "[fa] Searching"
    assert search["step"]["detail"] == '"USCIS phone"'
