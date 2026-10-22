"""Database session management for the AI SaaS Platform.

Provides an async session factory and the ``get_async_session`` dependency used
by routes. The engine is created once during application startup (in ``main.py``)
and shared across requests. Transactions are per-request; the caller is
responsible for committing or rolling back.

Typical use in a route::

    async def my_route(
        session: AsyncSession = Depends(get_async_session),
    ) -> ...:
        result = await session.execute(select(User).where(User.id == user_id))
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

#: Global engine and session maker instances (set during app startup).
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, echo: bool = False) -> None:
    """Initialize the global async engine and session maker.

    Must be called during application startup (inside the lifespan).

    Args:
        url: The database URL (e.g. ``sqlite:///./app.db`` or a PostgreSQL URL).
        echo: If true, SQL statements are logged to stdout (useful for debug).
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(to_async_url(url), echo=echo)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def to_async_url(url: str) -> str:
    """Return the async driver form of a database URL.

    SQLAlchemy's async engine cannot use a synchronous driver. A plain
    ``sqlite:///`` URL would fail at the first query with an obscure driver
    error, so the async SQLite driver is selected here instead. The same goes
    for PostgreSQL: the application talks to it through ``asyncpg``.

    The Alembic environment uses this function too, so a migration runs
    against the same driver and the same database as the application.

    Args:
        url: The configured database URL.

    Returns:
        The URL with an async-compatible driver.
    """
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def shutdown_engine() -> None:
    """Dispose of the async engine. Call during application shutdown.

    The disposal is awaited rather than driven through ``run_until_complete``,
    because the shutdown runs inside the event loop that owns the engine.

    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session bound to the global engine.

    This is the ``Depends`` dependency the routers use. It yields a session
    rather than the session maker: a route that asked for a session and
    received a factory would fail at the first query.

    Raises:
        RuntimeError: If the engine has not been initialized.
    """
    if _sessionmaker is None:
        raise RuntimeError("Database not initialized. Call init_engine() during startup.")
    async with _sessionmaker() as session:
        yield session


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a single async session bound to the global engine.

    Use this as a fastAPI ``Depends`` dependency when you want the framework
    to manage the session lifecycle (commit on success, rollback on exception).

    Yields:
        An ``AsyncSession`` instance.
    """
    if _sessionmaker is None:
        raise RuntimeError("Database not initialized. Call init_engine() during startup.")
    async with _sessionmaker() as session:
        yield session
