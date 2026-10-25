"""The WhatsApp pipe: what happens to each inbound message after the webhook acks.

Order per message: user row → media saved → inbound logged → routed. Code answers
what's instant and certain: a bare number to an ask_user question (the call is
waiting), the language pick, photo grouping, a bare 1/2 to "same letter or new?", an
answer to research's question about the letter (C39, any text), and a 1/2 or yes/no
word to a consent request or to "may I save this?" (C15). Everything else goes to the
orchestrator turn, with what's open (open_questions.py), so the model answers it
through guarded tools: hear, decide, act. A turn's plain reply may end with "may I
save this?", but only at a quiet moment: no other numbered question open or waiting,
research done with their letters, and no call running.

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

from app.contracts import MessageDirection, MessageSender, QuestionStatus
from app.contracts.common import LanguageCode, MediaId, MessageId, UserId
from app.db import tables
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
from app.orchestrator.open_questions import (
    CONSENT_OPTIONS_EN,
    SAME_OR_NEW_OPTIONS_EN,
    SAVE_FACTS_OPTIONS_EN,
    OpenQuestion,
    OpenQuestions,
    QuestionKind,
)
from app.orchestrator.photos import PHOTO_QUIET_WINDOW_S, PendingPages, PhotoBatcher
from app.orchestrator.research_questions import ResearchQuestions
from app.orchestrator.turn import OrchestratorTurn, QuietMoment
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
        open_questions: OpenQuestions | None = None,
        quiet_moment: QuietMoment | None = None,
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
        without `turn`, free text is echoed or re-asked for a number (no Anthropic
        key); without `consent`, nothing is routed to a consent request; without
        `fact_consent`, no "may I save this?" answer is routed. `conversation` must
        be the one the consent gate and the letter results share; `fact_consent`
        the one the turn asks with."""
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

    async def open_questions(self, user_id: UserId) -> OpenQuestions:
        """The numbered questions waiting for the user, for the turn."""
        questions = []
        call_question = await self._ask_user.question_for_reply(user_id)
        if call_question is not None and call_question.status == QuestionStatus.OPEN:
            questions.append(
                OpenQuestion(
                    QuestionKind.CALL_QUESTION,
                    call_question.id,
                    tuple(call_question.options_en),
                )
            )
        if self._consent is not None and (consent := self._consent.pending(user_id)):
            questions.append(
                OpenQuestion(
                    QuestionKind.CALL_CONSENT, consent.case_id, CONSENT_OPTIONS_EN
                )
            )
        same_or_new = self.photos.pending(user_id) is not None
        if same_or_new:
            questions.append(
                OpenQuestion(QuestionKind.SAME_OR_NEW, None, SAME_OR_NEW_OPTIONS_EN)
            )
        if self._fact_consent is not None and self._fact_consent.pending(user_id):
            questions.append(
                OpenQuestion(QuestionKind.SAVE_FACTS, None, SAVE_FACTS_OPTIONS_EN)
            )
        return OpenQuestions(
            tuple(questions),
            settle_same_or_new=self._settle_same_or_new if same_or_new else None,
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

        answers_call = question is not None and (
            parse_choice(message.text, len(question.options_en)) is not None
        )
        inbound = await append_message(
            user.id,
            MessageDirection.IN,
            MessageSender.USER,
            message.body,
            language,
            body_en=await self._english(message, language),
            media_ids=[media_id for media_id, _ in saved],
            question_id=question.id if question and answers_call else None,
            twilio_sid=message.message_sid,
        )
        if failed:
            await send_template(self._whatsapp, user, "media.download_failed")
        if question is not None and await self._ask_user.handle_reply(
            user, question, message.text, reprompt=self._turn is None
        ):
            return user.id, None

        pages = [media_id for media_id, item in saved if item.is_letter_page]
        same_or_new = self.photos.pending(user.id)
        consent_open = (
            self._consent is not None and self._consent.pending(user.id) is not None
        )
        facts_open = (
            self._fact_consent is not None
            and self._fact_consent.pending(user.id) is not None
        )
        yes_no = parse_yes_no(message.text) if message.text else None
        turn = None
        if step is not None:
            await self._apply_language_step(user, step, pages)
        elif pages:
            await self._letter_pages(user, pages)
        elif same_or_new is not None and (n := parse_choice(message.text, 2)):
            await self._settle_same_or_new(user, n)
        elif (
            message.text
            and same_or_new is None
            and self.letters.question_pending(user.id)
        ):
            await self._letter_answer(user, message, inbound)
        elif consent_open and yes_no is not None:
            # Rule 4: a bare 1/yes is answered in code, never by the model.
            assert self._consent is not None
            await self._consent.answer(user, inbound, yes_no)
        elif facts_open and yes_no is not None:
            assert self._fact_consent is not None
            await self._fact_consent.answer(user, yes_no)
        elif self._turn is None:
            await self._without_turn(user, message, same_or_new, consent_open)
        else:
            turn = partial(self._orchestrator_turn, user, inbound.id)
        return user.id, turn

    async def _english(
        self, message: InboundMessage, language: LanguageCode
    ) -> str | None:
        """The English for the log and the turn (rule 6). A bare number is the same
        in English, so a reply to an ask_user question never waits on a model
        call."""
        if language == "en" or parse_choice(message.text, 99) is not None:
            return message.body
        if not message.text or self._to_english is None:
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

    async def _settle_same_or_new(self, user: tables.User, choice: int) -> bool:
        """1: the held photos join the letter; 2: they start a new one. False if no
        "same letter or new?" is open (the turn's tool, a stale snapshot)."""
        pending = self.photos.take_pending(user.id)
        if pending is None:
            return False
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
        return True

    async def _without_turn(
        self,
        user: tables.User,
        message: InboundMessage,
        same_or_new: PendingPages | None,
        consent_open: bool,
    ) -> None:
        """No Anthropic key: re-ask an open question for its number, or echo, so
        the pipe can still be tried on a phone."""
        if same_or_new is not None:
            await send_template(self._whatsapp, user, "letter.same_or_new")
        elif consent_open and message.text:
            await send_template(self._whatsapp, user, "consent.reprompt")
        elif message.text:
            if self._fact_consent is not None:
                self._fact_consent.drop(user.id)
            await send_text(self._whatsapp, user, f"Echo: {message.text}")

    async def _letter_answer(
        self, user: tables.User, message: InboundMessage, inbound: tables.Message
    ) -> None:
        """C39: any text answers research's question about the letter; research reads
        it (in English) as data, so there's nothing to parse here."""
        answer_en = inbound.body_en or message.text
        if await self.letters.answer_question(user, answer_en):
            await send_template(self._whatsapp, user, "letter.reading_again")

    async def _quiet_moment(self, user_id: UserId) -> bool:
        """C15: "may I save this?" only at a quiet moment. Not while another
        numbered question is open or waiting (its "1" must not be read as this
        one's), and not while research or a call will soon send the user something
        else: the question would get lost among it."""
        return not (
            await self.question_open(user_id)
            or self.conversation.is_waiting(user_id)
            or self.letters.researching(user_id)
            or (self._consent is not None and self._consent.calling(user_id))
        )

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
        self, user: tables.User, message_id: MessageId
    ) -> None:
        assert self._turn is not None
        # "Typing…" from the start, even while a proactive message holds the lock.
        with self.conversation.typing_while(user.id, "turn", TURN_TYPING_S):
            async with self.conversation.speaking(user.id):
                facts = self._fact_consent
                facts_asked = facts.pending(user.id) if facts is not None else None
                try:
                    await self._turn(
                        user,
                        message_id,
                        open_questions=await self.open_questions(user.id),
                        quiet_moment=self._quiet_moment,
                    )
                finally:
                    self.conversation.done_typing(user.id, "turn")
                if (
                    facts is not None
                    and facts_asked is not None
                    and facts.pending(user.id) is facts_asked
                ):
                    # Not answered: it stays open one more message, then
                    # closes; the facts stay pending (C15).
                    facts.unanswered(user.id)


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
    ask_user = get_ask_user()
    fact_consent = FactConsent(whatsapp, translator)
    turn = OrchestratorTurn(
        client,
        settings.model_default,
        whatsapp,
        translator,
        consent,
        research_questions=ResearchQuestions(
            whatsapp, translator, get_job_watcher(), conversation=conversation
        ),
        ask_user=ask_user,
        fact_consent=fact_consent,
    )
    return InboundPipe(
        whatsapp,
        partial(detect_language, client, settings.model_fast),
        ask_user,
        letters,
        to_english=translator.to_english,
        turn=turn.run,
        consent=consent,
        fact_consent=fact_consent,
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
