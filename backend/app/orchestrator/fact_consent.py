"""Asking before saving (C15, Goal 7.5), the orchestrator's half: at the end of a
turn's reply, ask the user once about the facts the memory writer is holding as
`pending_consent`, as a numbered question in the same message (pacing: one message,
not a reply and then a question). The answer goes to the memory writer
(`app.memory.consent`), which owns the `facts` table; the orchestrator writes none of
it.

Each fact is asked about once per process. A 1/2 (or yes/no) is answered in code;
other text goes to the turn, which may answer it (`answer_save_facts`). If it
doesn't, the question stays open for one more message (the user may have asked what
it means), then closes unanswered; the facts stay pending, and the dashboard shows
them as waiting for the user's OK. The open question lives in memory, one per
user; a restart forgets it.
"""

import logging
from dataclasses import dataclass

from app.contracts import FactStatus
from app.contracts.common import FactId, UserId
from app.db import reads, tables
from app.memory import consent as memory_consent
from app.relay.outbound import send_template
from app.relay.templates import render
from app.relay.whatsapp import WhatsApp
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

MAX_FACTS_ASKED = 5
# Turns that may go by without an answer before the question closes: one, so the
# user can ask what it means and then answer. Closing frees the slot for other
# numbered questions (the call question waits while this one is open).
UNANSWERED_TURNS = 1


@dataclass(frozen=True)
class SaveQuestion:
    """The question as it goes out: in the user's language and in English."""

    text: str
    text_en: str
    fact_ids: list[FactId]


class FactConsent:
    def __init__(self, whatsapp: WhatsApp, translator: Translator | None) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._pending: dict[UserId, list[FactId]] = {}
        self._asked: set[FactId] = set()
        self._unanswered: dict[UserId, int] = {}

    def pending(self, user_id: UserId) -> list[FactId] | None:
        return self._pending.get(user_id)

    def drop(self, user_id: UserId) -> None:
        """Close the question unanswered; the facts stay pending."""
        self._pending.pop(user_id, None)
        self._unanswered.pop(user_id, None)

    def unanswered(self, user_id: UserId) -> None:
        """A turn went by without an answer: keep the question open for the next
        message, up to UNANSWERED_TURNS, then close it."""
        count = self._unanswered.get(user_id, 0) + 1
        if count > UNANSWERED_TURNS:
            self.drop(user_id)
        else:
            self._unanswered[user_id] = count

    async def question(self, user: tables.User) -> SaveQuestion | None:
        """The question about pending facts not asked about yet, or None. Nothing is
        sent: call `asked` once it went out."""
        if user.id in self._pending:
            return None
        facts = [
            fact
            for fact in await reads.list_facts(user.id, [FactStatus.PENDING_CONSENT])
            if fact.id not in self._asked
        ][:MAX_FACTS_ASKED]
        if not facts:
            return None
        language = user.language or "en"
        facts_en = "\n".join(f"• {fact.fact}" for fact in facts)
        facts_text = await localize(self._translator, facts_en, language)
        if facts_text is None:
            # Never English instead (rule 6); a later turn tries again.
            logger.warning("Fact consent not asked user_id=%s: no translation", user.id)
            return None
        return SaveQuestion(
            text=render("memory.ask_save", language, facts=facts_text),
            text_en=render("memory.ask_save", "en", facts=facts_en),
            fact_ids=[fact.id for fact in facts],
        )

    def asked(self, user_id: UserId, question: SaveQuestion) -> None:
        """`question` went out: its facts are never asked about again, and the
        user's next 1 or 2 answers it."""
        self._asked.update(question.fact_ids)
        self._pending[user_id] = question.fact_ids
        logger.info(
            "Fact consent asked user_id=%s facts=%d", user_id, len(question.fact_ids)
        )

    async def answer(
        self, user: tables.User, choice: int, *, confirm: bool = True
    ) -> str | None:
        """The user's 1 (save) or 2 (don't) to the open question. Returns the
        template that confirms it, sent only with `confirm` (the turn's reply says
        it instead); None if no question was open."""
        fact_ids = self._pending.pop(user.id, None)
        self._unanswered.pop(user.id, None)
        if fact_ids is None:
            logger.error(
                "Fact consent answer with no open question user_id=%s", user.id
            )
            return None
        if choice == 1:
            await memory_consent.confirm_facts(user.id, fact_ids)
            template = "memory.saved"
        else:
            await memory_consent.decline_facts(user.id, fact_ids)
            template = "memory.not_saved"
        if confirm:
            await send_template(self._whatsapp, user, template)
        return template
