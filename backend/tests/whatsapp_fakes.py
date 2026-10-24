"""Fakes for the WhatsApp side: an in-memory stand-in for the DB helpers the pipe
and the relay call, a fake Twilio, and inbound-message builders. Fixtures that
install them are in conftest.py."""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.contracts import (
    AskUserRequest,
    Event,
    MessageDirection,
    MessageSender,
    QuestionStatus,
)
from app.db import tables
from app.db.tables import utcnow
from app.relay.inbound import InboundMedia, InboundMessage
from app.relay.media import DownloadedMedia, MediaDownloadError
from app.relay.whatsapp import WhatsAppSendError

NUMBER = "+15105550123"
QUIET_S = 0.05


class FakeDB:
    """Just enough of the DB helpers for the pipe and the relay, keyed like the real
    tables. Question reads return copies, as a real read would, so a test can hold
    a stale "open" row while the stored one changes."""

    def __init__(self) -> None:
        self.users: dict[str, tables.User] = {}
        self.messages: list[tables.Message] = []
        self.media: list[tables.Media] = []
        self.documents: list[tables.Document] = []
        self.cases: list[tables.Case] = []
        self.calls: dict[str, tables.Call] = {}
        self.questions: dict[str, tables.Question] = {}
        self.events: list[Event] = []

    # Relay: questions (race-safe like the real helpers: only an open row closes)

    async def create_question(
        self, request: AskUserRequest, user_id: str
    ) -> tables.Question:
        question = tables.Question(
            id=request.question_id,
            call_id=request.call_id,
            user_id=user_id,
            template=request.template,
            options_en=request.options_en,
            default_option=request.default_option,
            timeout_s=request.timeout_s,
        )
        self.questions[question.id] = question
        return _copy(question)

    async def _close_if_open(
        self, question_id: str, **values: Any
    ) -> tables.Question | None:
        question = self.questions[question_id]
        if question.status != QuestionStatus.OPEN:
            return None
        for key, value in values.items():
            setattr(question, key, value)
        return _copy(question)

    async def answer_question(
        self, question_id: str, choice: int
    ) -> tables.Question | None:
        return await self._close_if_open(
            question_id, status=QuestionStatus.ANSWERED, choice=choice
        )

    async def time_out_question(self, question_id: str) -> tables.Question | None:
        return await self._close_if_open(question_id, status=QuestionStatus.TIMED_OUT)

    async def record_late_reply(self, question_id: str) -> tables.Question:
        self.questions[question_id].late_reply_at = utcnow()
        return _copy(self.questions[question_id])

    async def get_open_question(self, user_id: str) -> tables.Question | None:
        open_questions = [
            q
            for q in self.questions.values()
            if q.user_id == user_id and q.status == QuestionStatus.OPEN
        ]
        return _copy(open_questions[-1]) if open_questions else None

    async def get_call(self, call_id: str) -> tables.Call | None:
        return self.calls.get(call_id)

    async def get_case(self, case_id: str) -> tables.Case | None:
        return next((c for c in self.cases if c.id == case_id), None)

    async def get_user(self, user_id: str) -> tables.User | None:
        return next((u for u in self.users.values() if u.id == user_id), None)

    async def append_event(self, event: Event) -> Event:
        self.events.append(event)
        return event

    async def list_events(
        self, user_id: str, since: datetime | None = None
    ) -> list[Event]:
        return [
            e
            for e in self.events
            if e.user_id == user_id and (since is None or e.created_at > since)
        ]

    def event_types(self) -> list[str]:
        return [e.type for e in self.events]

    def add_call(self, user: tables.User) -> tables.Call:
        """A case and a call in progress for `user`, as the phone agent would have."""
        case = tables.Case(user_id=user.id)
        self.cases.append(case)
        call = tables.Call(
            case_id=case.id,
            job_id="job_1",
            brief_id="brief_1",
            consent_message_id="msg_1",
        )
        self.calls[call.id] = call
        return call

    # Orchestrator: users, media, letters

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
        self.fail_sends = False

    async def send(self, to_number: str, body: str) -> list[str]:
        assert to_number == NUMBER
        if self.fail_sends:
            raise WhatsAppSendError("Twilio send failed after 0 parts: error 63016")
        self.sent.append(body)
        return [f"SM{len(self.sent)}"]

    async def download(self, media: InboundMedia, message_sid: str) -> DownloadedMedia:
        if media.url in self.broken_urls:
            raise MediaDownloadError(f"Media download failed for {message_sid}")
        return DownloadedMedia(content_type=media.content_type, data=b"jpeg")


def _copy(question: tables.Question) -> tables.Question:
    return tables.Question(**question.model_dump())


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
