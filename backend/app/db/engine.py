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
    # No pre_ping: it costs a round trip on every checkout (~130 ms to us-east-2).
    # Neon closes connections when it suspends after 5 idle minutes, so recycling
    # at 4 minutes means a pooled connection is never older than the compute.
    # 20 connections so the dashboard's concurrent reads don't queue for the pool.
    return create_async_engine(
        url, pool_size=20, pool_recycle=240, connect_args=connect_args
    )


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as db:
        yield db


async def ping() -> str:
    """Round-trip to the database; returns the server version string."""
    async with get_engine().connect() as conn:
        return (await conn.execute(text("select version()"))).scalar_one()
