from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select

from bot.db.models import Word, WordSense, UserCard
from bot.domain.parts_of_speech import ALL_POS
from bot.repositories.base import BaseRepo, one, rows
from bot.repositories.word_filters import matches_parts


class WordsRepo(BaseRepo):
    async def senses(self, word_id: int) -> list[dict[str, Any]]:
        async with self._sf() as s:
            return rows(await s.execute(select(WordSense.__table__).where(
                WordSense.word_id == word_id
            ).order_by(WordSense.position)))

    @staticmethod
    def _available(user_id: int, min_rank: int, pos_filter: int):
        return (
            Word.frequency_rank >= min_rank,
            ~select(1).where(UserCard.user_id == user_id, UserCard.word_id == Word.id).exists(),
            matches_parts(pos_filter),
        )

    async def available_count(self, user_id: int, min_rank: int, pos_filter: int = ALL_POS) -> int:
        async with self._sf() as s:
            result = await s.execute(select(func.count()).select_from(Word).where(
                *self._available(user_id, min_rank, pos_filter)
            ))
            return int(result.scalar_one())

    async def next_available(self, user_id: int, min_rank: int, n: int,
                             pos_filter: int = ALL_POS) -> list[dict[str, Any]]:
        async with self._sf() as s:
            return rows(await s.execute(select(Word.__table__).where(
                *self._available(user_id, min_rank, pos_filter)
            ).order_by(Word.frequency_rank).limit(n)))

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
