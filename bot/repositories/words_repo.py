from __future__ import annotations

from typing import Any, Optional

from bson import ObjectId

from bot.constants import WORDS_COLLECTION


class WordsRepo:
    def __init__(self, db: Any) -> None:
        self._coll = db[WORDS_COLLECTION]

    async def by_id(self, word_id: ObjectId) -> Optional[dict[str, Any]]:
        return await self._coll.find_one({"_id": word_id})

    async def by_ids(self, word_ids: list[ObjectId]) -> list[dict[str, Any]]:
        if not word_ids:
            return []
        cursor = self._coll.find({"_id": {"$in": word_ids}})
        return [doc async for doc in cursor]

    async def next_n_with_rank_gte(self, min_rank: int, n: int) -> list[dict[str, Any]]:
        cursor = (
            self._coll.find({"frequency_rank": {"$gte": min_rank}})
            .sort("frequency_rank", 1)
            .limit(n)
        )
        return [doc async for doc in cursor]

    async def count(self) -> int:
        return await self._coll.count_documents({})

    async def ensure_indexes(self) -> None:
        await self._coll.create_index("frequency_rank", unique=True)
        await self._coll.create_index("english")
