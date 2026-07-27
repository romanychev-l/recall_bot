"""Async engine and session factory."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def to_sync_url(url: str) -> str:
    """Async-driver URL → its sync equivalent.

    Alembic runs migrations synchronously, so it needs the plain driver.
    """
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


def _ensure_parent_dir(url: str) -> None:
    """Create the directory holding the SQLite file if it does not exist.

    On a fresh Railway volume the mount point exists but nested paths may not.
    """
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return
    raw_path = url[len(prefix) :]
    if not raw_path or raw_path.startswith(":memory:"):
        return
    parent = Path(raw_path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def build_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    _ensure_parent_dir(url)
    engine = create_async_engine(url, echo=echo, pool_pre_ping=True)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            # WAL lets reads proceed during a write and is the right mode for a
            # long-running single-process app.
            cursor.execute("PRAGMA journal_mode=WAL")
            # SQLite ignores FK constraints unless asked to enforce them.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            # Wait instead of failing instantly if the file is briefly locked.
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    # expire_on_commit=False: repos read attributes off rows after commit.
    return async_sessionmaker(engine, expire_on_commit=False)


async def check_connection(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("db_connected dialect=%s", engine.dialect.name)
