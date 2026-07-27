"""Seed the words table from a CSV file.

CSV columns (with header):
    english,translation,frequency_rank,pos,example,is_phrasal

Usage:
    python -m data.seed data/dictionary.csv
    python -m data.seed data/fixtures/test_words.csv

Upserts by frequency_rank (unique), so re-runs are safe. The bot also seeds an
empty database on startup; use this to refresh or extend an existing one.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Allow running as a module from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config_data.config import config_settings, engine, session_factory
from bot.db.bootstrap import run_migrations
from bot.db.seed import seed_from_csv

logger = logging.getLogger(__name__)


async def _run(csv_path: Path) -> tuple[int, int]:
    await run_migrations(config_settings.database_url)
    try:
        return await seed_from_csv(session_factory, csv_path)
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="Seed the words table from a CSV")
    parser.add_argument("csv", type=Path, help="Path to dictionary CSV")
    args = parser.parse_args()
    if not args.csv.exists():
        parser.error(f"file not found: {args.csv}")
    inserted, updated = asyncio.run(_run(args.csv))
    logger.info("seeded inserted=%s updated=%s", inserted, updated)
    print(f"Inserted: {inserted}, updated: {updated}")


if __name__ == "__main__":
    main()
