"""SQLAlchemy engine and session factory for the application's own tables."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ragdoctor.settings import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None) -> AsyncEngine:
    """Create the process-wide engine (idempotent)."""
    global _engine, _factory
    if _engine is None:
        _engine = create_async_engine(url or get_settings().sqlalchemy_url, pool_pre_ping=True)
        _factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    """Close every pooled connection."""
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine, _factory = None, None


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory, creating the engine on first use."""
    init_engine()
    assert _factory is not None
    return _factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with session_factory()() as session:
        yield session
