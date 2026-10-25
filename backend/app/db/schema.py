"""Create and drop every table. No migrations: startup creates missing tables,
and `python -m app.db.reset` rebuilds them (data-layer-schema.md → Conventions)."""

from collections.abc import Collection

from sqlalchemy import text
from sqlmodel import SQLModel

from app.db import tables  # noqa: F401  (registers every table on the metadata)
from app.db.engine import get_engine


async def create_all() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def clear_data(keep: Collection[str]) -> list[str]:
    """Empty every table except `keep`, in one statement. Returns the emptied
    tables. A kept table must not point at an emptied one; `users` and `glossary`
    point at nothing."""
    names = [t.name for t in SQLModel.metadata.sorted_tables if t.name not in keep]
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(f'"{n}"' for n in names)}"))
    return names


async def drop_all() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
