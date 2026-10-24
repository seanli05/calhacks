"""The async engine and session factory every DB helper uses."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    url = get_settings().async_database_url
    connect_args = {"timeout": 10}
    if "-pooler." in url:
        # Transaction pooler: prepared-statement caching breaks across connections.
        connect_args["statement_cache_size"] = 0
    # Neon suspends idle compute; pre_ping drops connections it closed meanwhile.
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as db:
        yield db


async def ping() -> str:
    """Round-trip to the database; returns the server version string."""
    async with get_engine().connect() as conn:
        return (await conn.execute(text("select version()"))).scalar_one()
