"""Bring the database schema up to date at startup."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from bot.db.session import to_sync_url

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = ROOT / "alembic.ini"


def _upgrade_sync(database_url: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    # Keep Alembic from reconfiguring the app's logging — see alembic/env.py.
    cfg.attributes["configure_logger"] = False
    # Set explicitly so it resolves the same regardless of working directory.
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", to_sync_url(database_url))
    command.upgrade(cfg, "head")


async def run_migrations(database_url: str) -> None:
    """Run ``alembic upgrade head`` in a worker thread.

    Alembic is synchronous; off-loading keeps it from blocking the event loop
    and avoids running a second loop inside the running one.
    """
    await asyncio.to_thread(_upgrade_sync, database_url)
    logger.info("migrations_applied")
