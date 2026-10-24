"""The WhatsApp pipe: what happens to each inbound message after the webhook acks.

Order per message: user row → media saved → inbound logged → routed (language pick,
photo grouping, "same letter or new?" answer, or an orchestrator turn).
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import lru_cache, partial

from anthropic import AsyncAnthropic
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import MessageDirection, MessageSender
from app.contracts.common import DocumentId, LanguageCode, MediaId, UserId
from app.db import reads, tables
from app.db.messages import append_message
from app.db.writes import orchestrator as writes
from app.orchestrator.language import (
    LanguageStep,
    answer_to_prompt,
    last_language_prompt,
    parse_choice,
    prompt_for,
)
from app.orchestrator.photos import PHOTO_QUIET_WINDOW_S, PendingPages, PhotoBatcher
from app.relay.inbound import InboundMedia, InboundMessage
from app.relay.media import MediaDownloadError
from app.relay.outbound import send_template, send_text
from app.relay.whatsapp import WhatsApp, WhatsAppSendError, get_whatsapp
from app.settings import get_settings
from app.translation.detect import detect_language

logger = logging.getLogger(__name__)

LanguageDetector = Callable[[str], Awaitable[LanguageCode | None]]

# Before the user picks a language, an undetectable message is logged as English.
_FALLBACK_LANGUAGE = "en"


class InboundPipe:
    def __init__(
        self,
        whatsapp: WhatsApp,
        detect: LanguageDetector,
        quiet_window_s: float = PHOTO_QUIET_WINDOW_S,
    ) -> None:
        self._whatsapp = whatsapp
        self._detect = detect
        self.photos = PhotoBatcher(self._letter_ready, quiet_window_s)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle(self, message: InboundMessage) -> None:
        """Runs as a background task per webhook. One number's messages are handled
        one at a time, in arrival order, so a burst of photos can't race."""
        async with self._locks[message.whatsapp_number]:
            try:
                await self._handle(message)
            except WhatsAppSendError as exc:
                logger.error("Reply to sid=%s failed: %s", message.message_sid, exc)
            except (SQLAlchemyError, OSError):
                logger.exception("Handling sid=%s failed", message.message_sid)

    async def _handle(self, message: InboundMessage) -> None:
        user = await writes.get_or_create_user(message.whatsapp_number)
        saved, failed = await self._save_media(user.id, message)

        step = None
        language = user.language
        if language is None:
            step, language = await self._language_step(user.id, message)

        await append_message(
            user.id,
            MessageDirection.IN,
            MessageSender.USER,
            message.body,
            language,
            # Goal 5: translate into English here, before the row is written.
            body_en=message.body if language == "en" else None,
            media_ids=[media_id for media_id, _ in saved],
            twilio_sid=message.message_sid,
        )
        if failed:
            await send_template(self._whatsapp, user, "media.download_failed")

        pages = [media_id for media_id, item in saved if item.is_letter_page]
        if step is not None:
            await self._apply_language_step(user, step, pages)
        elif pages:
            await self._letter_pages(user, pages)
        elif (pending := self.photos.pending(user.id)) is not None:
            await self._same_or_new_answer(user, message.text, pending)
        else:
            await self._orchestrator_turn(user, message)

    async def _save_media(
        self, user_id: UserId, message: InboundMessage
    ) -> tuple[list[tuple[MediaId, InboundMedia]], int]:
        """Download and store each media item; returns the saved ones and how many
        failed."""
        saved: list[tuple[MediaId, InboundMedia]] = []
        failed = 0
        for item in message.media:
            try:
                downloaded = await self._whatsapp.download(item, message.message_sid)
            except MediaDownloadError as exc:
                # No traceback: the chained httpx error would print the media URL.
                logger.error("%s", exc)
                failed += 1
                continue
            row = await writes.save_media(
                user_id, downloaded.content_type, downloaded.data, item.url
            )
            saved.append((row.id, item))
        return saved, failed

    async def _language_step(
        self, user_id: UserId, message: InboundMessage
    ) -> tuple[LanguageStep, LanguageCode]:
        """The next language-pick step, and the language to log the message in."""
        last_prompt = await last_language_prompt(user_id)
        step = answer_to_prompt(message.text, last_prompt) if message.text else None
        detected = None
        if step is None:
            detected = await self._detect(message.text) if message.text else None
            step = prompt_for(
                detected,
                has_text=bool(message.text),
                prompt_pending=last_prompt is not None,
            )
        prompt_language = last_prompt.language if last_prompt else None
        return step, step.chosen or detected or prompt_language or _FALLBACK_LANGUAGE

    async def _apply_language_step(
        self, user: tables.User, step: LanguageStep, pages: list[MediaId]
    ) -> None:
        if pages:
            # No research before the language is known; the batch waits for it.
            self.photos.add(user.id, pages, hold=True)
        if step.chosen is not None:
            user = await writes.set_language(user.id, step.chosen)
            logger.info("Language set user_id=%s language=%s", user.id, step.chosen)
            if self.photos.is_open(user.id):
                self.photos.release(user.id)
                await send_template(self._whatsapp, user, "language.set_letter")
            else:
                await send_template(self._whatsapp, user, "language.set")
        elif step.prompt is not None:
            await send_template(
                self._whatsapp, user, step.prompt, language=step.prompt_language
            )

    async def _letter_pages(self, user: tables.User, pages: list[MediaId]) -> None:
        if self.photos.is_open(user.id):
            self.photos.add(user.id, pages)
            return
        if (pending := self.photos.pending(user.id)) is not None:
            self.photos.hold_for_answer(user.id, pending.document_id, pages)
            return
        # Research has started on a letter: the gap alone can't say whether this
        # is page 2 or a new letter (C20), so ask.
        document_id = await _latest_active_letter(user.id)
        if document_id is not None:
            self.photos.hold_for_answer(user.id, document_id, pages)
            await send_template(self._whatsapp, user, "letter.same_or_new")
            return
        self.photos.add(user.id, pages)
        await send_template(self._whatsapp, user, "letter.received")

    async def _same_or_new_answer(
        self, user: tables.User, text: str, pending: PendingPages
    ) -> None:
        choice = parse_choice(text, 2)
        if choice is None:
            await send_template(self._whatsapp, user, "letter.same_or_new")
            return
        self.photos.take_pending(user.id)
        if choice == 1:
            await writes.add_pages(pending.document_id, pending.media_ids)
            logger.info(
                "Pages added user_id=%s document_id=%s pages=%d",
                user.id,
                pending.document_id,
                len(pending.media_ids),
            )
            await send_template(self._whatsapp, user, "letter.pages_added")
            # Goal 4: re-run the fast pass on the updated letter.
        else:
            self.photos.add(user.id, pending.media_ids)
            await send_template(self._whatsapp, user, "letter.received")

    async def _letter_ready(self, user_id: UserId, media_ids: list[MediaId]) -> None:
        document = await writes.create_document(user_id, media_ids)
        logger.info(
            "Letter ready user_id=%s document_id=%s pages=%d",
            user_id,
            document.id,
            len(media_ids),
        )
        # Goal 4.2: mint case_id and enqueue research_fast for this document.

    async def _orchestrator_turn(
        self, user: tables.User, message: InboundMessage
    ) -> None:
        """Stub until Goal 4's Claude turn: echo text so the pipe can be tried on a
        phone."""
        if message.text:
            await send_text(self._whatsapp, user, f"Echo: {message.text}")


async def _latest_active_letter(user_id: UserId) -> DocumentId | None:
    """The newest document of the newest active case, if research has started."""
    for case in await reads.list_active_cases(user_id):
        if case.document_ids:
            return case.document_ids[-1]
    return None


async def _no_detection(text: str) -> None:
    return None


@lru_cache
def get_pipe() -> InboundPipe:
    settings = get_settings()
    detect: LanguageDetector = _no_detection
    if settings.anthropic_api_key:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        detect = partial(detect_language, client, settings.model_fast)
    else:
        logger.warning("ANTHROPIC_API_KEY not set: first contact always gets the menu")
    return InboundPipe(get_whatsapp(), detect)
