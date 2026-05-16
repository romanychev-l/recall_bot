"""Seed MongoDB with words from a CSV file.

CSV columns (with header):
    english,translation,frequency_rank,pos,example,is_phrasal

Usage:
    python -m data.seed data/dictionary.csv
    python -m data.seed data/fixtures/test_words.csv

The seeder upserts by frequency_rank (unique). Re-runs are safe.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

# Allow running as a module from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config_data.config import db
from bot.constants import WORDS_COLLECTION
from bot.repositories.words_repo import WordsRepo

logger = logging.getLogger(__name__)


def _coerce_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y")


def _read_rows(path: Path) -> Iterable[dict]:
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


async def seed(csv_path: Path, batch: int = 1000) -> int:
    words_repo = WordsRepo(db)
    await words_repo.ensure_indexes()
    coll = db[WORDS_COLLECTION]
    total = 0
    pending: list = []
    for row in _read_rows(csv_path):
        pending.append({
            "filter": {"frequency_rank": row["frequency_rank"]},
            "update": {"$set": row},
        })
        if len(pending) >= batch:
            total += await _flush(coll, pending)
            pending = []
    if pending:
        total += await _flush(coll, pending)
    return total


async def _flush(coll, ops: list) -> int:
    from pymongo import UpdateOne
    bulk = [UpdateOne(o["filter"], o["update"], upsert=True) for o in ops]
    result = await coll.bulk_write(bulk, ordered=False)
    return (result.upserted_count or 0) + (result.modified_count or 0)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="Seed MongoDB with words CSV")
    parser.add_argument("csv", type=Path, help="Path to dictionary CSV")
    args = parser.parse_args()
    if not args.csv.exists():
        parser.error(f"file not found: {args.csv}")
    count = asyncio.run(seed(args.csv))
    logger.info("seeded rows: %s", count)
    print(f"Seeded/updated: {count}")


if __name__ == "__main__":
    main()
