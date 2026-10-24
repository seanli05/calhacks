"""The WhatsApp pipe on fakes: an in-memory stand-in for the DB helpers it calls,
a fake Twilio, and a fake language detector."""

import asyncio
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from app.contracts import MessageDirection, MessageSender
from app.db import tables
from app.orchestrator import language
from app.orchestrator.pipe import InboundPipe
from app.relay.inbound import InboundMedia, InboundMessage
from app.relay.media import DownloadedMedia, MediaDownloadError
from app.relay.templates import LANGUAGES, TEMPLATES, render
from app.relay.whatsapp import MAX_BODY_CHARS, split_body
from app.translation.detect import _Detected, detect_language

NUMBER = "+15105550123"
QUIET_S = 0.05


class FakeDB:
    """Just enough of the DB helpers for the pipe, keyed like the real tables."""

    def __init__(self) -> None:
        self.users: dict[str, tables.User] = {}
        self.messages: list[tables.Message] = []
        self.media: list[tables.Media] = []
        self.documents: list[tables.Document] = []
        self.cases: list[tables.Case] = []

    async def get_or_create_user(self, whatsapp_number: str) -> tables.User:
        return self.users.setdefault(
            whatsapp_number, tables.User(whatsapp_number=whatsapp_number)
        )

    async def set_language(self, user_id: str, lang: str) -> tables.User:
        user = next(u for u in self.users.values() if u.id == user_id)
        user.language = lang
        return user

    async def save_media(
        self, user_id: str, content_type: str, data: bytes, url: str | None = None
    ) -> tables.Media:
        row = tables.Media(user_id=user_id, content_type=content_type, data=data)
        self.media.append(row)
        return row

    async def create_document(
        self, user_id: str, media_ids: Sequence[str]
    ) -> tables.Document:
        doc = tables.Document(
            user_id=user_id, pages=[{"media_id": m} for m in media_ids]
        )
        self.documents.append(doc)
        return doc

    async def add_pages(self, document_id: str, media_ids: Sequence[str]) -> None:
        doc = next(d for d in self.documents if d.id == document_id)
        doc.pages = [*doc.pages, *({"media_id": m} for m in media_ids)]

    async def append_message(
        self,
        user_id: str,
        direction: MessageDirection,
        sender: MessageSender,
        body_original: str,
        lang: str,
        **fields: Any,
    ) -> tables.Message:
        fields["media_ids"] = list(fields.get("media_ids", ()))
        row = tables.Message(
            user_id=user_id,
            direction=direction,
            sender=sender,
            body_original=body_original,
            language=lang,
            **fields,
        )
        self.messages.append(row)
        return row

    async def list_messages(self, user_id: str) -> list[tables.Message]:
        return [m for m in self.messages if m.user_id == user_id]

    async def list_active_cases(self, user_id: str) -> list[tables.Case]:
        return [c for c in reversed(self.cases) if c.user_id == user_id]

    def outbound_templates(self) -> list[str | None]:
        return [m.template for m in self.messages if m.direction == "out"]


class FakeWhatsApp:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.broken_urls: set[str] = set()

    async def send(self, to_number: str, body: str) -> list[str]:
        assert to_number == NUMBER
        self.sent.append(body)
        return [f"SM{len(self.sent)}"]

    async def download(self, media: InboundMedia, message_sid: str) -> DownloadedMedia:
        if media.url in self.broken_urls:
            raise MediaDownloadError(f"Media download failed for {message_sid}")
        return DownloadedMedia(content_type=media.content_type, data=b"jpeg")


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB()
    for name in (
        "get_or_create_user",
        "set_language",
        "save_media",
        "create_document",
        "add_pages",
    ):
        monkeypatch.setattr(f"app.db.writes.orchestrator.{name}", getattr(fake, name))
    monkeypatch.setattr("app.db.reads.list_messages", fake.list_messages)
    monkeypatch.setattr("app.db.reads.list_active_cases", fake.list_active_cases)
    monkeypatch.setattr("app.orchestrator.pipe.append_message", fake.append_message)
    monkeypatch.setattr("app.relay.outbound.append_message", fake.append_message)
    return fake


@pytest.fixture
def whatsapp() -> FakeWhatsApp:
    return FakeWhatsApp()


@pytest.fixture
def detected() -> dict[str, str | None]:
    """What the fake detector returns, by message text."""
    return {}


@pytest.fixture
def pipe(whatsapp: FakeWhatsApp, detected: dict[str, str | None]) -> InboundPipe:
    async def detect(text: str) -> str | None:
        return detected.get(text)

    return InboundPipe(whatsapp, detect, quiet_window_s=QUIET_S)


_sid = 0


def inbound(body: str = "", photos: int = 0) -> InboundMessage:
    global _sid
    _sid += 1
    form = {
        "MessageSid": f"SM{_sid}",
        "From": f"whatsapp:{NUMBER}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": str(photos),
    }
    for i in range(photos):
        form[f"MediaUrl{i}"] = f"https://api.twilio.com/media/{_sid}/{i}"
        form[f"MediaContentType{i}"] = "image/jpeg"
    return InboundMessage.from_form(form)


async def wait_for_batches() -> None:
    await asyncio.sleep(QUIET_S * 3)


async def use_spanish(db: FakeDB) -> tables.User:
    user = await db.get_or_create_user(NUMBER)
    user.language = "es"
    return user


# Language pick


async def test_text_first_contact_confirms_detected_language(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp, detected: dict
) -> None:
    detected["hola, recibí una carta"] = "es"

    await pipe.handle(inbound("hola, recibí una carta"))

    assert whatsapp.sent == [render("language.confirm", "es")]
    first_in, confirm = db.messages
    assert (first_in.direction, first_in.language) == ("in", "es")
    assert (confirm.template, confirm.language, confirm.twilio_sid) == (
        "language.confirm",
        "es",
        "SM1",
    )
    assert confirm.body_en == render("language.confirm", "en")

    await pipe.handle(inbound("1"))

    user = db.users[NUMBER]
    assert user.language == "es"
    assert whatsapp.sent[-1] == render("language.set", "es")


async def test_other_language_leads_to_menu_then_pick(
    pipe: InboundPipe, db: FakeDB, whatsapp: FakeWhatsApp, detected: dict
) -> None:
    detected["hello"] = "en"

    await pipe.handle(inbound("hello"))
    await pipe.handle(inbound("2"))
    assert db.outbound_templates()[-1] == "language.menu"
    assert db.users[NUMBER].language is None

    await pipe.handle(inbound("1"))
    assert db.users[NUMBER].language == LANGUAGES[0] == "es"


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


# Pure pieces


@pytest.mark.parametrize(
    ("text", "expected"), [("1", 1), (" 2. ", 2), ("2)", 2), ("3", None), ("uno", None)]
)
def test_parse_choice(text: str, expected: int | None) -> None:
    assert language.parse_choice(text, 2) == expected


def test_every_template_exists_in_every_language() -> None:
    for template_id, texts in TEMPLATES.items():
        assert set(texts) == set(LANGUAGES), template_id


def test_render_without_language_sends_every_language_once() -> None:
    both = render("letter.received", None)
    assert render("letter.received", "es") in both
    assert render("letter.received", "en") in both
    assert render("language.menu", None) == render("language.menu", "es")


def test_menu_lists_languages_in_order() -> None:
    menu = render("language.menu", None)
    assert menu.index("1 Español") < menu.index("2 English")


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
    ("answer", "expected"), [("es", "es"), (" ES ", "es"), (None, None), ("spa", None)]
)
async def test_detect_language_keeps_only_iso_codes(
    answer: str | None, expected: str | None
) -> None:
    client: Any = _FakeAnthropic(answer)
    assert await detect_language(client, "model", "hola") == expected
