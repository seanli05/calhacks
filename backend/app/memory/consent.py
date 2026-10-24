"""Asking before saving (C15), the memory writer's half: the orchestrator asks the
user about facts held as `pending_consent` and passes the answer here. Yes makes
them active; no deletes them.

Only facts still pending for this user are touched: one may have been deleted from
the dashboard while the question was open.
"""

import logging
from collections.abc import Sequence

from app.contracts import EventType, FactStatus
from app.contracts.common import FactId, UserId
from app.db import reads
from app.db.writes import memory as writes
from app.memory.events import fact_event

logger = logging.getLogger(__name__)


async def confirm_facts(user_id: UserId, fact_ids: Sequence[FactId]) -> list[FactId]:
    """The user said yes: the facts become active. Returns the ones changed."""
    confirmed = await _still_pending(user_id, fact_ids)
    for fact_id in confirmed:
        await writes.set_fact_status(fact_id, FactStatus.ACTIVE)
        await fact_event(
            EventType.MEMORY_FACT_SAVED,
            user_id,
            fact_id,
            "Saved a fact after the user said yes",
        )
    logger.info("Facts confirmed user_id=%s count=%d", user_id, len(confirmed))
    return confirmed


async def decline_facts(user_id: UserId, fact_ids: Sequence[FactId]) -> list[FactId]:
    """The user said no: the facts are deleted. Returns the ones deleted.

    No event: `fact.deleted` would wrongly say the user deleted it (C26). The
    fact's `memory.fact_pending_consent` line falls back to the feed's generic
    text, with no date."""
    declined = await _still_pending(user_id, fact_ids)
    for fact_id in declined:
        await writes.delete_fact(fact_id)
    logger.info("Facts declined user_id=%s count=%d", user_id, len(declined))
    return declined


async def _still_pending(user_id: UserId, fact_ids: Sequence[FactId]) -> list[FactId]:
    pending = {
        f.id for f in await reads.list_facts(user_id, [FactStatus.PENDING_CONSENT])
    }
    return [fact_id for fact_id in fact_ids if fact_id in pending]
