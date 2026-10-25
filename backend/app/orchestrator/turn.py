"""The orchestrator's Claude turn (Goal 4.1, 4.5): answers free text from the user.

English inside (rule 6): the turn reads English history (`body_en`) and writes an
English reply, which `Translator.from_english` turns into the user's language at the
edge. If the model or the translation fails, the user gets a relay template saying
so, never an untranslated English reply.

Every message the pipe doesn't answer in code comes here, including while a
numbered question is open: the turn sees what's open (`<open_questions>`) and can
answer it through guarded tools, then reply to the rest of the message. When it
ends with a plain reply at a quiet moment, "may I save this?" (C15) goes at the end
of that same message.

The pipe runs this outside its per-number routing lock (concern 8).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import anthropic
from anthropic import AsyncAnthropic
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import Component, FactSource, MemoryWriteJob, MessageDirection
from app.contracts.common import MessageId, UserId
from app.db import jobs, reads, tables
from app.orchestrator.consent import ConsentGate
from app.orchestrator.open_questions import OpenQuestions
from app.orchestrator.prompts import ORCHESTRATOR_SYSTEM
from app.orchestrator.research_questions import ResearchQuestions
from app.orchestrator.tools import CaseTools, build_tools
from app.relay.outbound import send_template, send_text
from app.relay.whatsapp import WhatsApp
from app.translation.translate import Translator

if TYPE_CHECKING:
    from app.orchestrator.fact_consent import FactConsent
    from app.relay.ask_user import AskUser

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 30.0
TURN_TIMEOUT_S = 60.0
MAX_ITERATIONS = 6
HISTORY_MESSAGES = 20

UNAVAILABLE = "orchestrator.unavailable"

# The pipe's check that "may I save this?" won't crowd anything (C15, pacing).
QuietMoment = Callable[[UserId], Awaitable[bool]]


class OrchestratorTurn:
    def __init__(
        self,
        client: AsyncAnthropic,
        model: str,
        whatsapp: WhatsApp,
        translator: Translator,
        consent: ConsentGate | None = None,
        turn_timeout_s: float = TURN_TIMEOUT_S,
        research_questions: ResearchQuestions | None = None,
        *,
        ask_user: "AskUser | None" = None,
        fact_consent: "FactConsent | None" = None,
    ) -> None:
        self._client = client
        self._model = model
        self._whatsapp = whatsapp
        self._translator = translator
        self._consent = consent
        self._turn_timeout_s = turn_timeout_s
        self._research_questions = research_questions
        self._ask_user = ask_user
        self._fact_consent = fact_consent

    async def run(
        self,
        user: tables.User,
        message_id: MessageId,
        *,
        open_questions: OpenQuestions | None = None,
        quiet_moment: QuietMoment | None = None,
    ) -> None:
        """Reply to the user's latest message (`message_id`), which the pipe has
        already logged; then queue the memory writer on it (Goal 6.5).
        `open_questions` is what the user hasn't answered yet; with `quiet_moment`,
        a plain reply may end with "may I save this?"."""
        await self._reply(user, open_questions or OpenQuestions(), quiet_moment)
        await _queue_memory_write(user, message_id)

    async def _reply(
        self,
        user: tables.User,
        open_questions: OpenQuestions,
        quiet_moment: QuietMoment | None,
    ) -> None:
        tools = CaseTools(
            user,
            self._whatsapp,
            self._consent,
            self._research_questions,
            ask_user=self._ask_user,
            fact_consent=self._fact_consent,
            open_questions=open_questions,
        )
        context = await build_context(user, open_questions)
        try:
            async with asyncio.timeout(self._turn_timeout_s):
                reply_en = await self._ask_claude(tools, context)
        except anthropic.APIError as exc:
            logger.error("Turn failed user_id=%s: %s", user.id, type(exc).__name__)
            reply_en = None
        except TimeoutError:
            logger.error("Turn timed out user_id=%s", user.id)
            reply_en = None
        user = tools.user
        if tools.language_switched or tools.consent_requested:
            return  # a template already answered
        if reply_en is None:
            # After an answer's own confirmation, no text means nothing more to say.
            if not tools.answer_confirmed:
                await send_template(self._whatsapp, user, UNAVAILABLE)
            return
        language = user.language or "en"
        body = await self._translator.from_english(reply_en, language)
        if body is None:
            await send_template(self._whatsapp, user, UNAVAILABLE)
            return
        save = None
        if (
            self._fact_consent is not None
            and quiet_moment is not None
            and await quiet_moment(user.id)
        ):
            save = await self._fact_consent.question(user)
        if save is not None:
            body = f"{body}\n\n{save.text}"
            reply_en = f"{reply_en}\n\n{save.text_en}"
        await send_text(self._whatsapp, user, body, body_en=reply_en)
        if save is not None and self._fact_consent is not None:
            self._fact_consent.asked(user.id, save)

    async def _ask_claude(self, tools: CaseTools, context: str) -> str | None:
        runner = self._client.beta.messages.tool_runner(
            model=self._model,
            max_tokens=16000,
            system=[
                {
                    "type": "text",
                    "text": ORCHESTRATOR_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=build_tools(tools),
            messages=[{"role": "user", "content": context}],
            max_iterations=MAX_ITERATIONS,
            output_config={"effort": "low"},
            timeout=REQUEST_TIMEOUT_S,
        )
        last = None
        async for message in runner:
            last = message
        if last is None:
            return None
        if last.stop_reason == "refusal":
            logger.warning("Turn refused user_id=%s", tools.user.id)
            return None
        text = "".join(block.text for block in last.content if block.type == "text")
        return text.strip() or None


async def _queue_memory_write(user: tables.User, message_id: MessageId) -> None:
    """Plan.md → Jobs: the memory writer runs after each orchestrator reply, on the
    user's message. It extracts and filters the facts itself (C34)."""
    try:
        await jobs.enqueue(
            MemoryWriteJob(
                user_id=user.id,
                source=FactSource.USER_SAID,
                source_ref=message_id,
                proposed_facts=[],
            ),
            Component.ORCHESTRATOR,
            user.id,
        )
    except SQLAlchemyError:
        logger.exception("Memory write not queued user_id=%s", user.id)


async def build_context(
    user: tables.User, open_questions: OpenQuestions | None = None
) -> str:
    """The turn's user message: recent conversation in English, open cases, and the
    questions waiting for the user's answer. Built from stored rows only; refs are
    never resolved."""
    messages = (await reads.list_messages(user.id))[-HISTORY_MESSAGES:]
    lines = [_history_line(message) for message in messages]
    cases = [
        f"- {case.id}: {case.doc_type or 'letter being read'}"
        f" (opened {case.created_at.date().isoformat()})"
        for case in await reads.list_active_cases(user.id)
    ]
    parts = [
        "<conversation>",
        *lines,
        "</conversation>",
        "<open_cases>",
        *(cases or ["(none)"]),
        "</open_cases>",
        *(open_questions or OpenQuestions()).render(),
        "Reply to the user's latest message.",
    ]
    return "\n".join(parts)


def _history_line(message: tables.Message) -> str:
    speaker = "User" if message.direction == MessageDirection.IN else "Assistant"
    text = message.body_en or f"[in {message.language}] {message.body_original}"
    if message.media_ids:
        text = f"(sent {len(message.media_ids)} photo(s)) {text}".strip()
    return f"{speaker}: {text}"
