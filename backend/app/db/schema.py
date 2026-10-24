"""Create and drop every table. No migrations: startup creates missing tables,
and `python -m app.db.reset` rebuilds them (data-layer-schema.md → Conventions)."""

from sqlmodel import SQLModel

from app.db import tables  # noqa: F401  (registers every table on the metadata)
from app.db.engine import get_engine


async def create_all() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_all() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
