from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select

from bot.db.models import Word
from bot.repositories.base import BaseRepo, one, rows


class WordsRepo(BaseRepo):
    async def by_id(self, word_id: int) -> Optional[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(select(Word.__table__).where(Word.id == word_id))
            return one(res)

    async def by_ids(self, word_ids: list[int]) -> list[dict[str, Any]]:
        if not word_ids:
            return []
        async with self._sf() as s:
            res = await s.execute(
                select(Word.__table__).where(Word.id.in_(word_ids))
            )
            return rows(res)

    async def next_n_with_rank_gte(
        self, min_rank: int, n: int
    ) -> list[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(
                select(Word.__table__)
                .where(Word.frequency_rank >= min_rank)
                .order_by(Word.frequency_rank.asc())
                .limit(n)
            )
            return rows(res)

    async def count(self) -> int:
        async with self._sf() as s:
            res = await s.execute(select(func.count()).select_from(Word.__table__))
            return int(res.scalar_one())
