"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from meridian.config import get_settings
from meridian.persistence.models import Base

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _init() -> None:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables and apply additive column migrations idempotently."""
    _init()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive migrations: ADD COLUMN IF NOT EXISTS is idempotent in Postgres.
        for stmt in [
            "ALTER TABLE trace_spans ADD COLUMN IF NOT EXISTS turn_num INTEGER DEFAULT 0",
            "ALTER TABLE trace_spans ADD COLUMN IF NOT EXISTS attributes JSONB DEFAULT '{}'",
        ]:
            await conn.execute(__import__("sqlalchemy").text(stmt))


def session_factory() -> async_sessionmaker[AsyncSession]:
    _init()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
