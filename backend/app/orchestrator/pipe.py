"""The WhatsApp pipe: what happens to each inbound message after the webhook acks.

Order per message: user row → media saved → inbound logged → routed. Routing order:
a reply to an ask_user question (the call is waiting), then the language pick, photo
grouping, a "same letter or new?" answer, an answer to a consent request, or an
orchestrator turn.

One number's messages are routed one at a time, under a per-number lock. An
orchestrator turn (slow: a Claude call) runs after that lock is released, under a
second per-number lock, so a reply to an open ask_user question never waits behind it
(whatsapp-pipe.md, concern 8).
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import lru_cache, partial
from typing import Protocol

from anthropic import AsyncAnthropic
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import MessageDirection, MessageSender
from app.contracts.common import LanguageCode, MediaId, MessageId, UserId
from app.db import tables
from app.db.messages import append_message
from app.db.writes import orchestrator as writes
from app.orchestrator.call_status import get_call_status
from app.orchestrator.consent import ConsentGate
from app.orchestrator.job_watch import get_job_watcher
from app.orchestrator.language import (
    LanguageStep,
    answer_to_prompt,
    last_language_prompt,
    prompt_for,
)
from app.orchestrator.letter_result import LetterResults
from app.orchestrator.letters import Letters
from app.orchestrator.photos import PHOTO_QUIET_WINDOW_S, PendingPages, PhotoBatcher
from app.orchestrator.turn import OrchestratorTurn
from app.orchestrator.verdicts import Verdicts
from app.relay.ask_user import AskUser, get_ask_user
from app.relay.inbound import InboundMedia, InboundMessage
from app.relay.media import MediaDownloadError
from app.relay.outbound import send_template, send_text
from app.relay.replies import parse_choice, parse_yes_no
from app.relay.whatsapp import WhatsApp, WhatsAppSendError, get_whatsapp
from app.settings import get_settings
from app.translation.detect import detect_language
from app.translation.translate import Translator, get_translator

logger = logging.getLogger(__name__)

LanguageDetector = Callable[[str], Awaitable[LanguageCode | None]]
ToEnglish = Callable[[str, LanguageCode], Awaitable[str | None]]
Turn = Callable[[], Awaitable[None]]


class TurnRunner(Protocol):
    """The orchestrator's reply to free text (`OrchestratorTurn.run`)."""

    async def __call__(
        self,
        user: tables.User,
        message_id: MessageId,
        *,
        same_or_new_pending: bool = False,
        consent_pending: bool = False,
    ) -> None: ...


# Before the user picks a language, an undetectable message is logged as English.
_FALLBACK_LANGUAGE = "en"


class InboundPipe:
    def __init__(
        self,
        whatsapp: WhatsApp,
        detect: LanguageDetector,
        ask_user: AskUser,
        letters: Letters,
        quiet_window_s: float = PHOTO_QUIET_WINDOW_S,
        *,
        to_english: ToEnglish | None = None,
        turn: TurnRunner | None = None,
        consent: ConsentGate | None = None,
    ) -> None:
        """Without `to_english`, non-English messages are logged with no `body_en`;
        without `turn`, free text is echoed (no Anthropic key); without `consent`,
        nothing is routed to a consent request."""
        self._whatsapp = whatsapp
        self._detect = detect
        self._ask_user = ask_user
        self.letters = letters
        self._to_english = to_english
        self._turn = turn
        self._consent = consent
        self.photos = PhotoBatcher(self._letter_ready, quiet_window_s)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._turn_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle(self, message: InboundMessage) -> None:
        """Runs as a background task per webhook. One number's messages are routed
        one at a time, in arrival order, so a burst of photos can't race; an
        orchestrator turn runs after the routing lock is released."""
        number = message.whatsapp_number
        async with self._locks[number]:
            turn = await self._guarded(message, self._handle(message))
        if turn is not None:
            async with self._turn_locks[number]:
                await self._guarded(message, turn())

    async def _guarded[T](
        self, message: InboundMessage, work: Awaitable[T]
    ) -> T | None:
        try:
            return await work
        except WhatsAppSendError as exc:
            logger.error("Reply to sid=%s failed: %s", message.message_sid, exc)
        except (SQLAlchemyError, OSError):
            logger.exception("Handling sid=%s failed", message.message_sid)
        return None

    async def _handle(self, message: InboundMessage) -> Turn | None:
        """Route the message; returns the orchestrator turn to run, if any."""
        user = await writes.get_or_create_user(message.whatsapp_number)
        saved, failed = await self._save_media(user.id, message)

        step = None
        question = None
        language = user.language
        if language is None:
            step, language = await self._language_step(user.id, message)
        elif message.text:
            question = await self._ask_user.question_for_reply(user.id)

        inbound = await append_message(
            user.id,
            MessageDirection.IN,
            MessageSender.USER,
            message.body,
            language,
            body_en=await self._english(message, language, answers_question=question),
            media_ids=[media_id for media_id, _ in saved],
            question_id=question.id if question else None,
            twilio_sid=message.message_sid,
        )
        if failed:
            await send_template(self._whatsapp, user, "media.download_failed")
        if question is not None and await self._ask_user.handle_reply(
            user, question, message.text
        ):
            return None

        pages = [media_id for media_id, item in saved if item.is_letter_page]
        if step is not None:
            await self._apply_language_step(user, step, pages)
        elif pages:
            await self._letter_pages(user, pages)
        elif (pending := self.photos.pending(user.id)) is not None:
            return await self._same_or_new_answer(user, message, inbound, pending)
        elif self._consent is not None and self._consent.pending(user.id) is not None:
            return await self._consent_answer(user, message, inbound)
        else:
            return partial(self._orchestrator_turn, user, message, inbound.id)
        return None

    async def _english(
        self,
        message: InboundMessage,
        language: LanguageCode,
        *,
        answers_question: tables.Question | None,
    ) -> str | None:
        """The English for the log (rule 6). Skipped for a reply to an open ask_user
        question, which must not wait on a model call; a bare number is the same in
        English."""
        if language == "en" or parse_choice(message.text, 99) is not None:
            return message.body
        if not message.text or answers_question is not None or self._to_english is None:
            return None
        return await self._to_english(message.text, language)

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
        document_id = await self.letters.active_letter(user.id)
        if document_id is not None:
            self.photos.hold_for_answer(user.id, document_id, pages)
            await send_template(self._whatsapp, user, "letter.same_or_new")
            return
        self.photos.add(user.id, pages)
        await send_template(self._whatsapp, user, "letter.received")

    async def _same_or_new_answer(
        self,
        user: tables.User,
        message: InboundMessage,
        inbound: tables.Message,
        pending: PendingPages,
    ) -> Turn | None:
        """A "1" or "2" settles it; other text goes to the orchestrator turn, which
        answers and reminds the user to pick (or re-asks, without a turn)."""
        choice = parse_choice(message.text, 2)
        if choice is None:
            if self._turn is not None and message.text:
                return partial(
                    self._orchestrator_turn,
                    user,
                    message,
                    inbound.id,
                    same_or_new_pending=True,
                )
            await send_template(self._whatsapp, user, "letter.same_or_new")
            return None
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
            await self.letters.pages_added(user, pending.document_id)
        else:
            self.photos.add(user.id, pending.media_ids)
            await send_template(self._whatsapp, user, "letter.received")
        return None

    async def _consent_answer(
        self, user: tables.User, message: InboundMessage, inbound: tables.Message
    ) -> Turn | None:
        """A 1/yes or 2/no answers the consent request in code (rule 4: the model
        never starts a call); other text goes to the turn, which reminds the user."""
        assert self._consent is not None
        choice = parse_yes_no(message.text) if message.text else None
        if choice is not None:
            await self._consent.answer(user, inbound, choice)
            return None
        if self._turn is not None and message.text:
            return partial(
                self._orchestrator_turn,
                user,
                message,
                inbound.id,
                consent_pending=True,
            )
        if message.text:
            await send_template(self._whatsapp, user, "consent.reprompt")
        return None

    async def _letter_ready(self, user_id: UserId, media_ids: list[MediaId]) -> None:
        document = await writes.create_document(user_id, media_ids)
        logger.info(
            "Letter ready user_id=%s document_id=%s pages=%d",
            user_id,
            document.id,
            len(media_ids),
        )
        await self.letters.start(user_id, document.id)

    async def _orchestrator_turn(
        self,
        user: tables.User,
        message: InboundMessage,
        message_id: MessageId,
        *,
        same_or_new_pending: bool = False,
        consent_pending: bool = False,
    ) -> None:
        if self._turn is not None:
            await self._turn(
                user,
                message_id,
                same_or_new_pending=same_or_new_pending,
                consent_pending=consent_pending,
            )
        elif message.text:
            # No Anthropic key: echo, so the pipe can still be tried on a phone.
            await send_text(self._whatsapp, user, f"Echo: {message.text}")


async def _no_detection(text: str) -> None:
    return None


@lru_cache
def get_pipe() -> InboundPipe:
    settings = get_settings()
    whatsapp = get_whatsapp()
    translator = get_translator()
    consent, letters = _results_path(whatsapp, translator)
    if translator is None:
        logger.warning(
            "ANTHROPIC_API_KEY not set: first contact always gets the menu, nothing "
            "is translated, and free text is echoed"
        )
        return InboundPipe(
            whatsapp, _no_detection, get_ask_user(), letters, consent=consent
        )
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    turn = OrchestratorTurn(
        client, settings.model_default, whatsapp, translator, consent
    )
    return InboundPipe(
        whatsapp,
        partial(detect_language, client, settings.model_fast),
        get_ask_user(),
        letters,
        to_english=translator.to_english,
        turn=turn.run,
        consent=consent,
    )


def _results_path(
    whatsapp: WhatsApp, translator: Translator | None
) -> tuple[ConsentGate, Letters]:
    """Letter → explanation → verdict → consent → call → summary."""
    job_watcher = get_job_watcher()
    consent = ConsentGate(whatsapp, translator, job_watcher, get_call_status())
    verdicts = Verdicts(whatsapp, translator, consent)
    results = LetterResults(whatsapp, translator, verdicts)
    return consent, Letters(whatsapp, job_watcher, results)
