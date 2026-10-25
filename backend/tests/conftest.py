"""Fixtures for the WhatsApp side (pipe and relay), built on whatsapp_fakes."""

import os
from typing import Any

import pytest
from app.contracts import CallReport, CaseBrief, FastResult, Verification
from app.db import tables
from app.orchestrator.call_status import CallStatusWatcher
from app.orchestrator.consent import ConsentGate
from app.orchestrator.conversation import Conversation
from app.orchestrator.fact_consent import FactConsent
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letter_result import LetterResults
from app.orchestrator.letters import Letters
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.turn import OrchestratorTurn
from app.orchestrator.verdicts import Verdicts
from app.relay.ask_user import AskUser
from whatsapp_fakes import (
    QUIET_S,
    FakeDB,
    FakeRunnerClient,
    FakeTranslator,
    FakeWhatsApp,
)

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
def conversation(whatsapp: FakeWhatsApp) -> Conversation:
    return Conversation(whatsapp, typing_refresh_s=0.02)


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
    conversation: Conversation,
) -> Verdicts:
    fake: Any = translator
    return Verdicts(whatsapp, fake, poll_interval_s=0.01, conversation=conversation)


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
    whatsapp: FakeWhatsApp,
    job_watcher: JobWatcher,
    letter_results: LetterResults,
    conversation: Conversation,
) -> Letters:
    return Letters(whatsapp, job_watcher, letter_results, conversation=conversation)


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


@pytest.fixture
def fact_consent(whatsapp: FakeWhatsApp, translator: FakeTranslator) -> FactConsent:
    fake: Any = translator
    return FactConsent(whatsapp, fake)


@pytest.fixture
def runner() -> FakeRunnerClient:
    """The fake model behind `agent_pipe`; `runner.queue` scripts its turns."""
    return FakeRunnerClient(reply="Of course.")


@pytest.fixture
def agent_pipe(
    whatsapp: FakeWhatsApp,
    ask_user: AskUser,
    letters: Letters,
    consent: ConsentGate,
    fact_consent: FactConsent,
    runner: FakeRunnerClient,
    conversation: Conversation,
    translator: FakeTranslator,
) -> InboundPipe:
    """The pipe with the real orchestrator turn, on a fake model."""
    client: Any = runner
    fake: Any = translator
    turn = OrchestratorTurn(
        client,
        "model",
        whatsapp,
        fake,
        consent,
        ask_user=ask_user,
        fact_consent=fact_consent,
    )

    async def detect(text: str) -> None:
        return None

    return InboundPipe(
        whatsapp,
        detect,
        ask_user,
        letters,
        quiet_window_s=QUIET_S,
        to_english=translator.to_english,
        turn=turn.run,
        consent=consent,
        fact_consent=fact_consent,
        conversation=conversation,
    )


@pytest.fixture
def research_db(db: FakeDB, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fakes for the research writes (the fake research agent's); returns what was
    written. The verification and brief also land in `db`, so the consent gate
    reads them as it would research's rows."""
    written: dict[str, Any] = {"refs": {}, "verifications": [], "briefs": []}

    async def create_case(case_id: str, user_id: str, docs: list) -> tables.Case:
        case = tables.Case(id=case_id, user_id=user_id, document_ids=list(docs))
        db.cases.append(case)
        return case

    async def put_ref(case_id: str, name: str, value: str) -> None:
        written["refs"][name] = value

    async def save_fast_result(case_id: str, result: FastResult) -> None:
        case = next(c for c in db.cases if c.id == case_id)
        case.fast_result = result.model_dump(mode="json")

    async def save_verification(case_id: str, verification: Verification) -> None:
        written["verifications"].append(verification)
        db.verifications[case_id] = tables.Verification(
            case_id=case_id,
            status=verification.status,
            official_phone=verification.official_phone,
            result=verification.model_dump(mode="json"),
        )

    async def save_brief(
        case_id: str, brief: CaseBrief, note: str | None = None
    ) -> tables.CaseBrief:
        row = tables.CaseBrief(
            id=brief.brief_id,
            case_id=case_id,
            brief=brief.model_dump(mode="json"),
            handoff_note=note or brief.handoff_note,
        )
        written["briefs"].append(row)
        db.briefs[case_id] = row
        return row

    for name, fake in [
        ("create_case", create_case),
        ("put_ref", put_ref),
        ("save_fast_result", save_fast_result),
        ("save_verification", save_verification),
        ("save_brief", save_brief),
    ]:
        monkeypatch.setattr(f"app.db.writes.research.{name}", fake)
    for name in ("claim_next", "finish", "fail"):
        monkeypatch.setattr(f"app.db.jobs.{name}", getattr(db, name))
    monkeypatch.setattr("app.dev.fake_research.append_event", db.append_event)
    return written


@pytest.fixture
def phone_db(db: FakeDB, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fakes for the phone writes (the fake phone worker's); returns what was
    written."""
    written: dict[str, Any] = {"reports": [], "transcripts": []}

    async def create_call(case_id: str, *ids: str) -> tables.Call:
        call = tables.Call(
            case_id=case_id, job_id=ids[0], brief_id=ids[1], consent_message_id=ids[2]
        )
        db.calls[call.id] = call
        return call

    async def set_call_state(call_id: str, state: str) -> None:
        db.calls[call_id].state = state

    async def save_transcript(call_id: str, lines: list) -> tables.Transcript:
        transcript = tables.Transcript(call_id=call_id, lines=lines)
        written["transcripts"].append(transcript)
        return transcript

    async def save_call_report(call_id: str, report: CallReport) -> None:
        written["reports"].append(report)

    for name, fake in [
        ("create_call", create_call),
        ("set_call_state", set_call_state),
        ("save_transcript", save_transcript),
        ("save_call_report", save_call_report),
    ]:
        monkeypatch.setattr(f"app.db.writes.phone.{name}", fake)
    for name in ("claim_next", "finish", "fail"):
        monkeypatch.setattr(f"app.db.jobs.{name}", getattr(db, name))
    monkeypatch.setattr("app.dev.fake_call.append_event", db.append_event)
    return written
