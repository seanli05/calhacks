"""Asking before saving (C15, Goal 7.5) on fakes: the orchestrator asks about
pending facts after a turn; the memory writer acts on the answer."""

from typing import Any

import pytest
from app.contracts import (
    AskUserRequest,
    EventType,
    FactSource,
    FactStatus,
    Sensitivity,
)
from app.db import tables
from app.orchestrator.consent import ConsentGate
from app.orchestrator.fact_consent import FactConsent
from app.orchestrator.pipe import InboundPipe
from app.relay.ask_user import AskUser
from whatsapp_fakes import FakeDB, FakeTranslator, FakeWhatsApp, inbound, use_spanish


@pytest.fixture
def fact_consent(whatsapp: FakeWhatsApp, translator: FakeTranslator) -> FactConsent:
    fake: Any = translator
    return FactConsent(whatsapp, fake)


@pytest.fixture
def turns() -> list[str]:
    return []


@pytest.fixture
def memory_pipe(
    whatsapp: FakeWhatsApp,
    ask_user: AskUser,
    letters: Any,
    consent: ConsentGate,
    fact_consent: FactConsent,
    turns: list[str],
) -> InboundPipe:
    async def turn(user: tables.User, message_id: str, **_: bool) -> None:
        turns.append(message_id)

    async def detect(text: str) -> None:
        return None

    return InboundPipe(
        whatsapp,
        detect,
        ask_user,
        letters,
        quiet_window_s=0.05,
        to_english=FakeTranslator().to_english,
        turn=turn,
        consent=consent,
        fact_consent=fact_consent,
    )


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
    turns: list[str],
) -> None:
    user = await use_spanish(db)
    first = await pending_fact(db, user, "Has two children on the asylum application")
    second = await pending_fact(db, user, "Has an asylum interview scheduled")

    await memory_pipe.handle(inbound("¿Qué dice mi carta?"))

    assert len(turns) == 1
    assert db.outbound_templates() == ["memory.ask_save"]
    asked = db.messages[-1]
    # Translated for the user (rule 6); English in the log.
    assert "[es] • Has two children on the asylum application" in whatsapp.sent[-1]
    assert asked.body_en is not None and "• Has an asylum interview" in asked.body_en

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
    db: FakeDB, memory_pipe: InboundPipe, turns: list[str]
) -> None:
    user = await use_spanish(db)
    fact = await pending_fact(db, user, "Has an asylum interview scheduled")

    await memory_pipe.handle(inbound("hola"))
    await memory_pipe.handle(inbound("¿Y la entrevista?"))

    assert len(turns) == 2
    assert db.outbound_templates() == ["memory.ask_save"]
    assert fact.status == FactStatus.PENDING_CONSENT

    # A fact held later is asked about on the next turn.
    await pending_fact(db, user, "Has a work permit application")
    await memory_pipe.handle(inbound("gracias"))
    assert db.outbound_templates() == ["memory.ask_save", "memory.ask_save"]
    assert "work permit" in (db.messages[-1].body_en or "")
    assert "asylum interview" not in (db.messages[-1].body_en or "")


async def test_not_asked_while_a_call_question_is_open(
    db: FakeDB, memory_pipe: InboundPipe, turns: list[str]
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
    # A turn that ran while the call's question was open (the pipe routes the
    # reply itself to ask_user).
    await memory_pipe._orchestrator_turn(user, inbound("hola"), "msg_1")

    assert turns == ["msg_1"]
    assert "memory.ask_save" not in db.outbound_templates()


async def test_not_asked_when_the_translation_fails(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    await pending_fact(db, user, "Has an asylum interview scheduled")
    fake: Any = FakeTranslator(fail=True)

    asked = await FactConsent(whatsapp, fake).ask(user)

    assert asked is False
    assert whatsapp.sent == []


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
