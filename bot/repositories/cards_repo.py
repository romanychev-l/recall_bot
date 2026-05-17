from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from bot.constants import (
    STATE_LEARNING,
    STATE_NEW,
    STATE_REVIEW,
    USER_CARDS_COLLECTION,
)


class CardsRepo:
    def __init__(self, db: Any) -> None:
        self._coll = db[USER_CARDS_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._coll.create_index(
            [("user_id", 1), ("word_id", 1)], unique=True
        )
        await self._coll.create_index([("user_id", 1), ("fsrs.due", 1)])
        await self._coll.create_index(
            [("user_id", 1), ("batch_id", 1), ("my_state", 1)]
        )

    async def get(self, user_id: int, word_id: ObjectId) -> Optional[dict[str, Any]]:
        return await self._coll.find_one({"user_id": user_id, "word_id": word_id})

    async def bulk_create_new(
        self,
        user_id: int,
        words: list[dict[str, Any]],
        batch_id: ObjectId,
        fsrs_factory,
        now: datetime,
    ) -> list[dict[str, Any]]:
        if not words:
            return []
        docs = []
        for w in words:
            docs.append({
                "_id": ObjectId(),
                "user_id": user_id,
                "word_id": w["_id"],
                "batch_id": batch_id,
                "frequency_rank": w["frequency_rank"],
                "fsrs": fsrs_factory(now),
                "my_state": STATE_NEW,
                "consecutive_successes_at_review": 0,
                "first_reached_review_at": None,
                "is_hard": False,
                "skip_until": None,
                "created_at": now,
                "updated_at": now,
            })
        await self._coll.insert_many(docs)
        return docs

    async def update_after_review(
        self,
        user_id: int,
        word_id: ObjectId,
        *,
        fsrs: dict[str, Any],
        my_state: str,
        consecutive_successes_at_review: int,
        first_reached_review_at: Optional[datetime],
        now: datetime,
    ) -> None:
        await self._coll.update_one(
            {"user_id": user_id, "word_id": word_id},
            {
                "$set": {
                    "fsrs": fsrs,
                    "my_state": my_state,
                    "consecutive_successes_at_review": consecutive_successes_at_review,
                    "first_reached_review_at": first_reached_review_at,
                    "updated_at": now,
                }
            },
        )

    async def set_hard(self, user_id: int, word_id: ObjectId, value: bool) -> None:
        await self._coll.update_one(
            {"user_id": user_id, "word_id": word_id},
            {"$set": {"is_hard": value, "updated_at": datetime.now(timezone.utc)}},
        )

    async def set_skip_until(
        self, user_id: int, word_id: ObjectId, until: datetime
    ) -> None:
        await self._coll.update_one(
            {"user_id": user_id, "word_id": word_id},
            {"$set": {"skip_until": until, "updated_at": datetime.now(timezone.utc)}},
        )

    async def count_pending_in_batch(self, user_id: int, batch_id: ObjectId) -> int:
        return await self._coll.count_documents(
            {
                "user_id": user_id,
                "batch_id": batch_id,
                "my_state": {"$in": [STATE_NEW, STATE_LEARNING]},
            }
        )

    async def find_due(
        self, user_id: int, now: datetime, limit: int
    ) -> list[dict[str, Any]]:
        cursor = self._coll.find(
            {
                "user_id": user_id,
                "my_state": {"$in": [STATE_LEARNING, STATE_REVIEW]},
                "fsrs.due": {"$lte": now},
                "$or": [
                    {"skip_until": None},
                    {"skip_until": {"$lte": now}},
                ],
            }
        ).sort([("is_hard", -1), ("frequency_rank", 1)]).limit(limit)
        return [doc async for doc in cursor]

    async def find_new_in_batch(
        self, user_id: int, batch_id: ObjectId, limit: int
    ) -> list[dict[str, Any]]:
        cursor = self._coll.find(
            {"user_id": user_id, "batch_id": batch_id, "my_state": STATE_NEW}
        ).sort("frequency_rank", 1).limit(limit)
        return [doc async for doc in cursor]

    async def count_graduated(self, user_id: int) -> int:
        return await self._coll.count_documents(
            {"user_id": user_id, "my_state": "graduated"}
        )

    async def count_by_state(self, user_id: int) -> dict[str, int]:
        """Return {state: count} for all four states."""
        out = {STATE_NEW: 0, STATE_LEARNING: 0, STATE_REVIEW: 0, "graduated": 0}
        cursor = self._coll.aggregate([
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$my_state", "n": {"$sum": 1}}},
        ])
        async for doc in cursor:
            out[doc["_id"]] = doc["n"]
        return out

    async def graduated_ranks(self, user_id: int) -> list[int]:
        cursor = self._coll.find(
            {"user_id": user_id, "my_state": "graduated"},
            projection={"frequency_rank": 1},
        )
        return [doc["frequency_rank"] async for doc in cursor]

    async def learned_ranks(self, user_id: int) -> list[int]:
        """Ranks of cards in review OR graduated state — 'made it past first interval'."""
        cursor = self._coll.find(
            {"user_id": user_id, "my_state": {"$in": [STATE_REVIEW, "graduated"]}},
            projection={"frequency_rank": 1},
        )
        return [doc["frequency_rank"] async for doc in cursor]
