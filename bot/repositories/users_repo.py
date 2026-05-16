from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from bot.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DAILY_GOAL,
    DEFAULT_REMINDER_TIME,
    DEFAULT_TZ,
    USERS_COLLECTION,
)


class UsersRepo:
    def __init__(self, db: Any) -> None:
        self._coll = db[USERS_COLLECTION]

    async def get(self, telegram_id: int) -> Optional[dict[str, Any]]:
        return await self._coll.find_one({"_id": telegram_id})

    async def create_if_absent(
        self,
        telegram_id: int,
        *,
        initial_rank: int = 0,
        language: str = "ru",
    ) -> dict[str, Any]:
        doc = await self.get(telegram_id)
        if doc is not None:
            return doc
        doc = {
            "_id": telegram_id,
            "batch_size": DEFAULT_BATCH_SIZE,
            "daily_goal": DEFAULT_DAILY_GOAL,
            "reminder_time": DEFAULT_REMINDER_TIME,
            "tz": DEFAULT_TZ,
            "language": language,
            "initial_rank": initial_rank,
            "current_batch_id": None,
            "next_batch_start_rank": initial_rank,
            "streak_days": 0,
            "last_session_date": None,
            "created_at": datetime.now(timezone.utc),
        }
        await self._coll.insert_one(doc)
        return doc

    async def update(self, telegram_id: int, **fields: Any) -> None:
        if not fields:
            return
        await self._coll.update_one({"_id": telegram_id}, {"$set": fields})

    async def set_current_batch(
        self, telegram_id: int, batch_id: ObjectId, next_start_rank: int
    ) -> None:
        await self.update(
            telegram_id,
            current_batch_id=batch_id,
            next_batch_start_rank=next_start_rank,
        )

    async def all(self) -> list[dict[str, Any]]:
        return [doc async for doc in self._coll.find({})]
