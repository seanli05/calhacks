"""Fixtures for the WhatsApp side (pipe and relay), built on whatsapp_fakes."""

import pytest
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letters import Letters
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
    "get_job",
    "case_progress",
    "latest_verification",
    "get_profile",
    "list_facts",
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
    monkeypatch.setattr("app.db.jobs.enqueue", fake.enqueue)
    monkeypatch.setattr("app.orchestrator.pipe.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.outbound.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.ask_user.append_event", fake.append_event)
    monkeypatch.setattr("app.orchestrator.tools.append_event", fake.append_event)
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
def job_watcher() -> JobWatcher:
    return JobWatcher(poll_interval_s=0.01)


@pytest.fixture
def letters(whatsapp: FakeWhatsApp, job_watcher: JobWatcher) -> Letters:
    return Letters(whatsapp, job_watcher)


@pytest.fixture
def pipe(
    whatsapp: FakeWhatsApp,
    detected: dict[str, str | None],
    ask_user: AskUser,
    letters: Letters,
) -> InboundPipe:
    async def detect(text: str) -> str | None:
        return detected.get(text)

    return InboundPipe(whatsapp, detect, ask_user, letters, quiet_window_s=QUIET_S)
