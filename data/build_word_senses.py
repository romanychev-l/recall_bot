"""Match existing Russian translations to their POS in the local Kaikki dump.

No English-spelling-only inference: unmatched translations stay in 'other'.
Usage: python -m data.build_word_senses --kaikki PATH
The output supplements dictionary.csv without changing its ranks or word IDs.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from bot.domain.parts_of_speech import POS_BITS, pos_mask, selected_parts
from data.build_dictionary import iter_kaikki, strip_stress


def normalize(text: str) -> str:
    return " ".join(strip_stress(text).lower().replace("ё", "е").split())


def build_senses(dictionary: Path, kaikki: Path, output: Path) -> None:
    with dictionary.open(encoding="utf-8", newline="") as source:
        words = list(csv.DictReader(source))
    wanted = {row["english"].lower() for row in words}
    lookup: dict[tuple[str, str], int] = defaultdict(int)
    for entry in iter_kaikki(kaikki):
        english = (entry.get("word") or "").lower()
        if english not in wanted:
            continue
        mask = pos_mask(entry.get("pos") or "")
        lists = [entry.get("translations") or []]
        lists.extend(sense.get("translations") or [] for sense in entry.get("senses") or [])
        for translations in lists:
            for translation in translations:
                if translation.get("lang_code") == "ru" and translation.get("word"):
                    lookup[english, normalize(translation["word"])] |= mask
    unknown = 0
    total = 0
    with output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["english", "translation", "parts_of_speech"], lineterminator="\n")
        writer.writeheader()
        seen = set()
        for row in words:
            for translation in row["translation"].split(";"):
                translation = translation.strip()
                key = (row["english"], translation)
                if not translation or key in seen:
                    continue
                seen.add(key)
                mask = lookup.get((row["english"].lower(), normalize(translation)), POS_BITS["other"])
                unknown += mask == POS_BITS["other"]
                total += 1
                writer.writerow(dict(english=row["english"], translation=translation,
                                     parts_of_speech="|".join(selected_parts(mask))))
    print(f"Wrote {total} translations; {unknown} unclassified to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=Path("data/dictionary.csv"))
    parser.add_argument("--kaikki", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/dictionary_senses.csv"))
    args = parser.parse_args()
    build_senses(args.dictionary, args.kaikki, args.out)
