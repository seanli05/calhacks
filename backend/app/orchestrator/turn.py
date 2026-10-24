"""The orchestrator's Claude turn (Goal 4.1, 4.5): answers free text from the user.

English inside (rule 6): the turn reads English history (`body_en`) and writes an
English reply, which `Translator.from_english` turns into the user's language at the
edge. If the model or the translation fails, the user gets a relay template saying
so, never an untranslated English reply.

The pipe runs this outside its per-number routing lock (concern 8).
"""

import asyncio
import logging

import anthropic
from anthropic import AsyncAnthropic
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import Component, FactSource, MemoryWriteJob, MessageDirection
from app.contracts.common import MessageId
from app.db import jobs, reads, tables
from app.orchestrator.consent import ConsentGate
from app.orchestrator.prompts import ORCHESTRATOR_SYSTEM
from app.orchestrator.research_questions import ResearchQuestions
from app.orchestrator.tools import CaseTools, build_tools
from app.relay.outbound import send_template, send_text
from app.relay.whatsapp import WhatsApp
from app.translation.translate import Translator

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 30.0
TURN_TIMEOUT_S = 60.0
MAX_ITERATIONS = 6
HISTORY_MESSAGES = 20

UNAVAILABLE = "orchestrator.unavailable"


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
    ) -> None:
        self._client = client
        self._model = model
        self._whatsapp = whatsapp
        self._translator = translator
        self._consent = consent
        self._turn_timeout_s = turn_timeout_s
        self._research_questions = research_questions

    async def run(
        self,
        user: tables.User,
        message_id: MessageId,
        *,
        same_or_new_pending: bool = False,
        consent_pending: bool = False,
    ) -> None:
        """Reply to the user's latest message (`message_id`), which the pipe has
        already logged; then queue the memory writer on it (Goal 6.5)."""
        await self._reply(
            user,
            same_or_new_pending=same_or_new_pending,
            consent_pending=consent_pending,
        )
        await _queue_memory_write(user, message_id)

    async def _reply(
        self, user: tables.User, *, same_or_new_pending: bool, consent_pending: bool
    ) -> None:
        tools = CaseTools(user, self._whatsapp, self._consent, self._research_questions)
        context = await build_context(
            user,
            same_or_new_pending=same_or_new_pending,
            consent_pending=consent_pending,
        )
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
            await send_template(self._whatsapp, user, UNAVAILABLE)
            return
        language = user.language or "en"
        body = await self._translator.from_english(reply_en, language)
        if body is None:
            await send_template(self._whatsapp, user, UNAVAILABLE)
            return
        await send_text(self._whatsapp, user, body, body_en=reply_en)

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
    user: tables.User, *, same_or_new_pending: bool, consent_pending: bool = False
) -> str:
    """The turn's user message: recent conversation in English, open cases, and any
    pending question. Built from stored rows only; refs are never resolved."""
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
    ]
    if same_or_new_pending:
        parts.append(
            "<pending>We asked whether the user's latest photo is another page of "
            "the same letter (1) or a new letter (2), and they haven't answered with "
            "a number. Answer their message, then remind them to reply 1 or 2."
            "</pending>"
        )
    if consent_pending:
        parts.append(
            "<pending>We asked whether we may call USCIS for the user (1 yes, 2 no), "
            "and they haven't answered with a number. Answer their message, then "
            "remind them to reply 1 if they want the call or 2 if not. A yes in "
            "words isn't enough: the call starts only from their reply.</pending>"
        )
    parts.append("Reply to the user's latest message.")
    return "\n".join(parts)


def _history_line(message: tables.Message) -> str:
    speaker = "User" if message.direction == MessageDirection.IN else "Assistant"
    text = message.body_en or f"[in {message.language}] {message.body_original}"
    if message.media_ids:
        text = f"(sent {len(message.media_ids)} photo(s)) {text}".strip()
    return f"{speaker}: {text}"
