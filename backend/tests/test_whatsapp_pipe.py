"""The WhatsApp pipe on fakes (see whatsapp_fakes.py and conftest.py)."""

import asyncio
import re
import string
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from app.contracts import (
    CallOutcome,
    FactSource,
    FactStatus,
    JobType,
    MessageDirection,
    MessageSender,
    Sensitivity,
)
from app.db import tables
from app.dev import fake_call, fake_research
from app.dev.fake_phone import FakePhone
from app.dev.fake_research import FakeResearch
from app.orchestrator.consent import ConsentGate
from app.orchestrator.conversation import Conversation
from app.orchestrator.fact_consent import FactConsent
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letters import Letters
from app.orchestrator.pipe import InboundPipe
from app.orchestrator.turn import OrchestratorTurn
from app.relay.ask_user import AskUser
from app.relay.replies import parse_choice, parse_yes_no
from app.relay.templates import LANGUAGES, TEMPLATES, render
from app.relay.whatsapp import MAX_BODY_CHARS, split_body
from app.translation.detect import _Detected, detect_language
from whatsapp_fakes import (
    NUMBER,
    QUIET_S,
    FakeDB,
    FakeRunnerClient,
    FakeTranslator,
    FakeWhatsApp,
    inbound,
    use_spanish,
    wait_for_batches,
)

# Language pick


@pytest.fixture
def runner() -> FakeRunnerClient:
    return FakeRunnerClient(reply="A language is how we write to each other.")


@pytest.fixture
def talking_pipe(
    whatsapp: FakeWhatsApp,
    ask_user: AskUser,
    letters: Letters,
    consent: ConsentGate,
    conversation: Conversation,
    translator: FakeTranslator,
    detected: dict[str, str | None],
    runner: FakeRunnerClient,
) -> InboundPipe:
    """Detection and the real turn on a fake model: a first message gets answered."""
    fake: Any = translator
    client: Any = runner
    turn = OrchestratorTurn(client, "model", whatsapp, fake, consent)

    async def detect(text: str) -> str | None:
        return detected.get(text)

    return InboundPipe(
        whatsapp,
        detect,
        ask_user,
        letters,
        quiet_window_s=QUIET_S,
        to_english=translator.to_english,
        turn=turn.run,
        consent=consent,
        conversation=conversation,
    )


async def test_clear_first_message_sets_the_language_and_is_answered(
    talking_pipe: InboundPipe,
    db: FakeDB,
    detected: dict,
    runner: FakeRunnerClient,
) -> None:
    """C45: on a real phone, "What is a language" got the 1/2 confirm again; now it
    gets an answer, which mentions the language in passing."""
    detected["¿qué es un idioma?"] = "es"

    await talking_pipe.handle(inbound("¿qué es un idioma?"))

    assert db.users[NUMBER].language == "es"
    assert db.outbound_templates() == [None]
    reply = db.messages[-1]
    assert (reply.sender, reply.language) == ("orchestrator", "es")
    context = runner.requests[0]["messages"][0]["content"]
    assert "<language_note>" in context and "read it as Spanish" in context


async def test_a_guessed_language_is_noted_only_on_the_first_turn(
    talking_pipe: InboundPipe, db: FakeDB, detected: dict, runner: FakeRunnerClient
) -> None:
    detected["hola, recibí una carta"] = "es"
    await talking_pipe.handle(inbound("hola, recibí una carta"))

    await talking_pipe.handle(inbound("¿y qué hago ahora?"))

    assert "<language_note>" not in runner.requests[1]["messages"][0]["content"]


async def test_dari_first_message_is_answered_in_dari(
    talking_pipe: InboundPipe, db: FakeDB, detected: dict
) -> None:
    detected["سلام، یک نامه گرفتم"] = "fa"

    await talking_pipe.handle(inbound("سلام، یک نامه گرفتم"))

    assert db.users[NUMBER].language == "fa"
    assert db.messages[-1].language == "fa"
    assert "language.confirm" not in db.outbound_templates()


async def test_without_a_turn_a_guessed_language_is_confirmed_by_template(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp, detected: dict
) -> None:
    detected["hola, recibí una carta"] = "es"

    await pipe.handle(inbound("hola, recibí una carta"))

    assert db.users[NUMBER].language == "es"
    assert whatsapp.sent == [render("language.set", "es")]


async def test_dari_is_the_third_choice_on_the_menu(
    pipe: InboundPipe, db: FakeDB
) -> None:
    await pipe.handle(inbound("ok"))
    await pipe.handle(inbound("۳"))

    assert db.users[NUMBER].language == "fa"


@pytest.mark.parametrize(
    ("reply", "language"),
    [
        ("español", "es"),
        ("English please", "en"),
        ("دری", "fa"),
        ("2", "en"),
        ("en español por favor", "es"),
    ],
)
async def test_the_menu_takes_a_language_by_name_or_number(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp, reply: str, language: str
) -> None:
    await pipe.handle(inbound("ok"))

    await pipe.handle(inbound(reply))

    assert db.users[NUMBER].language == language
    assert whatsapp.sent[-1] == render("language.set", language)


async def test_a_clear_sentence_answers_the_menu_too(
    talking_pipe: InboundPipe, db: FakeDB, detected: dict, runner: FakeRunnerClient
) -> None:
    detected["what is this letter about?"] = "en"
    await talking_pipe.handle(inbound("ok"))

    await talking_pipe.handle(inbound("what is this letter about?"))

    assert db.users[NUMBER].language == "en"
    assert db.outbound_templates() == ["language.menu", None]
    assert len(runner.requests) == 1


async def test_an_unsupported_language_gets_the_menu(
    pipe: InboundPipe, db: FakeDB, detected: dict
) -> None:
    detected["bonjour, j'ai reçu une lettre"] = "fr"

    await pipe.handle(inbound("bonjour, j'ai reçu une lettre"))

    assert db.outbound_templates() == ["language.menu"]
    assert db.users[NUMBER].language is None


async def test_undetectable_text_gets_the_menu(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    await pipe.handle(inbound("ok"))

    assert db.outbound_templates() == ["language.menu"]
    assert db.messages[0].language == "en"


async def test_photo_first_contact_holds_the_letter_until_language_is_picked(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    await pipe.handle(inbound(photos=1))
    await pipe.handle(inbound(photos=1))
    await wait_for_batches()

    # One menu for both photos, and no letter yet: research waits for the language.
    assert db.outbound_templates() == ["language.menu"]
    assert db.documents == []

    await pipe.handle(inbound("1"))
    assert db.outbound_templates()[-1] == "language.set_letter"
    await wait_for_batches()

    [document] = db.documents
    assert [p["media_id"] for p in document.pages] == [m.id for m in db.media]


async def test_photo_with_a_clear_caption_needs_no_language_question(
    talking_pipe: InboundPipe, db: FakeDB, detected: dict, runner: FakeRunnerClient
) -> None:
    detected["me llegó esta carta"] = "es"
    message = inbound("me llegó esta carta", photos=1)

    await talking_pipe.handle(message)
    await wait_for_batches()

    assert db.users[NUMBER].language == "es"
    assert db.outbound_templates() == ["language.set_letter"]
    assert len(db.documents) == 1
    assert runner.requests == []  # the explanation answers it


# Photos once the language is known


async def test_burst_of_photos_becomes_one_letter(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    await use_spanish(db)

    for _ in range(3):
        await pipe.handle(inbound(photos=1))
    assert db.outbound_templates() == ["letter.received"]
    await wait_for_batches()

    [document] = db.documents
    assert len(document.pages) == 3
    inbound_rows = [m for m in db.messages if m.direction == "in"]
    assert [m.media_ids for m in inbound_rows] == [[m.id] for m in db.media]


async def test_photo_after_research_started_asks_same_or_new(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    letter = await db.create_document(user.id, ["media_old"])
    db.cases.append(tables.Case(user_id=user.id, document_ids=[letter.id]))

    await pipe.handle(inbound(photos=1))
    assert db.outbound_templates() == ["letter.same_or_new"]

    await pipe.handle(inbound("tal vez"))
    assert db.outbound_templates()[-1] == "letter.same_or_new"

    await pipe.handle(inbound("1"))
    assert db.outbound_templates()[-1] == "letter.pages_added"
    assert [p["media_id"] for p in letter.pages] == ["media_old", db.media[0].id]
    await wait_for_batches()
    assert len(db.documents) == 1


async def test_new_letter_answer_starts_a_new_batch(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    user = await use_spanish(db)
    letter = await db.create_document(user.id, ["media_old"])
    db.cases.append(tables.Case(user_id=user.id, document_ids=[letter.id]))

    await pipe.handle(inbound(photos=1))
    await pipe.handle(inbound("2"))
    await wait_for_batches()

    assert db.outbound_templates() == ["letter.same_or_new", "letter.received"]
    assert len(db.documents) == 2
    new = db.documents[-1]
    assert [p["media_id"] for p in new.pages] == [db.media[0].id]


async def test_failed_download_asks_to_resend(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    await use_spanish(db)
    message = inbound(photos=1)
    whatsapp.broken_urls.add(message.media[0].url)

    await pipe.handle(message)
    await wait_for_batches()

    assert db.outbound_templates() == ["media.download_failed"]
    assert db.documents == []


async def test_text_after_language_goes_to_the_orchestrator(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp
) -> None:
    await use_spanish(db)

    await pipe.handle(inbound("¿qué dice mi carta?"))

    reply = db.messages[-1]
    assert (reply.sender, reply.template) == ("orchestrator", None)


# Pacing over the whole demo path (agentic-routing plan, step 0)

# Test seconds per real second: the fakes keep their real pacing (research 5 s and
# 10 s, call steps 3 s), squeezed 50 times.
SCALE = 0.02
# Two messages closer than this, with nothing from the user between, read as a burst.
BURST_S = 5.0
# Messages that must go out at once, whatever was just sent (C36, P1).
URGENT = {"call.human_detected", "ask_user.menu_choice"}
# What the user takes to read a question and answer it.
USER_READS_S = 3.0


async def _until(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("condition never became true")
        await asyncio.sleep(0.005)


def _label(message: tables.Message) -> str:
    if message.template:
        return message.template
    return f"text: {(message.body_en or '')[:40]!r}"


def bursts(messages: list[tables.Message]) -> list[tuple[str, str, float]]:
    """Back-to-back outbound pairs under BURST_S (in real seconds), with no inbound
    message between them."""
    found = []
    previous: tables.Message | None = None
    for message in messages:
        if message.direction == "in":
            previous = None
            continue
        if previous is not None:
            gap_s = (message.created_at - previous.created_at).total_seconds() / SCALE
            if gap_s < BURST_S:
                found.append((_label(previous), _label(message), round(gap_s, 1)))
        previous = message
    return found


async def _demo_path(
    db: FakeDB,
    pipe: InboundPipe,
    ask_user: AskUser,
    job_watcher: JobWatcher,
    consent: ConsentGate,
    *,
    question_after: bool = False,
) -> None:
    """Letter → explanation → verdict → the user needs a call → consent → YES →
    the fake call → summary; with `question_after`, the user then asks something."""
    user = await use_spanish(db)
    research = FakeResearch(
        "+15005550006",
        fake_research.Pacing(fast_s=5 * SCALE, deep_s=10 * SCALE, poll_s=0.01),
    )
    research.start(run_for_s=5)
    phone = FakePhone(
        ask_user,
        fake_call.Pacing(step_s=3 * SCALE, on_hold_count=3, ask_timeout_s=45),
        poll_s=0.01,
    )
    phone.start(5)

    await pipe.handle(inbound(photos=1))
    await _until(lambda: "verification.verified" in db.outbound_templates())
    await asyncio.sleep(USER_READS_S * SCALE)
    # The user says they can't make the date; the turn's request_consent asks.
    await db.append_message(
        user.id,
        MessageDirection.IN,
        MessageSender.USER,
        "No puedo ir ese día",
        "es",
        body_en="I can't go that day",
    )
    [case] = db.cases
    assert await consent.request(user, case.id) is None
    await asyncio.sleep(USER_READS_S * SCALE)
    await pipe.handle(inbound("1"))
    await _until(lambda: "ask_user.menu_choice" in db.outbound_templates())
    await asyncio.sleep(USER_READS_S * SCALE)
    await pipe.handle(inbound("2"))
    [call_job] = db.jobs_of(JobType.CALL)
    await _until(lambda: not job_watcher.is_watching(call_job.id))
    await asyncio.sleep(10 * SCALE)  # anything that follows the summary
    if question_after:
        # The memory writer held a fact from earlier messages.
        await db.add_fact(
            user.id,
            "Has two children",
            "household",
            FactSource.USER_SAID,
            Sensitivity.NORMAL,
            FactStatus.PENDING_CONSENT,
        )
        await pipe.handle(inbound("¿tengo que llevar a mis hijos?"))
        await asyncio.sleep(10 * SCALE)


@pytest.fixture(params=["as_reported", "resolved_no_followup", "failed"])
def call_outcome(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    db: FakeDB,
    phone_db: Any,
) -> str:
    """The fake phone's report, rewritten to the outcome under test."""
    edits = {
        "as_reported": {},
        "resolved_no_followup": {
            "outcome": CallOutcome.RESOLVED,
            "followup_needed": False,
        },
        "failed": {"outcome": CallOutcome.FAILED},
    }[request.param]

    async def finish(job_id: str, result: Any) -> None:
        db.finish_job(job_id, result.model_copy(update=edits))

    monkeypatch.setattr("app.db.jobs.finish", finish)
    return request.param


@pytest.fixture
def chatty_pipe(
    whatsapp: FakeWhatsApp,
    ask_user: AskUser,
    letters: Letters,
    consent: ConsentGate,
    conversation: Conversation,
    translator: FakeTranslator,
) -> InboundPipe:
    """A pipe with the real turn on a fake model that answers every message."""
    fake: Any = translator
    client: Any = FakeRunnerClient(reply="Yes, bring your children.")
    fact_consent = FactConsent(whatsapp, fake)
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


async def test_demo_path_sends_no_bursts(
    db: FakeDB,
    pipe: InboundPipe,
    ask_user: AskUser,
    job_watcher: JobWatcher,
    consent: ConsentGate,
    research_db: Any,
    call_outcome: str,
) -> None:
    await _demo_path(db, pipe, ask_user, job_watcher, consent)

    found = [pair for pair in bursts(db.messages) if pair[1] not in URGENT]
    assert found == []


async def test_a_question_after_the_call_sends_no_bursts(
    db: FakeDB,
    chatty_pipe: InboundPipe,
    ask_user: AskUser,
    job_watcher: JobWatcher,
    consent: ConsentGate,
    research_db: Any,
    phone_db: Any,
) -> None:
    await _demo_path(
        db, chatty_pipe, ask_user, job_watcher, consent, question_after=True
    )

    # The reply and "may I save this?" went out as one message.
    assert "May I remember this" in (db.messages[-1].body_en or "")
    found = [pair for pair in bursts(db.messages) if pair[1] not in URGENT]
    assert found == []


# Pure pieces


@pytest.mark.parametrize(
    ("text", "expected"), [("1", 1), (" 2. ", 2), ("2)", 2), ("3", None), ("uno", None)]
)
def test_parse_choice(text: str, expected: int | None) -> None:
    assert parse_choice(text, 2) == expected


@pytest.mark.parametrize(
    ("text", "expected"), [("۱", 1), (" ۲. ", 2), ("٢", 2), ("۳", None), ("۱۲", None)]
)
def test_parse_choice_reads_persian_digits(text: str, expected: int | None) -> None:
    assert parse_choice(text, 2) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("بلی", 1),
        ("بلي!", 1),  # Arabic yeh, as some keyboards type it
        ("بله", 1),
        ("آره؟", 1),
        ("نخیر", 2),
        ("نه", 2),
        ("نی", 2),
        ("۱", 1),
        ("۲", 2),
        ("sí", 1),
        ("بلی، لطفاً زنگ بزنید", None),  # a sentence goes to the turn
        ("ها", None),
    ],
)
def test_parse_yes_no_reads_dari(text: str, expected: int | None) -> None:
    assert parse_yes_no(text) == expected


def test_every_template_exists_in_every_language() -> None:
    for template_id, texts in TEMPLATES.items():
        assert set(texts) == set(LANGUAGES), template_id


def test_every_translation_has_the_english_placeholders() -> None:
    """A dropped {date} would lose the fact; an extra one would fail to render."""
    for template_id, texts in TEMPLATES.items():
        expected = _placeholders(texts["en"])
        for language, text in texts.items():
            assert _placeholders(text) == expected, (template_id, language)


def test_dari_templates_isolate_their_latin_fragments() -> None:
    """Without isolates a phone lays "I-797C" out as "797C-I", and a line that starts
    with "USCIS" runs left to right."""
    text = render("research_question.legal_advice", "fa")
    assert "\u2068DOJ\u2069" in text
    assert "\u2068USCIS\u2069" in render("call.dialing", "fa")
    assert "\u2068" not in render("call.dialing", "es")
    assert render("ask_user.reprompt", "fa", count=3).count("۳") == 1


def test_dari_templates_use_persian_digits_and_afghan_words() -> None:
    for template_id, texts in TEMPLATES.items():
        if template_id == "language.menu":
            continue  # shared by every language
        dari = texts["fa"]
        assert not re.search(r"[0-9]", dari), template_id
        for iranian in ("بله", "ممنون", "مرسی", "الان", "اطلاعات", "پرونده", "تلفن"):
            assert iranian not in dari, (template_id, iranian)


def test_render_without_language_sends_every_language_once() -> None:
    both = render("letter.received", None)
    assert render("letter.received", "es") in both
    assert render("letter.received", "en") in both
    assert render("language.menu", None) == render("language.menu", "es")


def test_menu_lists_languages_in_order_without_numbers() -> None:
    options = render("language.menu", None).splitlines()[-1]
    assert options.index("Español") < options.index("English") < options.index("دری")
    assert not re.search(r"[0-9۰-۹]", render("language.menu", None))


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_long_body_is_split_under_the_limit() -> None:
    paragraph = "palabra " * 150
    body = "\n\n".join([paragraph] * 4)

    parts = split_body(body)

    assert len(parts) > 1
    assert all(len(part) <= MAX_BODY_CHARS for part in parts)
    assert " ".join(parts).split() == body.split()


def test_unbroken_body_is_hard_split() -> None:
    parts = split_body("x" * (MAX_BODY_CHARS * 2 + 5))
    assert [len(p) for p in parts] == [MAX_BODY_CHARS, MAX_BODY_CHARS, 5]


class _FakeAnthropic:
    def __init__(self, language: str | None) -> None:
        self.messages = self
        self._language = language

    async def parse(self, **request: Any) -> SimpleNamespace:
        return SimpleNamespace(parsed_output=_Detected(language=self._language))


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("es", "es"),
        (" ES ", "es"),
        (None, None),
        ("spa", None),
        ("fa", "fa"),
        ("prs", "fa"),  # Dari's own ISO 639-3 code
    ],
)
async def test_detect_language_keeps_only_iso_codes(
    answer: str | None, expected: str | None
) -> None:
    client: Any = _FakeAnthropic(answer)
    assert await detect_language(client, "model", "hola") == expected
