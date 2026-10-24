"""Fixtures for the WhatsApp side (pipe and relay), built on whatsapp_fakes."""

import pytest
from app.orchestrator.pipe import InboundPipe
from app.relay.ask_user import AskUser
from whatsapp_fakes import QUIET_S, FakeDB, FakeWhatsApp

_ORCHESTRATOR_WRITES = (
    "get_or_create_user",
    "set_language",
    "save_media",
    "create_document",
    "add_pages",
)
_RELAY_WRITES = (
    "create_question",
    "answer_question",
    "time_out_question",
    "record_late_reply",
)
_READS = (
    "list_messages",
    "list_active_cases",
    "get_open_question",
    "get_call",
    "get_case",
    "get_user",
    "list_events",
)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB()
    for name in _ORCHESTRATOR_WRITES:
        monkeypatch.setattr(f"app.db.writes.orchestrator.{name}", getattr(fake, name))
    for name in _RELAY_WRITES:
        monkeypatch.setattr(f"app.db.writes.relay.{name}", getattr(fake, name))
    for name in _READS:
        monkeypatch.setattr(f"app.db.reads.{name}", getattr(fake, name))
    monkeypatch.setattr("app.orchestrator.pipe.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.outbound.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.ask_user.append_event", fake.append_event)
    return fake


@pytest.fixture
def whatsapp() -> FakeWhatsApp:
    return FakeWhatsApp()


@pytest.fixture
def detected() -> dict[str, str | None]:
    """What the fake detector returns, by message text."""
    return {}


@pytest.fixture
def ask_user(whatsapp: FakeWhatsApp) -> AskUser:
    return AskUser(whatsapp)


@pytest.fixture
def pipe(
    whatsapp: FakeWhatsApp, detected: dict[str, str | None], ask_user: AskUser
) -> InboundPipe:
    async def detect(text: str) -> str | None:
        return detected.get(text)

    return InboundPipe(whatsapp, detect, ask_user, quiet_window_s=QUIET_S)
