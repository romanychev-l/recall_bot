"""Load the dictionary CSV into the words table.

CSV columns (with header):
    english,translation,frequency_rank,pos,example,is_phrasal
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Word, WordSense
from bot.domain.parts_of_speech import POS_BITS, pos_mask
from bot.db.dictionary_sync import apply_dictionary

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
    """Upsert by English word, preserving IDs, cards and review history."""
    entries = list(read_rows(csv_path))
    if not entries:
        return 0, 0
    async with session_factory() as s:
        result = await apply_dictionary(s, entries, update_content=True)
        updated_ids = select(Word.id).where(Word.english.in_(row["english"] for row in entries))
        await s.execute(delete(WordSense).where(WordSense.word_id.in_(updated_ids)))
        await s.commit()
    await seed_word_senses(session_factory, csv_path.with_name(csv_path.stem + "_senses.csv"))
    return result


async def seed_word_senses(session_factory: async_sessionmaker, senses_csv: Path) -> int:
    """Fill only missing metadata, including when upgrading an existing volume.

    The sidecar matches both English and the exact Russian translation. Custom
    dictionaries without a sidecar use their own POS labels. No word IDs, ranks
    or learning state are rewritten.
    """
    async with session_factory() as s:
        missing = (await s.execute(select(Word.__table__).where(
            ~select(1).where(WordSense.word_id == Word.id).exists()
        ))).mappings().all()
        if not missing:
            return 0
        metadata = {}
        if senses_csv.is_file():
            with senses_csv.open(encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source):
                    mask = 0
                    for category in row["parts_of_speech"].split("|"):
                        mask |= POS_BITS[category]
                    metadata[row["english"], row["translation"]] = mask
        payload = []
        for word in missing:
            for position, translation in enumerate(word["translation"].split(";")):
                translation = translation.strip()
                if translation:
                    payload.append(dict(
                        word_id=word["id"], position=position, translation=translation,
                        pos_mask=metadata.get((word["english"], translation), pos_mask(word["pos"])),
                    ))
        if payload:
            await s.execute(insert(WordSense), payload)
            await s.commit()
        logger.info("word_senses_seeded senses=%s", len(payload))
        return len(payload)


async def seed_if_empty(
    session_factory: async_sessionmaker, csv_path: Path
) -> int:
    """Seed a fresh database or sync ranks of known words on an existing one.

    Existing translations and word IDs are preserved. The rank update and card
    rank mirrors are committed together before the bot accepts any updates.
    """
    existing = await count_words(session_factory)
    if existing:
        if csv_path.exists():
            async with session_factory() as s:
                _, updated = await apply_dictionary(s, list(read_rows(csv_path)), update_content=False)
                await s.commit()
            logger.info("dictionary_ranks_synced words=%s updated=%s", existing, updated)
        else:
            logger.warning("dictionary_csv_missing path=%s", csv_path)
        return 0
    if not csv_path.exists():
        logger.warning("dictionary_csv_missing path=%s", csv_path)
        return 0
    inserted, _ = await seed_from_csv(session_factory, csv_path)
    logger.info("dictionary_seeded words=%s path=%s", inserted, csv_path)
    return inserted
