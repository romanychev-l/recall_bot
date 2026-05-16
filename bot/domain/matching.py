from __future__ import annotations

import Levenshtein


def normalize(text: str) -> str:
    return text.strip().lower()


def is_correct(user_input: str, target: str) -> bool:
    if not user_input or not target:
        return False
    return Levenshtein.distance(normalize(user_input), normalize(target)) == 0
