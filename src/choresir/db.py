"""Async database engine and session factory for SQLite."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from choresir.config import Settings


def _set_sqlite_pragmas(dbapi_conn, connection_record) -> None:  # noqa: ANN001 — raw DBAPI types
    """Set SQLite pragmas on every new connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an async SQLAlchemy engine with SQLite pragmas configured."""
    engine = create_async_engine(settings.database_url)
    event.listens_for(engine.sync_engine, "connect")(_set_sqlite_pragmas)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """Create an async session factory with expire_on_commit disabled."""
    return async_sessionmaker(engine, expire_on_commit=False)
