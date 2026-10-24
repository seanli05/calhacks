"""Writes owned by the memory writer: profile, facts."""

from typing import Any

from app.contracts import FactSource, FactStatus, Sensitivity
from app.contracts.common import FactId, UserId
from app.db import tables
from app.db.engine import session
from app.db.errors import must_get
from app.db.tables import utcnow


async def upsert_profile(user_id: UserId, fields: dict[str, Any]) -> tables.Profile:
    """Merge `fields` into the profile (keys not given are kept)."""
    async with session() as db:
        profile = await db.get(tables.Profile, user_id)
        if profile is None:
            profile = tables.Profile(user_id=user_id, fields=dict(fields))
            db.add(profile)
        else:
            profile.fields = {**profile.fields, **fields}
            profile.updated_at = utcnow()
        await db.commit()
        return profile


async def add_fact(
    user_id: UserId,
    fact: str,
    category: str,
    source: FactSource,
    sensitivity: Sensitivity,
    status: FactStatus,
    source_ref: str | None = None,
    supersedes: FactId | None = None,
) -> tables.Fact:
    """Immigration facts must arrive as `pending_consent` (C15, C25); that rule is
    the memory writer's to apply, not this helper's."""
    row = tables.Fact(
        user_id=user_id,
        fact=fact,
        category=category,
        source=source,
        sensitivity=sensitivity,
        status=status,
        source_ref=source_ref,
        supersedes=supersedes,
    )
    async with session() as db:
        db.add(row)
        await db.commit()
        return row


async def set_fact_status(fact_id: FactId, status: FactStatus) -> tables.Fact:
    async with session() as db:
        fact = await must_get(db, tables.Fact, fact_id)
        fact.status = status
        await db.commit()
        return fact
