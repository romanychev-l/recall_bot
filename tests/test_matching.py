from __future__ import annotations

import pytest

from bot.domain.matching import is_correct, normalize


@pytest.mark.parametrize(
    "user_input, target, expected",
    [
        ("apple", "apple", True),
        ("Apple", "apple", True),
        ("apple ", "apple", True),
        (" apple", "apple", True),
        ("APPLE", "apple", True),
        ("appl", "apple", False),
        ("apples", "apple", False),
        ("aple", "apple", False),
        ("", "apple", False),
        ("apple", "", False),
        ("look up", "look up", True),
        ("look  up", "look up", False),  # extra space is Levenshtein > 0
    ],
)
def test_is_correct(user_input: str, target: str, expected: bool) -> None:
    assert is_correct(user_input, target) is expected


def test_normalize_strips_and_lowercases() -> None:
    assert normalize("  APPLE  ") == "apple"
