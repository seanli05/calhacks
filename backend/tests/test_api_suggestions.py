from datetime import date
from typing import Any

import pytest
from app.api import suggestions
from app.db import reads, tables
from app.db.reset import demo_brief, demo_fast_result
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
USER = tables.User(whatsapp_number="+15555550100", language="es")


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    fast_result: dict | None,
    brief: dict | None = None,
    glossary: tuple[str, ...] = (),
) -> tables.Case:
    case = tables.Case(user_id=USER.id, doc_type="uscis_i797c_asylum_interview")
    case.fast_result = fast_result
    brief_row = tables.CaseBrief(case_id=case.id, handoff_note="n", brief=brief or {})
    terms = [
        tables.GlossaryTerm(term=t, language="es", translation=t, trust_level="machine")
        for t in glossary
    ]
    fakes: dict[str, Any] = {
        "get_user": USER,
        "list_active_cases": [case],
        "latest_brief": brief_row if brief else None,
        "get_glossary": terms,
    }
    for name, value in fakes.items():

        async def fake(*_: Any, _value: Any = value) -> Any:
            return _value

        monkeypatch.setattr(reads, name, fake)
    monkeypatch.setattr(suggestions, "today", lambda: date(2026, 10, 23))
    return case


def _get(case: tables.Case) -> list[dict]:
    return client.get(f"/api/users/{case.user_id}/suggestions").json()


def test_demo_case_gets_all_three_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _serve(
        monkeypatch,
        demo_fast_result("case_1"),
        demo_brief("case_1", "brief_1"),
        glossary=("asylum interview", "interpreter", "dependent"),
    )
    countdown, glossary, checklist = _get(case)
    assert countdown["title"]["text"] == "Tu entrevista es en 20 días"
    assert countdown["title"]["en"] == "Your interview is in 20 days"
    assert countdown["prefill"] == "¿Qué tengo que llevar a mi entrevista?"
    assert glossary["detail"]["text"] == "asylum interview · interpreter · dependent"
    assert checklist["title"] == {
        "text": "No olvides: un intérprete calificado si no hablas inglés con fluidez",
        "en": "Don't forget: a qualified interpreter if you are not fluent in English",
    }
    assert checklist["prefill"] == (
        "¿Cómo consigo un intérprete calificado si no hablas inglés con fluidez?"
    )


def test_rules_without_data_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    fast = demo_fast_result("case_1") | {"appointment": None, "deadline": None}
    case = _serve(monkeypatch, fast, demo_brief("case_1", "brief_1"), glossary=())
    assert [s["kind"] for s in _get(case)] == ["checklist"]


def test_no_fast_result_means_no_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _serve(monkeypatch, None)
    assert _get(case) == []
