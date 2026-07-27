"""Alembic environment.

Migrations run through a *sync* driver even though the app is async. Schema
changes gain nothing from concurrency, and staying sync means the bot can run
``upgrade head`` at startup (via a worker thread) without nesting one event loop
inside another.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the project importable when Alembic is invoked from the CLI.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.db.models import Base  # noqa: E402
from bot.db.session import to_sync_url  # noqa: E402

config = context.config

# Applying alembic.ini's logging config would clobber the app's: fileConfig
# drops the root level to WARNING and, by default, disables every logger created
# before it — which silences the whole bot when migrations run at startup. Only
# configure logging when Alembic runs standalone from the CLI.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL from alembic.ini, then the env, then the default path.

    Read straight from the environment rather than importing Settings, so
    ``alembic`` works without a bot TOKEN set.
    """
    url = config.get_main_option("sqlalchemy.url", None) or ""
    if not url:
        url = os.environ.get("DATABASE_URL") or ""
    if not url:
        url = f"sqlite+aiosqlite:///{os.environ.get('DB_PATH', 'recall_bot.db')}"
    return to_sync_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most things; batch mode rebuilds the table.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
