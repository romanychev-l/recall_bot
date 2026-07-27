from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, insert, select

from bot.constants import RESULT_GOOD
from bot.db.models import ReviewLog
from bot.repositories.base import BaseRepo


class ReviewLogRepo(BaseRepo):
    async def append(
        self,
        *,
        user_id: int,
        word_id: int,
        batch_id: int,
        result: str,
        user_input: str,
        reviewed_at: datetime,
    ) -> None:
        async with self._sf() as s:
            await s.execute(
                insert(ReviewLog).values(
                    user_id=user_id,
                    word_id=word_id,
                    batch_id=batch_id,
                    result=result,
                    user_input=user_input,
                    reviewed_at=reviewed_at,
                )
            )
            await s.commit()

    async def stats_for_window(
        self, user_id: int, since: datetime
    ) -> tuple[int, int]:
        """Return (correct_count, total_count) since the given datetime."""
        async with self._sf() as s:
            res = await s.execute(
                select(
                    func.count(),
                    func.coalesce(
                        func.sum(case((ReviewLog.result == RESULT_GOOD, 1), else_=0)),
                        0,
                    ),
                ).where(
                    ReviewLog.user_id == user_id,
                    ReviewLog.reviewed_at >= since,
                )
            )
            total, good = res.one()
            return int(good), int(total)

    async def distinct_days(
        self, user_id: int, since: datetime
    ) -> list[datetime]:
        """Newest-first timestamps, one per distinct UTC calendar day."""
        async with self._sf() as s:
            res = await s.execute(
                select(ReviewLog.reviewed_at)
                .where(
                    ReviewLog.user_id == user_id,
                    ReviewLog.reviewed_at >= since,
                )
                .order_by(ReviewLog.reviewed_at.desc())
            )
            seen: set[tuple[int, int, int]] = set()
            ordered: list[datetime] = []
            for ts in res.scalars():
                key = (ts.year, ts.month, ts.day)
                if key not in seen:
                    seen.add(key)
                    ordered.append(ts)
            return ordered
