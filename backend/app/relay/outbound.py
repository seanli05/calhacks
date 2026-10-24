"""Send a WhatsApp message and log it to `messages` (C2). A message is logged only
once Twilio accepts it; a long message split into parts is one row, with the first
part's SID."""

from collections.abc import Mapping

from app.contracts import MessageDirection, MessageSender
from app.contracts.common import CaseId, LanguageCode, QuestionId
from app.db import tables
from app.db.messages import append_message
from app.relay.templates import LANGUAGES, render
from app.relay.whatsapp import WhatsApp


async def send_template(
    whatsapp: WhatsApp,
    user: tables.User,
    template_id: str,
    values: Mapping[str, object] | None = None,
    *,
    values_en: Mapping[str, object] | None = None,
    language: LanguageCode | None = None,
    case_id: CaseId | None = None,
    question_id: QuestionId | None = None,
) -> tables.Message:
    """Send a pre-translated template in `language` (default: the user's). Before
    the user has picked a language, it goes out in every supported language.
    `values_en` replaces `values` in the logged English when a value was translated
    (rule 6)."""
    values = values or {}
    language = language or user.language
    body = render(template_id, language, **values)
    sids = await whatsapp.send(user.whatsapp_number, body)
    return await append_message(
        user.id,
        MessageDirection.OUT,
        MessageSender.RELAY,
        body,
        language or LANGUAGES[0],
        body_en=render(template_id, "en", **(values_en or values)),
        case_id=case_id,
        template=template_id,
        question_id=question_id,
        twilio_sid=sids[0] if sids else None,
    )


async def send_text(
    whatsapp: WhatsApp,
    user: tables.User,
    body: str,
    *,
    body_en: str | None = None,
    case_id: CaseId | None = None,
) -> tables.Message:
    """Free-form text. Only the orchestrator may call this (product rule 1)."""
    sids = await whatsapp.send(user.whatsapp_number, body)
    language = user.language or "en"
    return await append_message(
        user.id,
        MessageDirection.OUT,
        MessageSender.ORCHESTRATOR,
        body,
        language,
        body_en=body if language == "en" else body_en,
        case_id=case_id,
        twilio_sid=sids[0] if sids else None,
    )
