from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from app.contracts import Component, Event, EventType
from app.db import reads, tables
from app.db.errors import NotFound
from app.db.progress import CaseStage
from app.db.reset import DEMO_REFS, demo_brief, demo_fast_result
from app.main import app
from fastapi.testclient import TestClient

HOLD_AT = datetime(2026, 10, 23, 10, 5, tzinfo=UTC)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)


def _patch(monkeypatch: pytest.MonkeyPatch, **fakes: Any) -> None:
    for name, value in fakes.items():

        async def fake(*_: Any, _value: Any = value, **__: Any) -> Any:
            return _value

        monkeypatch.setattr(reads, name, fake)


@pytest.fixture
def demo_case(monkeypatch: pytest.MonkeyPatch) -> tables.Case:
    """The seeded demo case, served by faked reads (no database)."""
    user = tables.User(whatsapp_number="+15555550100", language="es")
    media = tables.Media(user_id=user.id, content_type="image/png", data=b"")
    document = tables.Document(user_id=user.id, pages=[{"media_id": media.id}])
    case = tables.Case(
        user_id=user.id,
        document_ids=[document.id],
        doc_type="uscis_i797c_asylum_interview",
    )
    case.fast_result = demo_fast_result(case.id)
    brief = tables.CaseBrief(case_id=case.id, handoff_note="note")
    brief.brief = demo_brief(case.id, brief.id)
    call = tables.Call(
        case_id=case.id, job_id="job_1", brief_id=brief.id, consent_message_id="msg_1"
    )
    on_hold = Event(
        event_id="event_1",
        created_at=HOLD_AT,
        type=EventType.CALL_ON_HOLD,
        source=Component.PHONE_AGENT,
        user_id=user.id,
        call_id=call.id,
        summary_en="On hold",
    )

    async def resolve_ref(case_id: str, name: str) -> str:
        key = name.removeprefix("<ref:").removesuffix(">")
        if key not in DEMO_REFS:
            raise NotFound(key)
        return DEMO_REFS[key]

    monkeypatch.setattr(reads, "resolve_ref", resolve_ref)
    _patch(
        monkeypatch,
        get_user=user,
        get_case=case,
        get_document=document,
        case_progress=CaseStage.ON_HOLD,
        list_active_cases=[case],
        list_case_refs=[
            tables.CaseRef(case_id=case.id, name=name, value=value)
            for name, value in DEMO_REFS.items()
        ],
        latest_verification=tables.Verification(
            case_id=case.id,
            status="verified",
            result={
                "status": "verified",
                "official_phone": "+15555550199",
                "letter_phone_matches": None,
                "evidence": ["https://www.uscis.gov/contactcenter"],
                "red_flags": [],
            },
        ),
        latest_brief=brief,
        list_calls=[call],
        latest_event=on_hold,
        get_transcript=None,
    )
    return case


def test_case_detail_masks_refs_and_never_sends_date_of_birth(
    client: TestClient, demo_case: tables.Case
) -> None:
    response = client.get(f"/api/cases/{demo_case.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["refs"] == [
        {"name": "receipt_number", "masked": "•••• 2345"},
        {"name": "a_number", "masked": "•••• 5678"},
    ]
    for secret in ("ZLA2690012345", "A212345678", "1988-03-14", "date_of_birth"):
        assert secret not in response.text
    assert body["appointment"] == {
        "date": "2026-11-12",
        "time": "08:30",
        "location": DEMO_REFS["interview_location"],
    }


def test_case_detail_shape(client: TestClient, demo_case: tables.Case) -> None:
    body = client.get(f"/api/cases/{demo_case.id}?lang=es").json()
    assert body["issuer"] == "USCIS"
    assert body["stage"] == "on_hold"
    assert body["page_media_ids"] and body["document_id"] == demo_case.document_ids[0]
    assert body["explanation"]["en"].startswith("This is a notice")
    assert body["checklist"][0]["kind"] == "who_must_come"
    assert body["verification"]["evidence"] == ["https://www.uscis.gov/contactcenter"]
    assert body["brief"]["call_goal"]["en"].startswith("Confirm the asylum interview")
    assert len(body["brief"]["questions_to_ask"]) == 2
    (call,) = body["calls"]
    assert call["hold_started_at"] == "2026-10-23T10:05:00Z"
    assert call["transcript_id"] is None and call["report"] is None


def test_case_list_has_thumbnail_and_latest_call(
    client: TestClient, demo_case: tables.Case
) -> None:
    (summary,) = client.get(f"/api/users/{demo_case.user_id}/cases").json()
    assert summary["thumbnail_media_id"]
    assert summary["latest_call"]["state"] == "dialing"
    assert summary["appointment"]["time"] == "08:30"


def test_brief_with_missing_fields_is_null_not_an_error(
    client: TestClient, demo_case: tables.Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, latest_brief=tables.CaseBrief(case_id="c", handoff_note="n"))
    brief = client.get(f"/api/cases/{demo_case.id}").json()["brief"]
    assert brief == {"call_goal": None, "questions_to_ask": []}


def test_unknown_case_and_transcript_are_404(
    client: TestClient, demo_case: tables.Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, get_case=None, get_transcript=None)
    assert client.get("/api/cases/case_x").status_code == 404
    assert client.get("/api/calls/call_x/transcript").status_code == 404
