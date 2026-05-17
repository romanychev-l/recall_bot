"""Build dictionary.csv from open data sources.

Two translation sources are supported (pick one):

  --kaikki PATH       Use a Wiktionary dump from kaikki.org (rich: POS + sense).
                      File: kaikki.org-dictionary-English.jsonl.gz (~450MB gz).
                      Get it from https://kaikki.org/dictionary/English/index.html.

  (default)           Use Facebook MUSE en-ru dictionary (auto-downloads ~1.2MB).
                      Faster but no POS, single literal translation per word.

Frequency list always comes from hermitdave/FrequencyWords (OpenSubtitles 2018).

Phrasal verbs from data/phrasal_verbs.csv are appended with continued rank.

Usage:
    python -m data.build_dictionary --top 20000 --out data/dictionary.csv
    python -m data.build_dictionary --kaikki kaikki.org-dictionary-English.jsonl.gz
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Iterator, Optional

FREQ_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/"
    "content/2018/en/en_full.txt"
)
MUSE_URL = "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-ru.txt"

SKIP_WORDS = {
    "the", "a", "an", "to", "of", "in", "on", "at", "for", "by", "with",
    "and", "or", "but", "if", "as", "is", "are", "was", "were", "be", "been",
}
WORD_RE = re.compile(r"^[a-z][a-z'-]*[a-z]$")

# POS preference (lower = preferred) for words with multiple kaikki entries.
# Function words win — fixes "you"→verb, "it"→noun, "this/that"→adj, etc.
# Verb beats noun — fixes "do"→noun(party), "have"→noun, "be"→noun.
POS_PRIORITY = {
    "pron": 0, "det": 0, "prep": 0, "conj": 0, "intj": 0, "particle": 0,
    "verb": 1,
    "noun": 2,
    "adj": 3,
    "adv": 4,
    "num": 5,
    "phrase": 6,
    "name": 9, "proper_noun": 9,  # avoid proper nouns when alternatives exist
}


def _download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    logging.info("downloading %s → %s", url, dest)
    urllib.request.urlretrieve(url, dest)
    return dest


def strip_stress(s: str) -> str:
    """Remove Russian stress marks (combining acute U+0301, grave U+0300).

    Important: keep U+0306 (combining breve) — that's the diacritic that makes
    'и' into 'й'; stripping it would corrupt words like 'мой' → 'мои'.
    """
    return s.replace("́", "").replace("̀", "")


def load_frequency(path: Path, top: int, over: int = 4) -> list[str]:
    """Top-N English lemmas, most frequent first. Over-fetches for translation gaps."""
    out: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            word = parts[0].lower()
            if word in seen or word in SKIP_WORDS:
                continue
            if not WORD_RE.match(word):
                continue
            seen.add(word)
            out.append(word)
            if len(out) >= top * over:
                break
    return out


def load_muse_translations(path: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            en, ru = parts[0].lower(), parts[1].strip()
            if not ru:
                continue
            out.setdefault(en, (ru, ""))
    return out


def iter_kaikki(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


MAX_PER_ENTRY = 3
MAX_TOTAL = 5


def build_kaikki_index(
    kaikki_path: Path, wanted: set[str]
) -> dict[str, tuple[str, str]]:
    """Stream the kaikki dump; collect (joined_translations, pos) for each wanted lemma.

    A word like "very" has separate adj and adv entries in Wiktionary
    (the adj is "the very man", the adv is "очень"). Picking only one
    POS would drop the dominant adv meaning. So we accumulate across
    ALL POS entries for a word — up to MAX_PER_ENTRY per entry,
    MAX_TOTAL overall. POS label on the row is the one with highest
    POS_PRIORITY (used downstream for display only, doesn't affect
    matching).
    """
    out: dict[str, dict] = {}

    for entry in iter_kaikki(kaikki_path):
        word = (entry.get("word") or "").lower()
        if not word or word not in wanted:
            continue
        pos = entry.get("pos") or ""
        pos_pri = POS_PRIORITY.get(pos, 99)
        rec = out.setdefault(word, {
            "translations": [],
            "seen": set(),
            "best_pos": pos,
            "best_pos_pri": pos_pri,
        })
        if pos_pri < rec["best_pos_pri"]:
            rec["best_pos"] = pos
            rec["best_pos_pri"] = pos_pri

        if len(rec["translations"]) >= MAX_TOTAL:
            continue

        added_here = 0
        translation_lists = [entry.get("translations") or []]
        for sense in entry.get("senses") or []:
            translation_lists.append(sense.get("translations") or [])
        for tr_list in translation_lists:
            if added_here >= MAX_PER_ENTRY or len(rec["translations"]) >= MAX_TOTAL:
                break
            for tr in tr_list:
                if tr.get("lang_code") != "ru":
                    continue
                w = tr.get("word")
                if not w:
                    continue
                clean = strip_stress(w).strip()
                if not clean or clean.lower() in rec["seen"]:
                    continue
                rec["seen"].add(clean.lower())
                rec["translations"].append(clean)
                added_here += 1
                if added_here >= MAX_PER_ENTRY or len(rec["translations"]) >= MAX_TOTAL:
                    break

    return {
        w: ("; ".join(r["translations"]), r["best_pos"])
        for w, r in out.items()
        if r["translations"]
    }


def append_phrasal(out_rows: list[dict], phrasal_csv: Path, start_rank: int) -> int:
    if not phrasal_csv.exists():
        logging.warning("phrasal_verbs.csv missing — skipping")
        return start_rank
    added = 0
    with phrasal_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            english = (row.get("english") or "").strip()
            translation = (row.get("translation") or "").strip()
            if not english or not translation:
                continue
            out_rows.append({
                "english": english,
                "translation": translation,
                "frequency_rank": start_rank + added,
                "pos": (row.get("pos") or "phrasal").strip(),
                "example": (row.get("example") or "").strip(),
                "is_phrasal": "true",
            })
            added += 1
    return start_rank + added


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20000)
    parser.add_argument("--out", type=Path, default=Path("data/dictionary.csv"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/.cache"))
    parser.add_argument("--phrasal", type=Path, default=Path("data/phrasal_verbs.csv"))
    parser.add_argument(
        "--kaikki", type=Path, default=None,
        help="Path to kaikki.org-dictionary-English.jsonl.gz (richer source).",
    )
    args = parser.parse_args()

    freq_file = _download(FREQ_URL, args.cache_dir / "en_full.txt")
    logging.info("loading frequency list")
    freq_words = load_frequency(freq_file, args.top)
    wanted = set(freq_words)

    if args.kaikki:
        if not args.kaikki.exists():
            parser.error(f"--kaikki file not found: {args.kaikki}")
        logging.info("streaming kaikki dump %s (this takes ~1-2 min)", args.kaikki)
        translations = build_kaikki_index(args.kaikki, wanted)
        logging.info("kaikki gave translations for %s lemmas", len(translations))
    else:
        muse_file = _download(MUSE_URL, args.cache_dir / "en-ru.txt")
        logging.info("loading MUSE translations")
        translations = load_muse_translations(muse_file)

    rows: list[dict] = []
    rank = 0
    for word in freq_words:
        item = translations.get(word)
        if not item:
            continue
        ru, pos = item
        rank += 1
        if rank > args.top:
            break
        rows.append({
            "english": word,
            "translation": ru,
            "frequency_rank": rank,
            "pos": pos,
            "example": "",
            "is_phrasal": "false",
        })
    logging.info("merged %s lemmas with translations", len(rows))

    append_phrasal(rows, args.phrasal, rank + 1)
    logging.info("total rows after phrasal verbs: %s", len(rows))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["english", "translation", "frequency_rank", "pos", "example", "is_phrasal"],
        )
        writer.writeheader()
        writer.writerows(rows)
    logging.info("wrote %s entries to %s", len(rows), args.out)
    print(f"OK: {len(rows)} entries → {args.out}")


if __name__ == "__main__":
    main()
