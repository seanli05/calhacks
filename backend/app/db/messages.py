"""Append-only WhatsApp message log; written by the orchestrator and the relay (C2)."""

from collections.abc import Sequence

from app.contracts import MessageDirection, MessageSender
from app.contracts.common import CaseId, LanguageCode, MediaId, QuestionId, UserId
from app.db import tables
from app.db.engine import session


async def append_message(
    user_id: UserId,
    direction: MessageDirection,
    sender: MessageSender,
    body_original: str,
    language: LanguageCode,
    *,
    body_en: str | None = None,
    case_id: CaseId | None = None,
    media_ids: Sequence[MediaId] = (),
    template: str | None = None,
    question_id: QuestionId | None = None,
    twilio_sid: str | None = None,
) -> tables.Message:
    message = tables.Message(
        user_id=user_id,
        direction=direction,
        sender=sender,
        body_original=body_original,
        language=language,
        body_en=body_en,
        case_id=case_id,
        media_ids=list(media_ids),
        template=template,
        question_id=question_id,
        twilio_sid=twilio_sid,
    )
    async with session() as db:
        db.add(message)
        await db.commit()
        return message
