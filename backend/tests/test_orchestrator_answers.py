"""Answers in words (agentic routing, C43) on fakes: every message the pipe doesn't
answer in code reaches the turn, which answers open questions through guarded
tools. Rule 4 first: consent in words counts only from the user's latest message."""

import asyncio
import json
from typing import Any

import pytest
from app.contracts import AskUserRequest, EventType, JobType
from app.db import tables
from app.orchestrator import tools as orchestrator_tools
from app.orchestrator.consent import ConsentGate
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.tools import CaseTools
from app.relay.ask_user import AskUser
from whatsapp_fakes import FakeDB, FakeRunnerClient, FakeWhatsApp, inbound, use_spanish


async def asked_to_call(
    db: FakeDB, consent: ConsentGate
) -> tuple[tables.User, tables.Case]:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    assert await consent.request(user, case.id) is None
    return user, case


def context_of(runner: FakeRunnerClient, turn: int = -1) -> str:
    return runner.requests[turn]["messages"][0]["content"]


# Rule 4: consent in words


async def test_yes_in_words_records_consent_and_answers_the_rest(
    db: FakeDB,
    agent_pipe: InboundPipe,
    consent: ConsentGate,
    runner: FakeRunnerClient,
) -> None:
    user, case = await asked_to_call(db, consent)
    runner.queue(
        [
            (
                "answer_call_consent",
                {"case_id": case.id, "answer": "yes", "user_words": "sí, llame"},
            )
        ],
        reply="Yes, bring your children.",
    )

    await agent_pipe.handle(inbound("sí, llame. ¿Llevo a mis hijos?"))

    assert f"call_consent case_id={case.id}" in context_of(runner)
    yes = next(m for m in db.messages if m.direction == "in")
    [job] = db.jobs_of(JobType.CALL)
    assert job.payload["consent_message_id"] == yes.id
    [given] = [e for e in db.events if e.type == EventType.CONSENT_GIVEN]
    assert given.data == {"consent_message_id": yes.id, "via": "words"}
    # Answer and act in one message: the confirmation, then the rest of the reply.
    assert db.outbound_templates()[-2:] == ["consent.given", None]
    assert db.messages[-1].body_en == "Yes, bring your children."
    assert consent.pending(user.id) is None


async def test_consent_in_words_with_no_open_request_is_refused(
    db: FakeDB, agent_pipe: InboundPipe, runner: FakeRunnerClient
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    runner.queue(
        [
            (
                "answer_call_consent",
                {"case_id": case.id, "answer": "yes", "user_words": "llámelos"},
            )
        ],
        reply="Of course.",
    )

    await agent_pipe.handle(inbound("llámelos"))

    assert "error" in json.loads(runner.tool_results[0])
    assert db.jobs_of(JobType.CALL) == []
    assert EventType.CONSENT_GIVEN not in db.event_types()


async def test_words_not_in_the_latest_message_are_refused(
    db: FakeDB,
    agent_pipe: InboundPipe,
    consent: ConsentGate,
    runner: FakeRunnerClient,
) -> None:
    user, case = await asked_to_call(db, consent)
    runner.queue(
        [
            (
                "answer_call_consent",
                {"case_id": case.id, "answer": "yes", "user_words": "sí, llame"},
            )
        ],
        reply="I'd ask whether your interview is still on.",
    )

    await agent_pipe.handle(inbound("¿qué les va a decir?"))

    assert "user_words" in json.loads(runner.tool_results[0])["error"]
    assert db.jobs_of(JobType.CALL) == []
    assert consent.pending(user.id) is not None


async def test_a_yes_from_before_the_request_is_refused(
    db: FakeDB, agent_pipe: InboundPipe, consent: ConsentGate, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    case = db.add_verified_case(user)
    await agent_pipe.handle(inbound("llámelos por favor"))
    assert await consent.request(user, case.id) is None

    result = await CaseTools(user, whatsapp, consent).answer_call_consent(
        case.id, "yes", "llámelos por favor"
    )

    assert "hasn't answered since" in json.loads(result)["error"]
    assert db.jobs_of(JobType.CALL) == []
    assert consent.pending(user.id) is not None


async def test_maybe_makes_no_call(
    db: FakeDB,
    agent_pipe: InboundPipe,
    consent: ConsentGate,
    runner: FakeRunnerClient,
) -> None:
    """A hedge goes to the turn, which answers and asks again; only an answer tool
    could start a call, and the model didn't use one."""
    user, case = await asked_to_call(db, consent)

    await agent_pipe.handle(inbound("tal vez, ¿qué les va a preguntar?"))

    assert len(runner.requests) == 1
    assert f"call_consent case_id={case.id}" in context_of(runner)
    assert db.jobs_of(JobType.CALL) == []
    assert consent.pending(user.id) is not None
    assert "consent.reprompt" not in db.outbound_templates()


async def test_a_bare_one_is_answered_in_code_without_the_model(
    db: FakeDB,
    agent_pipe: InboundPipe,
    consent: ConsentGate,
    runner: FakeRunnerClient,
) -> None:
    await asked_to_call(db, consent)

    await agent_pipe.handle(inbound("1"))

    assert runner.requests == []
    assert len(db.jobs_of(JobType.CALL)) == 1
    [given] = [e for e in db.events if e.type == EventType.CONSENT_GIVEN]
    assert "via" not in given.data


# Routing while the call asks the user something


async def asking(db: FakeDB, ask_user: AskUser, user: tables.User) -> Any:
    """The call's menu question, open and waiting."""
    call = db.add_call(user)
    task = asyncio.create_task(
        ask_user.ask(
            AskUserRequest(
                question_id="question_1",
                call_id=call.id,
                template="menu_choice",
                options_en=["Appointment", "Case status"],
                default_option=2,
                timeout_s=5,
            )
        )
    )
    while EventType.CALL_ASK_USER not in db.event_types():
        await asyncio.sleep(0.01)
    return task, call


async def test_a_question_mid_call_reaches_the_turn_and_words_answer_it(
    db: FakeDB,
    agent_pipe: InboundPipe,
    ask_user: AskUser,
    runner: FakeRunnerClient,
) -> None:
    user = await use_spanish(db)
    task, _ = await asking(db, ask_user, user)

    await agent_pipe.handle(inbound("¿por qué me pregunta esto?"))

    assert 'call_question question_id=question_1: 1 "Appointment"' in context_of(runner)
    assert "ask_user.reprompt" not in db.outbound_templates()
    assert db.messages[-2].body_en == "[en] ¿por qué me pregunta esto?"
    assert not task.done()

    runner.queue(
        [("answer_call_question", {"question_id": "question_1", "choice": 1})],
        reply="Done: I chose your appointment.",
    )
    await agent_pipe.handle(inbound("la primera"))

    assert (await asyncio.wait_for(task, timeout=1)).choice == 1
    assert db.messages[-1].body_en == "Done: I chose your appointment."


async def test_hang_up_during_a_call_question_hangs_up(
    db: FakeDB,
    agent_pipe: InboundPipe,
    ask_user: AskUser,
    runner: FakeRunnerClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hung_up: list[str] = []

    def hang_up(call_id: str) -> str:
        hung_up.append(call_id)
        return "ending"

    monkeypatch.setattr(orchestrator_tools, "request_hang_up", hang_up)
    user = await use_spanish(db)
    task, call = await asking(db, ask_user, user)
    runner.queue([("hang_up_call", {"case_id": call.case_id})], reply="Ending it.")

    await agent_pipe.handle(inbound("cuelgue ya"))

    assert hung_up == [call.id]
    task.cancel()  # the phone agent stops waiting as the call ends
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_bare_two_mid_call_is_answered_in_code(
    db: FakeDB,
    agent_pipe: InboundPipe,
    ask_user: AskUser,
    runner: FakeRunnerClient,
) -> None:
    user = await use_spanish(db)
    task, _ = await asking(db, ask_user, user)

    await agent_pipe.handle(inbound("2"))

    assert (await asyncio.wait_for(task, timeout=1)).choice == 2
    assert runner.requests == []


async def test_an_answer_tool_refuses_a_question_that_isnt_open(
    db: FakeDB, agent_pipe: InboundPipe, runner: FakeRunnerClient
) -> None:
    await use_spanish(db)
    runner.queue(
        [("answer_call_question", {"question_id": "question_1", "choice": 1})],
        reply="Of course.",
    )

    await agent_pipe.handle(inbound("la primera"))

    assert "error" in json.loads(runner.tool_results[0])


# "Same letter or new?" in words


async def test_same_or_new_answered_in_words(
    db: FakeDB, agent_pipe: InboundPipe, runner: FakeRunnerClient
) -> None:
    user = await use_spanish(db)
    letter = await db.create_document(user.id, ["media_old"])
    db.cases.append(tables.Case(user_id=user.id, document_ids=[letter.id]))
    await agent_pipe.handle(inbound(photos=1))
    runner.queue([("answer_same_or_new", {"choice": "same_letter"})], reply=None)

    await agent_pipe.handle(inbound("es otra hoja de la misma carta"))

    assert "same_or_new" in context_of(runner)
    assert db.outbound_templates() == ["letter.same_or_new", "letter.pages_added"]
    assert [p["media_id"] for p in letter.pages] == ["media_old", db.media[0].id]
