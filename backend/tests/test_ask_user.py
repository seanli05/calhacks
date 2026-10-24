"""ask_user (P1) on fakes: answer, timeout, the race between them, late replies
(C24), re-prompts, cancellation, and routing priority in the pipe."""

import asyncio

import pytest
from app.contracts import (
    AskUserReply,
    AskUserRequest,
    EventType,
    JobType,
    QuestionStatus,
)
from app.db import tables
from app.orchestrator.consent import ConsentGate
from app.orchestrator.pipe import InboundPipe
from app.relay.ask_user import AskUser
from app.relay.templates import render
from whatsapp_fakes import FakeDB, FakeWhatsApp, inbound, use_spanish

OPTIONS = ["Speak to a representative about an appointment", "Case status"]


def request(call: tables.Call, timeout_s: int = 1) -> AskUserRequest:
    return AskUserRequest(
        question_id=f"question_{len(call.id)}_{timeout_s}",
        call_id=call.id,
        template="menu_choice",
        options_en=OPTIONS,
        default_option=1,
        timeout_s=timeout_s,
    )


async def on_call(db: FakeDB) -> tuple[tables.User, tables.Call]:
    user = await use_spanish(db)
    return user, db.add_call(user)


async def start_asking(
    ask_user: AskUser, req: AskUserRequest, db: FakeDB
) -> asyncio.Task[AskUserReply]:
    """Start `ask` as the phone agent would, and return once the question is out."""
    task = asyncio.create_task(ask_user.ask(req))
    for _ in range(100):
        if EventType.CALL_ASK_USER in db.event_types() or task.done():
            break
        await asyncio.sleep(0.01)
    return task


async def test_answer_reaches_the_waiting_agent(
    pipe: InboundPipe, ask_user: AskUser, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    _, call = await on_call(db)
    req = request(call, timeout_s=5)
    task = await start_asking(ask_user, req, db)

    question_out = db.messages[-1]
    assert (question_out.template, question_out.question_id) == (
        "ask_user.menu_choice",
        req.question_id,
    )
    assert "1 Speak to a representative" in whatsapp.sent[-1]
    assert "¿Cuál elijo?" in whatsapp.sent[-1]

    await pipe.handle(inbound("2"))

    assert await task == AskUserReply(question_id=req.question_id, choice=2)
    assert db.questions[req.question_id].status == QuestionStatus.ANSWERED
    assert db.messages[-1].question_id == req.question_id  # the inbound "2"
    assert db.event_types() == [
        EventType.CALL_ASK_USER,
        EventType.CALL_ASK_USER_ANSWERED,
    ]
    assert all(e.call_id == call.id and e.case_id == call.case_id for e in db.events)
    # The dashboard feed reads `choice` (api/feed_templates.py).
    assert db.events[-1].data["choice"] == 2


async def test_timeout_takes_the_default(ask_user: AskUser, db: FakeDB) -> None:
    _, call = await on_call(db)
    req = request(call, timeout_s=1)

    reply = await ask_user.ask(req)

    assert reply.choice == req.default_option
    assert db.questions[req.question_id].status == QuestionStatus.TIMED_OUT
    assert db.event_types()[-1] == EventType.CALL_ASK_USER_TIMEOUT
    # The dashboard feed reads `default_option` (api/feed_templates.py).
    assert db.events[-1].data["default_option"] == req.default_option


async def test_timeout_that_loses_the_race_returns_the_users_choice(
    ask_user: AskUser, db: FakeDB
) -> None:
    """The user's answer commits just before the timeout fires; the agent must get
    the answer, not the default."""
    _, call = await on_call(db)
    req = request(call, timeout_s=1)
    task = await start_asking(ask_user, req, db)

    await db.answer_question(req.question_id, 2)  # the reply handler's write
    await asyncio.sleep(1.1)  # the timeout fires and finds the row closed
    ask_user._waiting[req.question_id].set_result(2)  # the handler's next step

    assert (await task).choice == 2
    assert EventType.CALL_ASK_USER_TIMEOUT not in db.event_types()
    assert db.event_types()[-1] == EventType.CALL_ASK_USER_ANSWERED


async def test_reply_that_loses_the_race_gets_the_late_reply(
    ask_user: AskUser, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    """The pipe read the question as open, but the timeout closed it before the
    answer was written (C24)."""
    user, call = await on_call(db)
    req = request(call)
    stale = await db.create_question(req, user.id)
    await db.time_out_question(req.question_id)

    assert await ask_user.handle_reply(user, stale, "2")

    assert db.questions[req.question_id].late_reply_at is not None
    assert db.questions[req.question_id].choice is None
    assert whatsapp.sent[-1] == render(
        "ask_user.late_reply", "es", default=1, default_option=OPTIONS[0]
    )
    assert db.event_types() == [EventType.CALL_ASK_USER_LATE_REPLY]
    assert db.events[0].data == {
        "question_id": req.question_id,
        "choice": 2,
        "default_option": 1,
    }


async def test_answer_after_timeout_gets_one_late_reply(
    pipe: InboundPipe, ask_user: AskUser, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    _, call = await on_call(db)
    req = request(call, timeout_s=1)
    await ask_user.ask(req)

    await pipe.handle(inbound("2"))
    assert db.messages[-1].template == "ask_user.late_reply"
    assert db.event_types()[-1] == EventType.CALL_ASK_USER_LATE_REPLY

    # Said once: the next number is ordinary text for the orchestrator.
    await pipe.handle(inbound("2"))
    assert db.messages[-1].sender == "orchestrator"


async def test_late_reply_window_expires(db: FakeDB, whatsapp: FakeWhatsApp) -> None:
    ask_user = AskUser(whatsapp, late_reply_window_s=0)
    user, call = await on_call(db)
    await ask_user.ask(request(call, timeout_s=1))

    assert await ask_user.question_for_reply(user.id) is None


async def test_text_while_waiting_is_reprompted(
    pipe: InboundPipe, ask_user: AskUser, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    _, call = await on_call(db)
    req = request(call, timeout_s=5)
    task = await start_asking(ask_user, req, db)

    await pipe.handle(inbound("¿qué significa?"))
    assert whatsapp.sent[-1] == render("ask_user.reprompt", "es", count=2)
    assert db.questions[req.question_id].status == QuestionStatus.OPEN

    await pipe.handle(inbound("1"))
    assert (await task).choice == 1


async def test_ask_user_reply_comes_before_same_or_new(
    pipe: InboundPipe, ask_user: AskUser, db: FakeDB
) -> None:
    """A "1" while both questions are pending answers the call's question: the call
    can't wait, the photo question can."""
    user, call = await on_call(db)
    pipe.photos.hold_for_answer(user.id, "doc_1", ["media_1"])
    req = request(call, timeout_s=5)
    task = await start_asking(ask_user, req, db)

    await pipe.handle(inbound("1"))

    assert (await task).choice == 1
    assert pipe.photos.pending(user.id) is not None


# Cancelling: the phone agent moved on (a new menu prompt, hold, a person)


async def cancel(task: asyncio.Task[AskUserReply]) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelled_ask_closes_the_question_quietly(
    ask_user: AskUser, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user, call = await on_call(db)
    req = request(call, timeout_s=5)
    task = await start_asking(ask_user, req, db)
    sent = len(whatsapp.sent)

    await cancel(task)

    assert db.questions[req.question_id].status == QuestionStatus.TIMED_OUT
    assert await ask_user.question_for_reply(user.id) is None  # no late-reply window
    assert len(whatsapp.sent) == sent
    assert db.event_types() == [EventType.CALL_ASK_USER]


async def test_cancel_propagates_even_if_the_question_cant_be_closed(
    ask_user: AskUser,
    db: FakeDB,
    whatsapp: FakeWhatsApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, call = await on_call(db)
    task = await start_asking(ask_user, request(call, timeout_s=5), db)

    async def broken(question_id: str) -> None:
        raise ConnectionError("database unreachable")

    monkeypatch.setattr("app.db.writes.relay.time_out_question", broken)

    await cancel(task)


async def test_yes_after_a_cancelled_ask_reaches_the_consent_request(
    pipe: InboundPipe, ask_user: AskUser, consent: ConsentGate, db: FakeDB
) -> None:
    """The call failed while the menu question was open; the retry consent YES
    must start a call, not answer the dead question."""
    user, call = await on_call(db)
    req = request(call, timeout_s=5)
    await cancel(await start_asking(ask_user, req, db))
    case = db.add_verified_case(user)
    assert await consent.request(user, case.id) is None

    await pipe.handle(inbound("1"))

    assert db.questions[req.question_id].choice is None
    assert consent.pending(user.id) is None
    [job] = db.jobs_of(JobType.CALL)
    assert job.payload["case_id"] == case.id
    assert EventType.CONSENT_GIVEN in db.event_types()
    assert "ask_user.reprompt" not in db.outbound_templates()


async def test_unsent_question_takes_the_default_at_once(
    ask_user: AskUser, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    _, call = await on_call(db)
    whatsapp.fail_sends = True
    req = request(call, timeout_s=30)

    reply = await asyncio.wait_for(ask_user.ask(req), 2)

    assert reply.choice == req.default_option
    assert db.questions[req.question_id].status == QuestionStatus.TIMED_OUT
    assert db.event_types() == [EventType.CALL_ASK_USER_TIMEOUT]


async def test_unknown_question_kind_fails_before_asking(
    ask_user: AskUser, db: FakeDB
) -> None:
    _, call = await on_call(db)
    req = request(call).model_copy(update={"template": "no_such_kind"})

    with pytest.raises(ValueError, match="no_such_kind"):
        await ask_user.ask(req)
    assert db.questions == {}


# Option labels in the user's language (concern 7)

SPANISH = ["Hablar con un representante sobre una cita", "Estado del caso"]


def translating(
    whatsapp: FakeWhatsApp, labels: list[str] | None = SPANISH, delay_s: float = 0
) -> AskUser:
    async def translate(options_en: list[str], language: str) -> list[str] | None:
        assert (options_en, language) == (OPTIONS, "es")
        await asyncio.sleep(delay_s)
        return labels

    return AskUser(whatsapp, translate_labels=translate, labels_timeout_s=0.2)


async def test_options_go_out_translated_and_are_logged_in_english(
    db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    _, call = await on_call(db)

    await translating(whatsapp).ask(request(call, timeout_s=1))

    question_out = next(m for m in db.messages if m.template == "ask_user.menu_choice")
    assert "1 Hablar con un representante sobre una cita" in question_out.body_original
    assert "Speak to a representative" not in question_out.body_original
    assert question_out.body_en is not None
    assert "1 Speak to a representative about an appointment" in question_out.body_en
    assert db.events[0].data["options_en"] == OPTIONS


@pytest.mark.parametrize(("labels", "delay_s"), [(None, 0), (SPANISH, 1)])
async def test_options_fall_back_to_english_rather_than_wait(
    db: FakeDB, whatsapp: FakeWhatsApp, labels: list[str] | None, delay_s: float
) -> None:
    """A failed or slow translation never holds up the call's question."""
    _, call = await on_call(db)
    ask_user = translating(whatsapp, labels, delay_s)

    task = await start_asking(ask_user, request(call, timeout_s=5), db)

    assert not task.done()
    assert "1 Speak to a representative" in whatsapp.sent[-1]
    task.cancel()


async def test_late_reply_names_the_default_as_the_user_saw_it(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    _, call = await on_call(db)
    ask_user = translating(whatsapp)
    pipe._ask_user = ask_user
    await ask_user.ask(request(call, timeout_s=1))

    await pipe.handle(inbound("2"))

    late = db.messages[-1]
    assert late.template == "ask_user.late_reply"
    assert late.body_original == render(
        "ask_user.late_reply", "es", default=1, default_option=SPANISH[0]
    )
    assert late.body_en == render(
        "ask_user.late_reply", "en", default=1, default_option=OPTIONS[0]
    )
