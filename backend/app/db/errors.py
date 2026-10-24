"""Errors the DB helpers raise, plus the shared get-or-raise."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel


class NotFound(LookupError):
    pass


class UnverifiedNumber(RuntimeError):
    """The case has no verified official number, so nothing may be dialed (rule 2)."""


async def must_get[Row: SQLModel](db: AsyncSession, model: type[Row], key: Any) -> Row:
    row = await db.get(model, key)
    if row is None:
        raise NotFound(f"{model.__tablename__} {key} not found")
    return row
