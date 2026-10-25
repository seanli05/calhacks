"""Asking before saving (C15, Goal 7.5) on fakes: the orchestrator asks about
pending facts at the end of a turn's reply; the memory writer acts on the answer."""

import json
from pathlib import Path
from typing import Any

import pytest
from app.contracts import (
    AskUserRequest,
    DeepResult,
    EventType,
    FactSource,
    FactStatus,
    JobType,
    Sensitivity,
)
from app.db import tables
from app.db.tables import utcnow
from app.orchestrator.consent import ConsentGate
from app.orchestrator.fact_consent import FactConsent
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.verdicts import Verdicts
from app.relay.templates import render
from whatsapp_fakes import (
    FakeDB,
    FakeRunnerClient,
    FakeTranslator,
    FakeWhatsApp,
    inbound,
    use_spanish,
)

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def verified_deep(case_id: str) -> DeepResult:
    """R2 for a verified letter with a call recommended."""
    data = json.loads((FIXTURES / "deep_result.json").read_text(encoding="utf-8"))
    return DeepResult.model_validate({**data, "case_id": case_id})


@pytest.fixture
def turns(runner: FakeRunnerClient) -> list[dict[str, Any]]:
    """One request per turn the model ran."""
    return runner.requests


@pytest.fixture
def memory_pipe(agent_pipe: InboundPipe) -> InboundPipe:
    return agent_pipe


ASKED_EN = render("memory.ask_save", "en", facts="").split("\n")[0]


def save_questions(db: FakeDB) -> list[tables.Message]:
    """Outbound messages that ask "may I save this?" (the end of a turn's reply)."""
    return [
        m for m in db.messages if m.direction == "out" and ASKED_EN in (m.body_en or "")
    ]


async def pending_fact(db: FakeDB, user: tables.User, text: str) -> tables.Fact:
    return await db.add_fact(
        user.id,
        text,
        "immigration",
        FactSource.FROM_DOCUMENT,
        Sensitivity.SENSITIVE,
        FactStatus.PENDING_CONSENT,
        source_ref="doc_1",
    )


async def test_turn_asks_once_and_yes_saves_the_facts(
    db: FakeDB,
    memory_pipe: InboundPipe,
    whatsapp: FakeWhatsApp,
    turns: list[dict[str, Any]],
) -> None:
    user = await use_spanish(db)
    first = await pending_fact(db, user, "Has two children on the asylum application")
    second = await pending_fact(db, user, "Has an asylum interview scheduled")

    await memory_pipe.handle(inbound("¿Qué dice mi carta?"))

    assert len(turns) == 1
    # One message: the reply, then the question (pacing).
    [asked] = [m for m in db.messages if m.direction == "out"]
    assert save_questions(db) == [asked]
    assert asked.body_en is not None and asked.body_en.startswith("Of course.")
    # Translated for the user (rule 6); English in the log.
    assert whatsapp.sent[-1].startswith("[es] Of course.")
    assert "[es] • Has two children on the asylum application" in whatsapp.sent[-1]
    assert "• Has an asylum interview" in asked.body_en

    await memory_pipe.handle(inbound("1"))

    assert len(turns) == 1  # the answer is handled in code, not by the turn
    assert db.outbound_templates()[-1] == "memory.saved"
    assert {f.status for f in db.facts} == {FactStatus.ACTIVE}
    saved = [e for e in db.events if e.type == EventType.MEMORY_FACT_SAVED]
    assert [e.data for e in saved] == [{"fact_id": first.id}, {"fact_id": second.id}]


async def test_no_deletes_the_facts_without_a_user_delete_event(
    db: FakeDB, memory_pipe: InboundPipe
) -> None:
    user = await use_spanish(db)
    await pending_fact(db, user, "Has an asylum interview scheduled")

    await memory_pipe.handle(inbound("hola"))
    await memory_pipe.handle(inbound("no"))

    assert db.facts == []
    assert db.outbound_templates()[-1] == "memory.not_saved"
    assert EventType.FACT_DELETED not in db.event_types()


async def test_other_text_closes_the_question_and_it_is_not_asked_again(
    db: FakeDB,
    memory_pipe: InboundPipe,
    fact_consent: FactConsent,
    turns: list[dict[str, Any]],
) -> None:
    user = await use_spanish(db)
    fact = await pending_fact(db, user, "Has an asylum interview scheduled")

    await memory_pipe.handle(inbound("hola"))
    await memory_pipe.handle(inbound("¿Y la entrevista?"))

    # The turn saw the open question and didn't answer it: it stays open for one
    # more message, then closes.
    assert "save_facts" in turns[1]["messages"][0]["content"]
    assert fact_consent.pending(user.id) is not None
    await memory_pipe.handle(inbound("¿A qué hora es?"))

    assert len(turns) == 3
    assert fact_consent.pending(user.id) is None
    assert len(save_questions(db)) == 1
    assert fact.status == FactStatus.PENDING_CONSENT

    # A fact held later is asked about on the next turn.
    await pending_fact(db, user, "Has a work permit application")
    await memory_pipe.handle(inbound("gracias"))
    assert len(save_questions(db)) == 2
    assert "work permit" in (db.messages[-1].body_en or "")
    assert "asylum interview" not in (db.messages[-1].body_en or "")


async def test_not_asked_while_a_call_question_is_open(
    db: FakeDB, memory_pipe: InboundPipe, turns: list[dict[str, Any]]
) -> None:
    user = await use_spanish(db)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    call = db.add_call(user)
    await db.create_question(
        AskUserRequest(
            question_id="question_1",
            call_id=call.id,
            template="menu_choice",
            options_en=["A", "B"],
            default_option=1,
            timeout_s=45,
        ),
        user.id,
    )
    # A turn that ran while the call's question was open.
    await memory_pipe.handle(inbound("hola"))

    assert len(turns) == 1
    assert save_questions(db) == []


async def test_not_asked_when_the_translation_fails(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    fake: Any = FakeTranslator(fail=True)

    assert await FactConsent(whatsapp, fake).question(user) is None


async def test_a_fact_deleted_meanwhile_is_left_alone(
    db: FakeDB, memory_pipe: InboundPipe, fact_consent: FactConsent
) -> None:
    user = await use_spanish(db)
    kept = await pending_fact(db, user, "Has an asylum interview scheduled")
    gone = await pending_fact(db, user, "Has a work permit application")

    await memory_pipe.handle(inbound("hola"))
    await db.delete_fact(gone.id)  # the user deleted it on the dashboard
    await memory_pipe.handle(inbound("sí"))

    assert [(f.id, f.status) for f in db.facts] == [(kept.id, FactStatus.ACTIVE)]
    saved = [e.data for e in db.events if e.type == EventType.MEMORY_FACT_SAVED]
    assert saved == [{"fact_id": kept.id}]
    assert fact_consent.pending(user.id) is None


# Pacing: the question waits for a quiet moment (conversation.py)


async def test_a_one_for_the_save_question_never_starts_a_call(
    db: FakeDB, memory_pipe: InboundPipe, verdicts: Verdicts, consent: ConsentGate
) -> None:
    """The verdict lands while "may I save this?" is open: the call question
    waits, so the user's "1" saves the facts and starts nothing (rule 4)."""
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    await memory_pipe.handle(inbound("hola"))
    assert len(save_questions(db)) == 1

    await verdicts.react(user, verified_deep(case.id))
    assert db.outbound_templates()[-1] == "verification.verified"
    assert consent.pending(user.id) is None

    await memory_pipe.handle(inbound("1"))

    assert db.outbound_templates()[-2:] == ["memory.saved", "consent.request"]
    assert db.jobs_of(JobType.CALL) == []

    await memory_pipe.handle(inbound("1"))
    assert len(db.jobs_of(JobType.CALL)) == 1


async def test_facts_wait_while_research_is_still_checking_the_letter(
    db: FakeDB,
    memory_pipe: InboundPipe,
    verdicts: Verdicts,
    turns: list[dict[str, Any]],
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    verdicts.watch(user.id, case.id, since=utcnow())  # the deep pass is running

    await memory_pipe.handle(inbound("ya está"))

    assert len(turns) == 1
    assert save_questions(db) == []


async def test_facts_wait_while_a_call_is_running(
    db: FakeDB,
    memory_pipe: InboundPipe,
    consent: ConsentGate,
    turns: list[dict[str, Any]],
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    assert await consent.request(user, case.id) is None
    await memory_pipe.handle(inbound("1"))  # the call starts
    await pending_fact(db, user, "Has an asylum interview scheduled")

    await memory_pipe.handle(inbound("¿cuánto tarda?"))

    assert len(turns) == 1
    assert save_questions(db) == []


async def test_save_answered_in_words_through_the_turn(
    db: FakeDB, memory_pipe: InboundPipe, runner: FakeRunnerClient
) -> None:
    user = await use_spanish(db)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    await memory_pipe.handle(inbound("hola"))
    runner.queue([("answer_save_facts", {"answer": "yes"})], reply=None)

    await memory_pipe.handle(inbound("claro, guárdelo"))

    assert {f.status for f in db.facts} == {FactStatus.ACTIVE}
    # The confirmation was the only message: an empty reply sends nothing more.
    assert db.outbound_templates()[-1] == "memory.saved"


async def test_asking_what_the_question_means_then_answering_in_words_saves(
    db: FakeDB,
    memory_pipe: InboundPipe,
    fact_consent: FactConsent,
    runner: FakeRunnerClient,
) -> None:
    """On a real phone: "what was your question?", the turn explained, and "Sure"
    found the question already closed."""
    user = await use_spanish(db)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    await memory_pipe.handle(inbound("hola"))
    runner.queue([], reply="I asked whether I may remember this. Is that OK?")
    await memory_pipe.handle(inbound("¿cuál era su pregunta?"))
    assert fact_consent.pending(user.id) is not None

    runner.queue([("answer_save_facts", {"answer": "yes"})], reply=None)
    await memory_pipe.handle(inbound("Sure"))

    assert {f.status for f in db.facts} == {FactStatus.ACTIVE}
    assert db.outbound_templates()[-1] == "memory.saved"
