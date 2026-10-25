import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.api import live
from app.api.live_tips import Tips, says
from app.api.models import LiveCallEvent
from app.contracts import CallState, Component, Event, EventType
from app.db import reads, tables
from app.main import app
from fastapi.testclient import TestClient

JOINED = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
QUESTIONS = [
    "Is the interview on November 12 at 8:30 AM still scheduled?",
    "If the interpreter can't come, what should the applicant do before the interview?",
]


def _line(seconds: int, speaker: str, text: str) -> dict[str, Any]:
    return {
        "at": (JOINED + timedelta(seconds=seconds)).isoformat(),
        "speaker": speaker,
        "text": text,
    }


LINES = [
    _line(-60, "agency", "For an asylum interview, press 2."),
    _line(-30, "agent", "The applicant is joining now."),
    _line(2, "agency", "Can you confirm your full name and date of birth?"),
    _line(6, "user", "Ana Morales, March 14, 1988."),
    _line(10, "agency", "Thank you. How can I help you today?"),
    _line(14, "user", "Is my interview on November 12 at 8:30 still scheduled?"),
]


class FakeStreamer:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def stream(
        self, text_en: str, speaker: str, language: str
    ) -> AsyncIterator[str]:
        self.calls += 1
        if self.fail:
            raise TimeoutError
        for word in f"[{language}] {text_en}".split(" "):
            yield word + " "


@pytest.fixture
def call_world(monkeypatch: pytest.MonkeyPatch) -> Iterator[tables.Call]:
    """A bridged call that has ended, served by faked reads (no database)."""
    user = tables.User(whatsapp_number="+15555550100", language="es")
    case = tables.Case(user_id=user.id, document_ids=[])
    brief = tables.CaseBrief(
        case_id=case.id, handoff_note="note", brief={"questions_to_ask": QUESTIONS}
    )
    call = tables.Call(
        case_id=case.id,
        job_id="job_1",
        brief_id=brief.id,
        consent_message_id="msg_1",
        state=CallState.ENDED,
    )
    transcript = tables.Transcript(call_id=call.id, lines=LINES)
    answered = Event(
        event_id="event_1",
        created_at=JOINED - timedelta(seconds=45),
        type=EventType.CALL_HUMAN_DETECTED,
        source=Component.PHONE_AGENT,
        user_id=user.id,
        call_id=call.id,
        summary_en="answered",
    )
    values = {
        "get_call": call,
        "get_case": case,
        "get_brief": brief,
        "get_user": user,
        "get_transcript": transcript,
        "list_events": [answered],
    }
    for name, value in values.items():

        async def fake(*_: Any, _value: Any = value, **__: Any) -> Any:
            return _value

        monkeypatch.setattr(reads, name, fake)
    monkeypatch.setattr(live, "_translated", {})
    monkeypatch.setattr(live, "POLL_S", 0)
    yield call


async def _never() -> bool:
    return False


async def _collect(call: tables.Call, lang: str) -> list[LiveCallEvent]:
    events = live.follow(call.id, "user_1", lang, QUESTIONS, _never)
    return [e async for e in events if e is not None]


async def test_follow_streams_bridged_lines_with_translation_and_tips(
    call_world: tables.Call, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "get_streamer", FakeStreamer)
    events = await _collect(call_world, "es")

    heard = [e for e in events if e.type == "line"]
    # Menu prompts before a person answered are left out; the agent holding the
    # line while the user's phone rings is in.
    assert [e.en for e in heard] == [line["text"] for line in LINES[1:]]
    assert heard[0].speaker == "agent"
    first = heard[1].id
    deltas = "".join(e.text for e in events if e.type == "delta" and e.id == first)
    assert deltas.strip() == f"[es] {LINES[2]['text']}"
    assert [e.type for e in events[:2]] == ["line", "delta"]

    tips = [e.tip for e in events if e.type == "tip"]
    yourself = next(t for t in tips if t.kind == "yourself")
    assert yourself.say_en is None
    assert yourself.line_id == first
    asks = [t for t in tips if t.kind == "ask"]
    # The next question waits for the officer's next line, which never comes.
    assert [t.say_en for t in asks] == QUESTIONS[:1]
    used = [e.id for e in events if e.type == "tip_used"]
    assert yourself.id in used
    assert asks[0].id in used


async def test_follow_is_english_without_a_model(
    call_world: tables.Call, monkeypatch: pytest.MonkeyPatch
) -> None:
    streamer = FakeStreamer()
    monkeypatch.setattr(live, "get_streamer", lambda: streamer)
    events = await _collect(call_world, "en")
    assert streamer.calls == 0
    assert [e.text for e in events if e.type == "delta"] == [
        line["text"] for line in LINES[1:]
    ]


async def test_follow_falls_back_to_the_line_when_translation_fails(
    call_world: tables.Call, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "get_streamer", lambda: FakeStreamer(fail=True))
    events = await _collect(call_world, "es")
    assert [e.text for e in events if e.type == "delta"] == [
        line["text"] for line in LINES[1:]
    ]


async def test_a_replay_reuses_finished_translations(
    call_world: tables.Call, monkeypatch: pytest.MonkeyPatch
) -> None:
    streamer = FakeStreamer()
    monkeypatch.setattr(live, "get_streamer", lambda: streamer)
    first = await _collect(call_world, "es")
    calls = streamer.calls
    second = await _collect(call_world, "es")
    assert streamer.calls == calls
    joined = lambda events: "".join(e.text for e in events if e.type == "delta")
    assert joined(first) == joined(second)


async def test_nothing_is_sent_before_a_person_answers(
    call_world: tables.Call, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_events(*_: Any, **__: Any) -> list[Event]:
        return []

    monkeypatch.setattr(reads, "list_events", no_events)
    assert await _collect(call_world, "en") == []


def test_live_route_sends_server_sent_events(
    call_world: tables.Call, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "get_streamer", lambda: None)
    with TestClient(app).stream(
        "GET", f"/api/calls/{call_world.id}/live?lang=en"
    ) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        # Proxies that compress (Next.js's /api rewrite) would buffer the stream.
        assert "no-transform" in res.headers["cache-control"]
        body = "".join(res.iter_text())
    events = [
        json.loads(chunk.removeprefix("data: "))
        for chunk in body.split("\n\n")
        if chunk.startswith("data: ")
    ]
    assert events[0]["type"] == "line"
    assert events[0]["speaker"] == "agent"
    assert events[-1]["type"] in {"done", "tip"}


def test_live_route_404s_for_an_unknown_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def none(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(reads, "get_call", none)
    assert TestClient(app).get("/api/calls/call_missing/live").status_code == 404


def test_glossary_route(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        tables.GlossaryTerm(
            term="interpreter",
            language="es",
            translation="intérprete",
            trust_level="official",
            source_url="https://www.uscis.gov/es",
        )
    ]
    asked: list[str] = []

    async def get_glossary(language: str) -> list[tables.GlossaryTerm]:
        asked.append(language)
        return rows

    monkeypatch.setattr(reads, "get_glossary", get_glossary)
    body = TestClient(app).get("/api/glossary?lang=es").json()
    assert asked == ["es"]
    assert body == [
        {
            "term": "interpreter",
            "translation": "intérprete",
            "trust_level": "official",
            "source_url": "https://www.uscis.gov/es",
        }
    ]


def test_identity_questions_never_get_an_answer() -> None:
    tips = Tips("call_1", [])
    for question in [
        "What's your A-number?",
        "Can you spell your last name?",
        "What is your current address?",
    ]:
        [tip] = tips.after_agency(question, "line")
        assert tip.kind == "yourself"
        assert tip.say_en is None
        assert tips.after_user("It's on my letter.") == [tip.id]


def test_ask_tips_come_one_at_a_time_in_brief_order() -> None:
    tips = Tips("call_1", QUESTIONS)
    [first] = tips.after_agency("How can I help?", "line0")
    assert first.say_en == QUESTIONS[0]
    assert tips.after_agency("Hello?", "line1") == []
    # Asking the second question first marks it asked but leaves the open tip.
    assert (
        tips.after_user(
            "If my interpreter can't come, what should I do before the interview?"
        )
        == []
    )
    assert tips.after_user(
        "Is my interview on November 12 at 8:30 still scheduled?"
    ) == [first.id]
    assert tips.after_agency("Anything else?", "line2") == []


def test_says_needs_most_of_the_question() -> None:
    assert says("is my interview still scheduled for november 12", QUESTIONS[0])
    assert not says("hello, yes, thank you", QUESTIONS[0])
