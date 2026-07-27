from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from bot.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DAILY_GOAL,
    DEFAULT_REMINDER_TIME,
    DEFAULT_TZ,
)
from bot.db.models import User
from bot.repositories.base import BaseRepo, one, rows


class UsersRepo(BaseRepo):
    async def get(self, telegram_id: int) -> Optional[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(
                select(User.__table__).where(User.id == telegram_id)
            )
            return one(res)

    async def create_if_absent(
        self,
        telegram_id: int,
        *,
        initial_rank: int = 0,
        language: str = "ru",
    ) -> dict[str, Any]:
        existing = await self.get(telegram_id)
        if existing is not None:
            return existing
        try:
            async with self._sf() as s:
                await s.execute(
                    insert(User).values(
                        id=telegram_id,
                        batch_size=DEFAULT_BATCH_SIZE,
                        daily_goal=DEFAULT_DAILY_GOAL,
                        reminder_time=DEFAULT_REMINDER_TIME,
                        tz=DEFAULT_TZ,
                        language=language,
                        initial_rank=initial_rank,
                        current_batch_id=None,
                        next_batch_start_rank=initial_rank,
                        streak_days=0,
                        last_session_date=None,
                        created_at=datetime.now(timezone.utc),
                    )
                )
                await s.commit()
        except IntegrityError:
            # Two updates from the same user can race here; whoever lost still
            # wants the row that won.
            pass
        created = await self.get(telegram_id)
        if created is None:  # pragma: no cover - insert either landed or raced
            raise RuntimeError(f"failed to create user {telegram_id}")
        return created

    async def update(self, telegram_id: int, **fields: Any) -> None:
        if not fields:
            return
        async with self._sf() as s:
            await s.execute(
                update(User).where(User.id == telegram_id).values(**fields)
            )
            await s.commit()

    async def set_current_batch(
        self, telegram_id: int, batch_id: int, next_start_rank: int
    ) -> None:
        await self.update(
            telegram_id,
            current_batch_id=batch_id,
            next_batch_start_rank=next_start_rank,
        )

    async def all(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(select(User.__table__))
            return rows(res)
