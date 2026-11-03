from __future__ import annotations

import re
import unicodedata

import Levenshtein


def normalize(text: str) -> str:
    return text.strip().lower()


def is_correct(user_input: str, target: str) -> bool:
    if not user_input or not target:
        return False
    return Levenshtein.distance(normalize(user_input), normalize(target)) == 0


def _normalize_translation(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    return " ".join(text.split()).strip(" .!?…")


def _translation_variants(translation: str) -> set[str]:
    """Semicolons separate meanings; commas can be part of a Russian phrase."""
    variants = set()
    for meaning in translation.split(";"):
        variants.add(_normalize_translation(meaning))
        # A whole parenthesized definition, e.g. an article, is an answer too.
        if meaning.strip().startswith("(") and meaning.strip().endswith(")"):
            variants.add(_normalize_translation(meaning.strip()[1:-1]))
        # Trailing qualifiers are optional: «удар (кулаком)» → «удар».
        bare = re.sub(r"\s+\([^()]*\)", "", meaning)
        variants.add(_normalize_translation(bare))
        # Compact optional endings: «собирать(ся)» accepts both forms.
        optional = re.search(r"(?<=\w)\(([^()]*)\)", bare)
        if optional:
            for ending in ("", optional[1]):
                variants.add(_normalize_translation(
                    bare[:optional.start()] + ending + bare[optional.end():]
                ))
    return variants - {""}


def is_translation_correct(user_input: str, translation: str) -> bool:
    """Accept one dictionary meaning, without fuzzy or substring matching."""
    answer = _normalize_translation(user_input)
    return bool(answer) and answer in _translation_variants(translation)
