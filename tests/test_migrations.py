from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from bot.db.models import Base

ROOT = Path(__file__).resolve().parent.parent


def test_migrations_produce_the_schema_models_describe(tmp_path) -> None:
    """`alembic upgrade head` must match the models exactly.

    Catches the easy mistake of editing a model and forgetting the migration —
    which would otherwise only surface on a deploy against a real volume.
    """
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"models and migrations have drifted: {diff}"
