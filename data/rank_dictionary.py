"""Restore corpus frequency order without rebuilding reviewed translations.

Usage: python -m data.rank_dictionary --frequency data/.cache/en_full.txt
The source is FrequencyWords/content/2018/en/en_full.txt (OpenSubtitles).
Phrases retain their relative order after the single-word vocabulary.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

FIELDS = ["english", "translation", "frequency_rank", "pos", "example", "is_phrasal", "frequency_count"]


def load_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            word, count = line.split()
            counts.setdefault(word.lower(), int(count))
    return counts


def rank_rows(rows: list[dict], counts: dict[str, int]) -> list[dict]:
    """Rank all existing words, keeping their translations and other metadata."""
    words, phrases = [], []
    for row in rows:
        if str(row.get("is_phrasal", "false")).lower() in ("true", "1", "yes"):
            phrases.append(row)
        else:
            if row["english"] not in counts:
                raise ValueError(f"Missing corpus frequency for {row['english']!r}")
            words.append(row)
    words.sort(key=lambda row: (-counts[row["english"]], row["english"]))
    phrases.sort(key=lambda row: int(row["frequency_rank"]))
    ranked = [{**row, "frequency_count": counts[row["english"]]} for row in words]
    ranked += [{**row, "frequency_count": ""} for row in phrases]
    return [{**row, "frequency_rank": rank} for rank, row in enumerate(ranked, 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", type=Path, required=True)
    parser.add_argument("--dictionary", type=Path, default=Path("data/dictionary.csv"))
    args = parser.parse_args()
    with args.dictionary.open(encoding="utf-8", newline="") as source:
        ranked = rank_rows(list(csv.DictReader(source)), load_counts(args.frequency))
    with args.dictionary.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ranked)
    print(f"Ranked {len(ranked)} entries in {args.dictionary}")


if __name__ == "__main__":
    main()
