from __future__ import annotations

from bot.constants import CEFR_BANDS


def cefr_for_rank(rank: int) -> str:
    for level, lo, hi in CEFR_BANDS:
        if lo <= rank <= hi:
            return level
    return "C2+"


def cefr_progress(graduated_ranks: list[int]) -> dict[str, dict[str, int]]:
    """Return per-CEFR-level {graduated, total} counts."""
    result: dict[str, dict[str, int]] = {}
    for level, lo, hi in CEFR_BANDS:
        total = hi - lo + 1
        graduated = sum(1 for r in graduated_ranks if lo <= r <= hi)
        result[level] = {"graduated": graduated, "total": total}
    return result
