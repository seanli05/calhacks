"""Asking before saving (C15, Goal 7.5), the orchestrator's half: after a turn, ask
the user once about the facts the memory writer is holding as `pending_consent`, in
one numbered message. The answer goes to the memory writer (`app.memory.consent`),
which owns the `facts` table; the orchestrator writes none of it.

Each fact is asked about once per process. A reply that isn't 1/2 (or yes/no)
closes the question and goes to the turn; the facts stay pending, and the dashboard
shows them as waiting for the user's OK. The open question lives in memory, one per
user; a restart forgets it.
"""

import logging

from app.contracts import FactStatus
from app.contracts.common import FactId, UserId
from app.db import reads, tables
from app.memory import consent as memory_consent
from app.relay.outbound import send_template
from app.relay.whatsapp import WhatsApp
from app.translation.translate import Translator, localize

logger = logging.getLogger(__name__)

MAX_FACTS_ASKED = 5


class FactConsent:
    def __init__(self, whatsapp: WhatsApp, translator: Translator | None) -> None:
        self._whatsapp = whatsapp
        self._translator = translator
        self._pending: dict[UserId, list[FactId]] = {}
        self._asked: set[FactId] = set()

    def pending(self, user_id: UserId) -> list[FactId] | None:
        return self._pending.get(user_id)

    def drop(self, user_id: UserId) -> None:
        """The user answered something else; the facts stay pending."""
        self._pending.pop(user_id, None)

    async def ask(self, user: tables.User) -> bool:
        """Ask about pending facts not asked about yet. Returns True if asked."""
        if user.id in self._pending:
            return False
        facts = [
            fact
            for fact in await reads.list_facts(user.id, [FactStatus.PENDING_CONSENT])
            if fact.id not in self._asked
        ][:MAX_FACTS_ASKED]
        if not facts:
            return False
        facts_en = "\n".join(f"• {fact.fact}" for fact in facts)
        facts_text = await localize(self._translator, facts_en, user.language or "en")
        if facts_text is None:
            # Never English instead (rule 6); a later turn tries again.
            logger.warning("Fact consent not asked user_id=%s: no translation", user.id)
            return False
        await send_template(
            self._whatsapp,
            user,
            "memory.ask_save",
            {"facts": facts_text},
            values_en={"facts": facts_en},
        )
        fact_ids = [fact.id for fact in facts]
        self._asked.update(fact_ids)
        self._pending[user.id] = fact_ids
        logger.info("Fact consent asked user_id=%s facts=%d", user.id, len(fact_ids))
        return True

    async def answer(self, user: tables.User, choice: int) -> None:
        """The user's 1 (save) or 2 (don't) to the open question."""
        fact_ids = self._pending.pop(user.id, None)
        if fact_ids is None:
            logger.error(
                "Fact consent answer with no open question user_id=%s", user.id
            )
            return
        if choice == 1:
            await memory_consent.confirm_facts(user.id, fact_ids)
            await send_template(self._whatsapp, user, "memory.saved")
        else:
            await memory_consent.decline_facts(user.id, fact_ids)
            await send_template(self._whatsapp, user, "memory.not_saved")
