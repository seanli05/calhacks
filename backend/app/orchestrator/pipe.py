"""The WhatsApp pipe: what happens to each inbound message after the webhook acks.

Order per message: user row → media saved → inbound logged → routed. Routing order:
a reply to an ask_user question (the call is waiting), then the language pick, photo
grouping, a "same letter or new?" answer, an answer to research's question about the
letter (C39), an answer to a consent request, an answer to "may I save this?" (C15),
or an orchestrator turn. After a turn, the user is asked about facts waiting for their
OK, but only at a quiet moment: no other numbered question open or waiting, research
done with their letters, and no call running.

One number's messages are routed one at a time, under a per-number lock. An
orchestrator turn (slow: a Claude call) runs after that lock is released, under the
user's conversation lock, which proactive messages share (conversation.py), so a reply
to an open ask_user question never waits behind it (whatsapp-pipe.md, concern 8).
After each message, a question that waited for the user's answer goes out if no other
is open now.
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
from app.db import reads, tables
from app.db.messages import append_message
from app.db.writes import orchestrator as writes
from app.orchestrator.call_status import get_call_status
from app.orchestrator.consent import ConsentGate
from app.orchestrator.conversation import Conversation
from app.orchestrator.fact_consent import FactConsent
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
from app.orchestrator.research_questions import ResearchQuestions
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
# "Typing…" during a turn: its 60 s budget plus a wait for the conversation lock.
TURN_TYPING_S = 90.0


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
        fact_consent: FactConsent | None = None,
        conversation: Conversation | None = None,
    ) -> None:
        """Without `to_english`, non-English messages are logged with no `body_en`;
        without `turn`, free text is echoed (no Anthropic key); without `consent`,
        nothing is routed to a consent request; without `fact_consent`, pending
        facts are never asked about. `conversation` must be the one the consent
        gate and the letter results share."""
        self._whatsapp = whatsapp
        self._detect = detect
        self._ask_user = ask_user
        self.letters = letters
        self._to_english = to_english
        self._turn = turn
        self._consent = consent
        self._fact_consent = fact_consent
        self.photos = PhotoBatcher(self._letter_ready, quiet_window_s)
        self.conversation = conversation or Conversation(whatsapp)
        self.conversation.bind(self.question_open)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle(self, message: InboundMessage) -> None:
        """Runs as a background task per webhook. One number's messages are routed
        one at a time, in arrival order, so a burst of photos can't race; an
        orchestrator turn runs after the routing lock is released."""
        number = message.whatsapp_number
        async with self._locks[number]:
            routed = await self._guarded(message, self._handle(message))
        if routed is None:
            return
        user_id, turn = routed
        if turn is not None:
            await self._guarded(message, turn())
        await self._guarded(message, self.conversation.flush(user_id))

    async def question_open(self, user_id: UserId) -> bool:
        """A numbered question (or research's question about a letter) is waiting
        for the user's answer: another one now would make a "1" ambiguous."""
        consent = self._consent
        facts = self._fact_consent
        return (
            (consent is not None and consent.pending(user_id) is not None)
            or (facts is not None and facts.pending(user_id) is not None)
            or self.photos.pending(user_id) is not None
            or self.letters.question_pending(user_id)
            or await self._ask_user.question_for_reply(user_id) is not None
        )

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

    async def _handle(self, message: InboundMessage) -> tuple[UserId, Turn | None]:
        """Route the message; returns the user and the orchestrator turn to run, if
        any."""
        user = await writes.get_or_create_user(message.whatsapp_number)
        self.conversation.heard(user.id, message.message_sid)
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
            return user.id, None

        pages = [media_id for media_id, item in saved if item.is_letter_page]
        turn = None
        if step is not None:
            await self._apply_language_step(user, step, pages)
        elif pages:
            await self._letter_pages(user, pages)
        elif (pending := self.photos.pending(user.id)) is not None:
            turn = await self._same_or_new_answer(user, message, inbound, pending)
        elif message.text and self.letters.question_pending(user.id):
            await self._letter_answer(user, message, inbound)
        elif self._consent is not None and self._consent.pending(user.id) is not None:
            turn = await self._consent_answer(user, message, inbound)
        elif self._fact_consent is not None and self._fact_consent.pending(user.id):
            turn = await self._fact_consent_answer(user, message, inbound)
        else:
            turn = partial(self._orchestrator_turn, user, message, inbound.id)
        return user.id, turn

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

    async def _letter_answer(
        self, user: tables.User, message: InboundMessage, inbound: tables.Message
    ) -> None:
        """C39: any text answers research's question about the letter; research reads
        it (in English) as data, so there's nothing to parse here."""
        answer_en = inbound.body_en or message.text
        if await self.letters.answer_question(user, answer_en):
            await send_template(self._whatsapp, user, "letter.reading_again")

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

    async def _fact_consent_answer(
        self, user: tables.User, message: InboundMessage, inbound: tables.Message
    ) -> Turn | None:
        """A 1/yes or 2/no answers "may I save this?"; anything else closes the
        question unanswered (the facts stay pending) and goes to the turn."""
        assert self._fact_consent is not None
        choice = parse_yes_no(message.text) if message.text else None
        if choice is not None:
            await self._fact_consent.answer(user, choice)
            return None
        self._fact_consent.drop(user.id)
        return partial(self._orchestrator_turn, user, message, inbound.id)

    async def _ask_about_facts(self, user_id: UserId) -> None:
        """C15: after a turn, ask about facts waiting for the user's OK, at a quiet
        moment only. Not while another numbered question is open or waiting (its
        "1" must not be read as this one's), and not while research or a call will
        soon send the user something else: the question would get lost among it."""
        if self._fact_consent is None:
            return
        if (
            await self.question_open(user_id)
            or self.conversation.is_waiting(user_id)
            or self.letters.researching(user_id)
            or (self._consent is not None and self._consent.calling(user_id))
        ):
            return
        # Re-read: the turn may have switched the user's language.
        user = await reads.get_user(user_id)
        if user is not None:
            await self._fact_consent.ask(user)

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
            # "Typing…" from the start, even while a proactive message holds the
            # lock; it stops before "may I save this?", so it can't show after it.
            with self.conversation.typing_while(user.id, "turn", TURN_TYPING_S):
                async with self.conversation.speaking(user.id):
                    try:
                        await self._turn(
                            user,
                            message_id,
                            same_or_new_pending=same_or_new_pending,
                            consent_pending=consent_pending,
                        )
                    finally:
                        self.conversation.done_typing(user.id, "turn")
                    await self._ask_about_facts(user.id)
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
    conversation = Conversation(whatsapp)
    consent, letters = _results_path(whatsapp, translator, conversation)
    if translator is None:
        logger.warning(
            "ANTHROPIC_API_KEY not set: first contact always gets the menu, nothing "
            "is translated, and free text is echoed"
        )
        return InboundPipe(
            whatsapp,
            _no_detection,
            get_ask_user(),
            letters,
            consent=consent,
            conversation=conversation,
        )
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    turn = OrchestratorTurn(
        client,
        settings.model_default,
        whatsapp,
        translator,
        consent,
        research_questions=ResearchQuestions(
            whatsapp, translator, get_job_watcher(), conversation=conversation
        ),
    )
    return InboundPipe(
        whatsapp,
        partial(detect_language, client, settings.model_fast),
        get_ask_user(),
        letters,
        to_english=translator.to_english,
        turn=turn.run,
        consent=consent,
        fact_consent=FactConsent(whatsapp, translator),
        conversation=conversation,
    )


def _results_path(
    whatsapp: WhatsApp, translator: Translator | None, conversation: Conversation
) -> tuple[ConsentGate, Letters]:
    """Letter → explanation → verdict → consent → call → summary."""
    job_watcher = get_job_watcher()
    consent = ConsentGate(
        whatsapp, translator, job_watcher, get_call_status(), conversation=conversation
    )
    verdicts = Verdicts(whatsapp, translator, consent, conversation=conversation)
    results = LetterResults(whatsapp, translator, verdicts, conversation=conversation)
    return consent, Letters(whatsapp, job_watcher, results, conversation=conversation)
