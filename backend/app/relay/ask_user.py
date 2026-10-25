"""ask_user (Plan.md → P1, C5, C10, C24).

The phone agent awaits `ask`: the relay records the question in `questions`, sends
it as a numbered template, and waits for the reply on an in-process future keyed by
`question_id`. The `questions` row is the source of truth: `answer_question` and
`time_out_question` only close an open row, so when a reply and the timeout race,
exactly one wins.

A reply that loses to the timeout, or arrives within LATE_REPLY_WINDOW_S after it,
gets a message saying which option the agent already took (C24). Recently timed-out
questions are remembered in memory (one process serves every webhook); a restart
forgets them, and a late reply then goes to the orchestrator like any other text.

Cancelling `ask` (the phone agent moved on: a new menu prompt, hold, a person) closes
the question quietly, so the user's next reply goes to normal routing.

Option labels come in English and are translated as the question goes out, under a
short timeout: if that fails or is slow, they go out in English rather than delay
the question (whatsapp-pipe.md, concern 7).
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.contracts import (
    AskUserReply,
    AskUserRequest,
    Component,
    Event,
    EventType,
    QuestionStatus,
)
from app.contracts.common import LanguageCode, QuestionId, UserId
from app.db import reads, tables
from app.db.errors import NotFound
from app.db.events import append_event
from app.db.ids import new_id
from app.db.tables import utcnow
from app.db.writes import relay as writes
from app.relay.outbound import send_template
from app.relay.replies import parse_choice
from app.relay.templates import TEMPLATES
from app.relay.whatsapp import WhatsApp, WhatsAppSendError, get_whatsapp
from app.translation.script import local_digits
from app.translation.translate import get_translator

logger = logging.getLogger(__name__)

LATE_REPLY_WINDOW_S = 600.0
# How long `ask` waits for the reply handler after losing the race to it: the handler
# resolves the future right after its answer commits, so this is a safety net.
_RACE_GRACE_S = 5.0
# The question is waiting on the call; past this, its options go out in English.
LABELS_TIMEOUT_S = 3.0

LabelTranslator = Callable[[list[str], LanguageCode], Awaitable[list[str] | None]]


@dataclass
class _TimedOut:
    question: tables.Question
    at: float
    # The option labels as the user saw them.
    labels: list[str]


def template_id(request_template: str) -> str:
    """P1's `template` names the question kind (e.g. `menu_choice`)."""
    return f"ask_user.{request_template}"


class AskUser:
    def __init__(
        self,
        whatsapp: WhatsApp,
        late_reply_window_s: float = LATE_REPLY_WINDOW_S,
        *,
        translate_labels: LabelTranslator | None = None,
        labels_timeout_s: float = LABELS_TIMEOUT_S,
    ) -> None:
        """Without `translate_labels`, option labels go out in English."""
        self._whatsapp = whatsapp
        self._late_reply_window_s = late_reply_window_s
        self._translate_labels = translate_labels
        self._labels_timeout_s = labels_timeout_s
        self._waiting: dict[QuestionId, asyncio.Future[int]] = {}
        self._timed_out: dict[UserId, _TimedOut] = {}
        self._late_replied: set[QuestionId] = set()

    async def ask(self, request: AskUserRequest) -> AskUserReply:
        """Ask the user and wait up to `timeout_s`. On timeout, or if the question
        can't be sent, the reply carries `default_option` (the safest choice) and a
        `call.ask_user_timeout` event is logged."""
        if template_id(request.template) not in TEMPLATES:
            raise ValueError(f"No template for ask_user kind {request.template!r}")
        user, case_id = await _user_for_call(request.call_id)
        question = await writes.create_question(request, user.id)
        # A newer question supersedes an older one's late-reply window.
        self._timed_out.pop(user.id, None)
        try:
            return await self._ask(request, question, user, case_id)
        except asyncio.CancelledError:
            await self._cancelled(question)
            raise

    async def _ask(
        self,
        request: AskUserRequest,
        question: tables.Question,
        user: tables.User,
        case_id: str,
    ) -> AskUserReply:
        labels = await self._labels(question, user.language)
        future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        self._waiting[question.id] = future
        try:
            try:
                await send_template(
                    self._whatsapp,
                    user,
                    template_id(request.template),
                    {
                        "options": _numbered(labels, user.language or "en"),
                        "default": request.default_option,
                        "seconds": request.timeout_s,
                    },
                    values_en={
                        "options": _numbered(request.options_en, "en"),
                        "default": request.default_option,
                        "seconds": request.timeout_s,
                    },
                    case_id=case_id,
                    question_id=question.id,
                )
            except WhatsAppSendError as exc:
                logger.error("ask_user %s not sent: %s", question.id, exc)
                return await self._time_out(question, case_id, future, labels)
            await self._event(
                EventType.CALL_ASK_USER,
                question,
                case_id,
                "Asked the user to choose a menu option",
                options_en=request.options_en,
                default_option=request.default_option,
                timeout_s=request.timeout_s,
            )
            try:
                choice = await asyncio.wait_for(
                    asyncio.shield(future), request.timeout_s
                )
            except TimeoutError:
                return await self._time_out(question, case_id, future, labels)
        finally:
            self._waiting.pop(question.id, None)
        return await self._answered(question, case_id, choice)

    async def question_for_reply(self, user_id: UserId) -> tables.Question | None:
        """The question an inbound text might answer: the open one, or else one that
        timed out within the late-reply window."""
        question = await reads.get_open_question(user_id)
        if question is not None:
            return question
        timed_out = self._timed_out.get(user_id)
        if timed_out is None:
            return None
        if time.monotonic() - timed_out.at >= self._late_reply_window_s:
            del self._timed_out[user_id]
            return None
        return timed_out.question

    async def handle_reply(
        self,
        user: tables.User,
        question: tables.Question,
        text: str,
        *,
        reprompt: bool = True,
    ) -> bool:
        """Route a bare-number reply to `question`. Returns False if the text isn't
        a number and should go on to normal routing: always for a question already
        timed out, and for an open one unless `reprompt` (no orchestrator turn to
        read the text), which asks again for a number instead."""
        choice = parse_choice(text, len(question.options_en))
        if choice is None:
            if question.status != QuestionStatus.OPEN or not reprompt:
                return False
            await send_template(
                self._whatsapp,
                user,
                "ask_user.reprompt",
                {"count": len(question.options_en)},
                question_id=question.id,
            )
            return True
        if question.status == QuestionStatus.OPEN:
            await self.answer(user, question, choice)
        else:
            await self._late_reply(user, question, choice)
        return True

    async def answer(
        self, user: tables.User, question: tables.Question, choice: int
    ) -> bool:
        """Answer the user's open `question` with `choice` (1-based), for the pipe
        or the orchestrator turn's answer tool. Returns False if the timeout closed
        it first; the user is then told which option was taken (C24)."""
        if question.user_id != user.id:
            raise ValueError(f"question {question.id} isn't this user's")
        if not 1 <= choice <= len(question.options_en):
            raise ValueError(f"choice {choice} out of range for {question.id}")
        answered = await writes.answer_question(question.id, choice)
        if answered is not None:
            future = self._waiting.get(question.id)
            if future is not None and not future.done():
                future.set_result(choice)
            return True
        # The timeout closed the question between our read and our answer.
        await self._late_reply(user, question, choice)
        return False

    async def _answered(
        self, question: tables.Question, case_id: str, choice: int
    ) -> AskUserReply:
        await self._event(
            EventType.CALL_ASK_USER_ANSWERED,
            question,
            case_id,
            f"The user chose option {choice}",
            choice=choice,
        )
        return AskUserReply(question_id=question.id, choice=choice)

    async def _time_out(
        self,
        question: tables.Question,
        case_id: str,
        future: asyncio.Future[int],
        labels: list[str],
    ) -> AskUserReply:
        if await writes.time_out_question(question.id) is None:
            # The user answered first; the reply handler is about to resolve us.
            try:
                choice = await asyncio.wait_for(future, _RACE_GRACE_S)
            except TimeoutError:
                logger.error(
                    "ask_user %s answered but never resolved; using the default",
                    question.id,
                )
            else:
                return await self._answered(question, case_id, choice)
        if question.id not in self._late_replied:
            self._timed_out[question.user_id] = _TimedOut(
                question, time.monotonic(), labels
            )
        await self._event(
            EventType.CALL_ASK_USER_TIMEOUT,
            question,
            case_id,
            f"No answer in time; took the default, option {question.default_option}",
            default_option=question.default_option,
        )
        return AskUserReply(question_id=question.id, choice=question.default_option)

    async def _cancelled(self, question: tables.Question) -> None:
        """The phone agent stopped waiting (a new menu prompt, hold, a person, or a
        hang-up). Close the row so the user's next reply goes to normal routing. No
        message, no timeout event, no late-reply window: nothing was decided for
        the user."""
        try:
            closed = await writes.time_out_question(question.id)
        except Exception:
            # Any failure: the caller's cancellation must still propagate.
            logger.exception(
                "ask_user %s cancelled but not closed call_id=%s",
                question.id,
                question.call_id,
            )
            return
        if closed is not None:
            logger.info(
                "ask_user %s cancelled; question closed call_id=%s",
                question.id,
                question.call_id,
            )

    async def _late_reply(
        self, user: tables.User, question: tables.Question, choice: int
    ) -> None:
        """C24: say what the agent already chose and why, once per question."""
        self._late_replied.add(question.id)
        timed_out = self._timed_out.pop(user.id, None)
        labels = question.options_en
        if timed_out is not None and timed_out.question.id == question.id:
            labels = timed_out.labels
        await writes.record_late_reply(question.id)
        default = question.default_option
        await send_template(
            self._whatsapp,
            user,
            "ask_user.late_reply",
            {"default": default, "default_option": labels[default - 1]},
            values_en={
                "default": default,
                "default_option": question.options_en[default - 1],
            },
            question_id=question.id,
        )
        call = await reads.get_call(question.call_id)
        await self._event(
            EventType.CALL_ASK_USER_LATE_REPLY,
            question,
            call.case_id if call else None,
            f"The user answered option {choice} after the timeout; option "
            f"{default} was already taken",
            choice=choice,
            default_option=default,
        )

    async def _labels(
        self, question: tables.Question, language: LanguageCode | None
    ) -> list[str]:
        """The option labels in the user's language, or in English if translation
        isn't set up, fails, or takes longer than `labels_timeout_s`."""
        if self._translate_labels is None or language in (None, "en"):
            return question.options_en
        try:
            labels = await asyncio.wait_for(
                self._translate_labels(question.options_en, language),
                self._labels_timeout_s,
            )
        except TimeoutError:
            logger.warning("ask_user %s options not translated in time", question.id)
            return question.options_en
        return labels if labels is not None else question.options_en

    async def _event(
        self,
        event_type: EventType,
        question: tables.Question,
        case_id: str | None,
        summary_en: str,
        **data: Any,
    ) -> None:
        await append_event(
            Event(
                event_id=new_id("event"),
                created_at=utcnow(),
                type=event_type,
                source=Component.RELAY,
                user_id=question.user_id,
                case_id=case_id,
                call_id=question.call_id,
                summary_en=summary_en,
                data={"question_id": question.id, **data},
            )
        )


def _numbered(options: list[str], language: LanguageCode) -> str:
    """One option per line, numbered in the language's digits."""
    return "\n".join(
        f"{local_digits(str(i), language)} {option}"
        for i, option in enumerate(options, start=1)
    )


async def _user_for_call(call_id: str) -> tuple[tables.User, str]:
    call = await reads.get_call(call_id)
    if call is None:
        raise NotFound(f"calls {call_id} not found")
    case = await reads.get_case(call.case_id)
    if case is None:
        raise NotFound(f"cases {call.case_id} not found")
    user = await reads.get_user(case.user_id)
    if user is None:
        raise NotFound(f"users {case.user_id} not found")
    return user, case.id


@lru_cache
def get_ask_user() -> AskUser:
    """The one instance the phone agent and the inbound pipe share."""
    translator = get_translator()
    return AskUser(
        get_whatsapp(),
        translate_labels=translator.labels_from_english if translator else None,
    )


async def ask_user(request: AskUserRequest) -> AskUserReply:
    """What the phone agent calls (P1)."""
    return await get_ask_user().ask(request)
