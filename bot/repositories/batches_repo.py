from __future__ import annotations

from datetime import datetime

from sqlalchemy import insert

from bot.db.models import Batch
from bot.repositories.base import BaseRepo


class BatchesRepo(BaseRepo):
    async def create(self, user_id: int, now: datetime) -> int:
        """Create a batch and return its generated id."""
        async with self._sf() as s:
            res = await s.execute(
                insert(Batch)
                .values(user_id=user_id, created_at=now)
                .returning(Batch.id)
            )
            batch_id = int(res.scalar_one())
            await s.commit()
            return batch_id
