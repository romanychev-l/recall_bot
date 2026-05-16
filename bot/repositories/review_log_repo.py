from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

from bot.constants import REVIEW_LOG_COLLECTION


class ReviewLogRepo:
    def __init__(self, db: Any) -> None:
        self._coll = db[REVIEW_LOG_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._coll.create_index([("user_id", 1), ("reviewed_at", -1)])

    async def append(
        self,
        *,
        user_id: int,
        word_id: ObjectId,
        batch_id: ObjectId,
        result: str,
        user_input: str,
        reviewed_at: datetime,
    ) -> None:
        await self._coll.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "word_id": word_id,
            "batch_id": batch_id,
            "result": result,
            "user_input": user_input,
            "reviewed_at": reviewed_at,
        })

    async def stats_for_window(
        self, user_id: int, since: datetime
    ) -> tuple[int, int]:
        """Return (correct_count, total_count) since the given datetime."""
        cursor = self._coll.find(
            {"user_id": user_id, "reviewed_at": {"$gte": since}},
            projection={"result": 1},
        )
        total = 0
        good = 0
        async for doc in cursor:
            total += 1
            if doc["result"] == "good":
                good += 1
        return good, total

    async def distinct_days(
        self, user_id: int, since: datetime
    ) -> list[datetime]:
        cursor = self._coll.find(
            {"user_id": user_id, "reviewed_at": {"$gte": since}},
            projection={"reviewed_at": 1},
        ).sort("reviewed_at", -1)
        seen: set[tuple[int, int, int]] = set()
        ordered: list[datetime] = []
        async for doc in cursor:
            ts: datetime = doc["reviewed_at"]
            key = (ts.year, ts.month, ts.day)
            if key not in seen:
                seen.add(key)
                ordered.append(ts)
        return ordered
