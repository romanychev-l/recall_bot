"""Stable category bits shared by settings, dictionary senses and cards."""
from __future__ import annotations

# Bits are persisted: never reorder or reuse a category's position.
PARTS_OF_SPEECH = (
    "noun", "verb", "adj", "adv", "pron", "num", "prep", "conj",
    "det", "intj", "particle", "name", "phrase", "other",
)
POS_BITS = {pos: 1 << index for index, pos in enumerate(PARTS_OF_SPEECH)}
ALL_POS = sum(POS_BITS.values())
POS_ALIASES = {"modal": "verb", "phrasal": "verb", "proper_noun": "name"}


def pos_mask(pos: str) -> int:
    category = pos.strip().lower()
    category = POS_ALIASES.get(category, category)
    return POS_BITS.get(category, POS_BITS["other"])


def selected_parts(mask: int) -> list[str]:
    return [pos for pos, bit in POS_BITS.items() if mask & bit]


def validate_pos_filter(mask: int) -> None:
    if not isinstance(mask, int) or mask <= 0 or mask & ~ALL_POS:
        raise ValueError("Select at least one valid part of speech")


def study_word(word: dict, senses: list[dict], mask: int) -> dict | None:
    """Render only meanings shared by the card's categories and current filter."""
    if mask == ALL_POS:
        return word
    matching = [sense for sense in senses if sense["pos_mask"] & mask]
    if not senses:
        # Custom dictionaries may only provide the row's POS.
        return word if pos_mask(word.get("pos", "")) & mask else None
    if not matching:
        return None
    translations = list(dict.fromkeys(sense["translation"] for sense in matching))
    matched_mask = 0
    for sense in matching:
        matched_mask |= sense["pos_mask"] & mask
    return {
        **word,
        "translation": "; ".join(translations),
        "pos": ", ".join(selected_parts(matched_mask)),
    }
