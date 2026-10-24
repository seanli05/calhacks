"""Fixtures for the WhatsApp side (pipe and relay), built on whatsapp_fakes."""

import os
from typing import Any

import pytest
from app.orchestrator.call_status import CallStatusWatcher
from app.orchestrator.consent import ConsentGate
from app.orchestrator.conversation import Conversation
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letter_result import LetterResults
from app.orchestrator.letters import Letters
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.verdicts import Verdicts
from app.relay.ask_user import AskUser
from whatsapp_fakes import QUIET_S, FakeDB, FakeTranslator, FakeWhatsApp

# A developer's .env may set the demo dial override (C40); tests that want it set
# it themselves. Env vars win over .env files.
os.environ["DEMO_DIAL_NUMBER"] = ""

_ORCHESTRATOR_WRITES = (
    "get_or_create_user",
    "set_language",
    "save_media",
    "create_document",
    "add_pages",
)
_MEMORY_WRITES = ("add_fact", "set_fact_status", "delete_fact", "upsert_profile")
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
    "official_dial_number",
    "latest_brief",
    "list_calls",
)


@pytest.fixture(autouse=True)
def no_dashboard_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dashboard API translates free text in the background with the real
    translator whenever a key is set; tests must never call it. Tests of the cache
    patch in a fake."""
    from app.api import translations

    monkeypatch.setattr(translations, "get_translator", lambda: None)
    translations.clear()


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB()
    for name in _ORCHESTRATOR_WRITES:
        monkeypatch.setattr(f"app.db.writes.orchestrator.{name}", getattr(fake, name))
    for name in _RELAY_WRITES:
        monkeypatch.setattr(f"app.db.writes.relay.{name}", getattr(fake, name))
    for name in _MEMORY_WRITES:
        monkeypatch.setattr(f"app.db.writes.memory.{name}", getattr(fake, name))
    for name in _READS:
        monkeypatch.setattr(f"app.db.reads.{name}", getattr(fake, name))
    monkeypatch.setattr("app.db.jobs.enqueue", fake.enqueue)
    monkeypatch.setattr("app.orchestrator.pipe.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.outbound.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.ask_user.append_event", fake.append_event)
    monkeypatch.setattr("app.orchestrator.tools.append_event", fake.append_event)
    monkeypatch.setattr("app.orchestrator.consent.append_event", fake.append_event)
    monkeypatch.setattr("app.memory.events.append_event", fake.append_event)
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
def translator() -> FakeTranslator:
    return FakeTranslator()


@pytest.fixture
def call_status(whatsapp: FakeWhatsApp) -> CallStatusWatcher:
    return CallStatusWatcher(whatsapp, poll_interval_s=0.01)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation()


@pytest.fixture
def consent(
    whatsapp: FakeWhatsApp,
    translator: FakeTranslator,
    job_watcher: JobWatcher,
    call_status: CallStatusWatcher,
    conversation: Conversation,
) -> ConsentGate:
    fake: Any = translator
    return ConsentGate(
        whatsapp, fake, job_watcher, call_status, conversation=conversation
    )


@pytest.fixture
def verdicts(
    whatsapp: FakeWhatsApp,
    translator: FakeTranslator,
    consent: ConsentGate,
    conversation: Conversation,
) -> Verdicts:
    fake: Any = translator
    return Verdicts(
        whatsapp, fake, consent, poll_interval_s=0.01, conversation=conversation
    )


@pytest.fixture
def letter_results(
    whatsapp: FakeWhatsApp,
    translator: FakeTranslator,
    verdicts: Verdicts,
    conversation: Conversation,
) -> LetterResults:
    fake: Any = translator
    return LetterResults(whatsapp, fake, verdicts, conversation=conversation)


@pytest.fixture
def letters(
    whatsapp: FakeWhatsApp, job_watcher: JobWatcher, letter_results: LetterResults
) -> Letters:
    return Letters(whatsapp, job_watcher, letter_results)


@pytest.fixture
def pipe(
    whatsapp: FakeWhatsApp,
    detected: dict[str, str | None],
    ask_user: AskUser,
    letters: Letters,
    consent: ConsentGate,
    conversation: Conversation,
) -> InboundPipe:
    async def detect(text: str) -> str | None:
        return detected.get(text)

    return InboundPipe(
        whatsapp,
        detect,
        ask_user,
        letters,
        quiet_window_s=QUIET_S,
        consent=consent,
        conversation=conversation,
    )
