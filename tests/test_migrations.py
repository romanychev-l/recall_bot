from __future__ import annotations

from pathlib import Path
import sqlite3

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


def test_group_migration_preserves_existing_learning_data(tmp_path) -> None:
    path = tmp_path / "existing.db"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "87e122489a6a")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO users VALUES (42, 10, 10, '19:00', 'Europe/Moscow', 'ru', 1, 1, 2, 5, NULL, '2026-10-23')")
        connection.execute("INSERT INTO words VALUES (1, 'word', 'слово', 1, 'noun', '', 0)")
        connection.execute("INSERT INTO batches VALUES (1, 42, '2026-10-23')")
        connection.execute("INSERT INTO user_cards VALUES (1, 42, 1, 1, 1, '{}', '2026-10-24', 'review', 3, '2026-10-22', 0, NULL, '2026-10-22', '2026-10-23')")
        connection.execute("INSERT INTO review_log VALUES (1, 42, 1, 1, 'good', 'word', '2026-10-23')")
        tables = ("users", "words", "batches", "user_cards", "review_log")
        before = {name: connection.execute(f"SELECT * FROM {name}").fetchall() for name in tables}
    command.upgrade(cfg, "b731d4e1a920")
    with sqlite3.connect(path) as connection:
        assert {name: connection.execute(f"SELECT * FROM {name}").fetchall() for name in tables} == before
        assert connection.execute("SELECT count(*) FROM group_chats").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM group_members").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_pos_migration_preserves_progress_and_defaults_to_all(tmp_path) -> None:
    from bot.domain.parts_of_speech import ALL_POS

    path = tmp_path / "before_pos.db"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "b731d4e1a920")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO users VALUES (42, 10, 10, '19:00', 'Europe/Moscow', 'ru', 1, 1, 2, 5, NULL, '2026-10-23')")
        connection.execute("INSERT INTO words VALUES (1, 'word', 'слово', 1, 'noun', '', 0)")
        connection.execute("INSERT INTO batches VALUES (1, 42, '2026-10-23')")
        connection.execute("INSERT INTO user_cards VALUES (1, 42, 1, 1, 1, '{\"due\": \"2026-10-24\", \"stability\": 42}', '2026-10-24', 'review', 3, '2026-10-22', 1, '2026-10-24', '2026-10-22', '2026-10-23')")
        connection.execute("INSERT INTO review_log VALUES (1, 42, 1, 1, 'good', 'word', '2026-10-23')")
        tables = ("users", "words", "batches", "user_cards", "review_log", "group_chats", "group_members")
        columns = {table: ", ".join(row[1] for row in connection.execute(f"PRAGMA table_info({table})")) for table in tables}
        before = {table: connection.execute(f"SELECT {columns[table]} FROM {table}").fetchall() for table in tables}
    command.upgrade(cfg, "head")
    with sqlite3.connect(path) as connection:
        assert {table: connection.execute(f"SELECT {columns[table]} FROM {table}").fetchall() for table in tables} == before
        assert connection.execute("SELECT pos_filter FROM users").fetchone() == (ALL_POS,)
        assert connection.execute("SELECT study_pos_filter FROM user_cards").fetchone() == (ALL_POS,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
