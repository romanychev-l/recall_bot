from __future__ import annotations

import pytest

from bot.domain.matching import is_correct, is_translation_correct, normalize


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


@pytest.mark.parametrize("answer,translation,expected", [
    ("свет", "свет; лёгкий", True),
    (" ЛЕГКИЙ! ", "свет; лёгкий", True),
    ("вместе   с", "с; вместе с", True),
    ("удар", "удар (кулаком); ударить; пунш", True),
    ("удар (кулаком)", "удар (кулаком); ударить; пунш", True),
    ("собирать", "собирать(ся)", True),
    ("собираться", "собирать(ся)", True),
    ("определенный артикль", "(определённый артикль)", True),
    ("тот, кто закрывает", "ближе; тот, кто закрывает", True),
    ("тот", "ближе; тот, кто закрывает", False),
    ("кто закрывает", "ближе; тот, кто закрывает", False),
    ("лёгкая", "свет; лёгкий", False),
    ("све", "свет; лёгкий", False),
    ("light", "свет; лёгкий", False),
    ("свет; неправильно", "свет; лёгкий", False),
    ("", "свет", False),
    ("...", "свет", False),
    ("свет", "", False),
    ("кулаком", "удар (кулаком)", False),
])
def test_one_russian_dictionary_meaning(answer, translation, expected):
    assert is_translation_correct(answer, translation) is expected
