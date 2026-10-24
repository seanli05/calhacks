from typing import Any

import pytest
from app.db import deletes, reads, tables
from app.db.errors import NotFound
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Records which delete helper got which ID; `*_missing` IDs raise NotFound."""
    seen: list[tuple[str, str]] = []
    for name in (
        "delete_fact",
        "delete_document",
        "delete_transcript",
        "delete_everything",
    ):

        async def fake(row_id: str, _name: str = name) -> Any:
            if row_id.endswith("_missing"):
                raise NotFound(row_id)
            seen.append((_name, row_id))
            return {"facts": 3}

        monkeypatch.setattr(deletes, name, fake)
    return seen


@pytest.mark.parametrize(
    ("path", "helper"),
    [
        ("/api/facts/fact_1", "delete_fact"),
        ("/api/documents/doc_1", "delete_document"),
        ("/api/transcripts/transcript_1", "delete_transcript"),
    ],
)
def test_delete_routes_call_their_helper(
    calls: list[tuple[str, str]], path: str, helper: str
) -> None:
    response = client.delete(path)
    assert response.status_code == 204
    assert calls == [(helper, path.rsplit("/", 1)[1])]


def test_delete_of_missing_row_is_404(calls: list[tuple[str, str]]) -> None:
    assert client.delete("/api/facts/fact_missing").status_code == 404
    assert client.post("/api/users/user_missing/delete-everything").status_code == 404
    assert calls == []


def test_delete_everything_returns_counts(calls: list[tuple[str, str]]) -> None:
    response = client.post("/api/users/user_1/delete-everything")
    assert response.json() == {"facts": 3}
    assert calls == [("delete_everything", "user_1")]


def test_memory_lists_facts_documents_and_transcripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = tables.User(whatsapp_number="+15555550100", language="es")
    document = tables.Document(user_id=user.id, pages=[{"media_id": "media_1"}])
    case = tables.Case(
        user_id=user.id, document_ids=[document.id], doc_type="uscis_i797c"
    )
    fact = tables.Fact(
        user_id=user.id,
        fact="Prefers voice notes",
        category="contact",
        source="user_said",
        sensitivity="normal",
        status="active",
    )
    transcript = tables.Transcript(call_id="call_1")
    fakes: dict[str, Any] = {
        "get_user": user,
        "get_profile": tables.Profile(user_id=user.id, fields={"household_size": 3}),
        "list_cases": [case],
        "list_facts": [fact],
        "list_documents": [document],
        "list_transcripts": [(transcript, case.id)],
    }
    for name, value in fakes.items():

        async def fake(*_: Any, _value: Any = value) -> Any:
            return _value

        monkeypatch.setattr(reads, name, fake)

    body = client.get(f"/api/users/{user.id}/memory").json()
    assert body["profile"] == {"household_size": "3"}
    assert body["facts"][0]["fact"] == {
        "text": "Prefers voice notes",
        "en": "Prefers voice notes",
    }
    assert body["documents"][0] | {"created_at": None} == {
        "id": document.id,
        "doc_type": "uscis_i797c",
        "case_id": case.id,
        "page_media_ids": ["media_1"],
        "created_at": None,
    }
    assert body["transcripts"][0]["case_id"] == case.id
