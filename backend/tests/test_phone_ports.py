"""The phone agent's ports and their fakes: the rules they hold by construction,
and a whole call run on fakes the way the runner (1e) will drive one."""

import asyncio
import inspect
from datetime import UTC, datetime

import pytest
from app.contracts import AskUserRequest, CallJob, EventType
from app.contracts.common import CallState
from app.db.errors import NotFound, UnverifiedNumber
from app.phone.call_events import CallEvents
from app.phone.fakes import (
    Answer,
    ConnectedUser,
    Dialed,
    FakeCallStore,
    FakeClock,
    FakeEventLog,
    FakeNumberSource,
    FakeRelay,
    FakeTelephony,
    HungUp,
    NoAnswer,
    RangUser,
    Said,
    Step,
)
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    Heard,
    LineEvent,
    NonSpeech,
    UserAnswered,
)
from app.phone.ports import LineClosed, Telephony, TranscriptLine

OFFICIAL = "+18005550100"
USER_PHONE = "+15555550123"


def _job(consent_message_id: str = "msg_41") -> CallJob:
    return CallJob(
        case_id="case_123",
        user_id="user_9",
        brief_id="brief_77",
        user_language="es",
        consent_at=datetime(2026, 10, 25, 10, 2, tzinfo=UTC),
        consent_message_id=consent_message_id,
        max_hold_minutes=60,
    )


def _numbers() -> FakeNumberSource:
    return FakeNumberSource(
        verified={"case_123": OFFICIAL}, users={"user_9": USER_PHONE}
    )


def _question(timeout_s: int = 30) -> AskUserRequest:
    return AskUserRequest(
        question_id="question_3",
        call_id="call_5",
        template="menu_choice",
        options_en=["Speak to a representative", "Case status"],
        default_option=1,
        timeout_s=timeout_s,
    )


async def _drain(line: FakeTelephony) -> list[LineEvent]:
    return [event async for event in line.events()]


def test_no_telephony_method_takes_a_phone_number() -> None:
    """Rule 2 by construction: keep it that way."""
    for name, method in inspect.getmembers(Telephony, inspect.isfunction):
        params = set(inspect.signature(method).parameters)
        assert not params & {"number", "phone", "to", "to_number"}, name


async def test_unverified_case_is_never_dialed() -> None:
    clock = FakeClock()
    line = FakeTelephony(FakeNumberSource(), clock)
    with pytest.raises(UnverifiedNumber):
        await line.dial_agency("call_5", "case_123")
    assert line.actions == []


async def test_dials_the_verified_number_and_plays_the_script() -> None:
    clock = FakeClock()
    script = [
        Step(3, AgencyAnswered()),
        Step(2, Heard(text="For appointments, press 2.")),
        Step(60, NonSpeech(sound="music", seconds=60)),
    ]
    line = FakeTelephony(_numbers(), clock, script)
    await line.dial_agency("call_5", "case_123")
    assert line.actions == [Dialed("call_5", "case_123", OFFICIAL)]

    await clock.advance(5)
    await line.hang_up()
    assert await _drain(line) == [step.event for step in script[:2]]


async def test_responder_answers_actions() -> None:
    clock = FakeClock()

    def tree(action: object) -> list[Step]:
        if action == Said("two"):
            return [Step(1, Heard(text="Please hold."))]
        return []

    line = FakeTelephony(_numbers(), clock, responder=tree)
    await line.dial_agency("call_5", "case_123")
    await line.say("two")
    await clock.advance(1)
    await line.hang_up()
    assert await _drain(line) == [Heard(text="Please hold.")]


async def test_nothing_goes_out_after_the_agency_hangs_up() -> None:
    clock = FakeClock()
    line = FakeTelephony(_numbers(), clock, [Step(1, AgencyHungUp())])
    await line.dial_agency("call_5", "case_123")
    await clock.advance(1)
    with pytest.raises(LineClosed):
        await line.say("hello")


async def test_ring_user_reads_the_users_number() -> None:
    clock = FakeClock()
    line = FakeTelephony(_numbers(), clock)
    await line.dial_agency("call_5", "case_123")
    await line.ring_user("call_5", "user_9")
    assert line.actions[-1] == RangUser("call_5", "user_9", USER_PHONE)
    with pytest.raises(NotFound):
        await line.ring_user("call_5", "user_unknown")


async def test_call_store_needs_consent_and_a_known_call() -> None:
    store = FakeCallStore()
    with pytest.raises(ValueError, match="consent"):
        await store.create_call("job_12", _job(consent_message_id=""))
    with pytest.raises(NotFound):
        await store.set_state("call_unknown", CallState.MENU)

    call_id = await store.create_call("job_12", _job())
    line = TranscriptLine(at=datetime.now(UTC), speaker="agency", text="Hello")
    first = await store.save_transcript(call_id, [line])
    second = await store.save_transcript(call_id, [line, line])
    assert first == second
    assert len(store.calls[call_id].transcript) == 2


async def test_relay_answers_times_out_and_records_cancels() -> None:
    clock = FakeClock()
    relay = FakeRelay(clock, [Answer(2, after_s=10), NoAnswer(), Answer(2, 99)])

    assert (await clock.run(relay.ask_user(_question()))).choice == 2
    before = clock.now()
    assert (await clock.run(relay.ask_user(_question()))).choice == 1
    assert (clock.now() - before).total_seconds() == 30
    # An answer after the timeout is a late reply: the default stands.
    assert (await clock.run(relay.ask_user(_question()))).choice == 1

    task = asyncio.create_task(relay.ask_user(_question()))
    await clock.advance(1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert relay.cancelled == ["question_3"]


async def test_call_events_fill_the_envelope() -> None:
    clock = FakeClock()
    log = FakeEventLog()
    events = CallEvents(log, clock, "user_9", "case_123", "job_12")
    await events.for_call("call_5").append(
        EventType.CALL_MENU_CHOICE, "Said 2 (Appointments)", digit="2"
    )
    [event] = log.events
    assert (event.source, event.user_id, event.call_id, event.job_id) == (
        "phone_agent",
        "user_9",
        "call_5",
        "job_12",
    )
    assert event.created_at == clock.now()
    assert event.data == {"digit": "2"}


async def test_a_whole_call_runs_on_fakes() -> None:
    """The shape of the 1e runner: ask_user runs as a task while the line is still
    read, so the menu's reprompt is heard while the user decides."""
    clock = FakeClock()
    store = FakeCallStore()
    relay = FakeRelay(clock, [Answer(1, after_s=12)])

    def tree(action: object) -> list[Step]:
        match action:
            case Said("representative"):
                return [
                    Step(1, NonSpeech(sound="music", seconds=600)),
                    Step(600, Heard(text="This is Maria, how can I help?")),
                ]
            case RangUser():
                return [Step(8, UserAnswered())]
        return []

    script = [
        Step(2, AgencyAnswered()),
        Step(1, Heard(text="Say the reason for your call.")),
        Step(8, Heard(text="Sorry, I didn't get that.")),
    ]
    line = FakeTelephony(_numbers(), clock, script, responder=tree)

    async def run_call() -> list[str]:
        seen: list[str] = []
        call_id = await store.create_call("job_12", _job())
        await line.dial_agency(call_id, "case_123")
        events = aiter(line.events())
        next_event = asyncio.ensure_future(anext(events))
        asking: asyncio.Future | None = None
        while True:
            waiting = {next_event, asking} - {None}
            done, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            if asking in done:
                choice = asking.result().choice
                asking = None
                seen.append(f"chose {choice}")
                await line.say("representative")
            if next_event not in done:
                continue
            try:
                event = next_event.result()
            except StopAsyncIteration:
                return seen
            seen.append(event.kind)
            match event:
                case Heard(text="Say the reason for your call."):
                    asking = asyncio.ensure_future(relay.ask_user(_question()))
                case Heard(text=text) if "Maria" in text:
                    await line.ring_user(call_id, "user_9")
                case UserAnswered():
                    await line.connect_user()
                    await line.hang_up()
            next_event = asyncio.ensure_future(anext(events))

    seen = await clock.run(run_call())
    assert seen == [
        "agency_answered",
        "heard",
        "heard",  # the reprompt, heard while the question was open
        "chose 1",
        "non_speech",
        "heard",
        "user_answered",
    ]
    assert isinstance(line.actions[-1], HungUp)
    assert ConnectedUser() in line.actions
