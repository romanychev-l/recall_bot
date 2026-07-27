"""Load the dictionary CSV into the words table.

CSV columns (with header):
    english,translation,frequency_rank,pos,example,is_phrasal
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Word

logger = logging.getLogger(__name__)


def _coerce_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y")


def read_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Yield well-formed rows, skipping incomplete ones."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            english = (raw.get("english") or "").strip()
            translation = (raw.get("translation") or "").strip()
            rank_str = (raw.get("frequency_rank") or "").strip()
            if not english or not translation or not rank_str:
                continue
            try:
                rank = int(rank_str)
            except ValueError:
                continue
            yield {
                "english": english,
                "translation": translation,
                "frequency_rank": rank,
                "pos": (raw.get("pos") or "").strip(),
                "example": (raw.get("example") or "").strip(),
                "is_phrasal": _coerce_bool(raw.get("is_phrasal") or "false"),
            }


async def count_words(session_factory: async_sessionmaker) -> int:
    async with session_factory() as s:
        res = await s.execute(select(func.count()).select_from(Word.__table__))
        return int(res.scalar_one())


async def seed_from_csv(
    session_factory: async_sessionmaker, csv_path: Path
) -> tuple[int, int]:
    """Upsert words keyed by frequency_rank. Returns (inserted, updated).

    Uses plain inserts/updates rather than a dialect-specific ON CONFLICT, so it
    behaves the same on SQLite and Postgres.
    """
    # Last row wins if a CSV repeats a rank — the unique index would reject it.
    deduped = {row["frequency_rank"]: row for row in read_rows(csv_path)}
    if not deduped:
        return 0, 0
    async with session_factory() as s:
        result = await s.execute(select(Word.id, Word.frequency_rank))
        existing = {rank: word_id for word_id, rank in result.all()}
        to_insert = [row for rank, row in deduped.items() if rank not in existing]
        to_update = [
            {"id": existing[rank], **row}
            for rank, row in deduped.items()
            if rank in existing
        ]
        if to_insert:
            await s.execute(insert(Word), to_insert)
        if to_update:
            # ORM bulk update by primary key.
            await s.execute(update(Word), to_update)
        await s.commit()
    return len(to_insert), len(to_update)


async def seed_if_empty(
    session_factory: async_sessionmaker, csv_path: Path
) -> int:
    """Seed a fresh database; no-op once any word exists.

    A deployment starts with an empty volume, so without this the bot would come
    up with nothing to teach.
    """
    existing = await count_words(session_factory)
    if existing:
        logger.info("dictionary_present words=%s", existing)
        return 0
    if not csv_path.exists():
        logger.warning("dictionary_csv_missing path=%s", csv_path)
        return 0
    inserted, _ = await seed_from_csv(session_factory, csv_path)
    logger.info("dictionary_seeded words=%s path=%s", inserted, csv_path)
    return inserted
