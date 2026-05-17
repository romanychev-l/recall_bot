from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.domain.cefr import cefr_for_rank, cefr_progress
from bot.repositories.cards_repo import CardsRepo
from bot.repositories.review_log_repo import ReviewLogRepo
from bot.repositories.users_repo import UsersRepo


class StatsService:
    def __init__(
        self,
        users_repo: UsersRepo,
        cards_repo: CardsRepo,
        review_log_repo: ReviewLogRepo,
    ) -> None:
        self.users_repo = users_repo
        self.cards_repo = cards_repo
        self.review_log_repo = review_log_repo

    async def graduated_count(self, user_id: int) -> int:
        return await self.cards_repo.count_graduated(user_id)

    async def state_counts(self, user_id: int) -> dict[str, int]:
        return await self.cards_repo.count_by_state(user_id)

    async def today_counts(
        self, user_id: int, tz: str, now: Optional[datetime] = None
    ) -> tuple[int, int]:
        """Return (correct_today, total_today) in user's local day."""
        from zoneinfo import ZoneInfo
        now = now or datetime.now(timezone.utc)
        local = now.astimezone(ZoneInfo(tz))
        day_start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_local.astimezone(timezone.utc)
        return await self.review_log_repo.stats_for_window(user_id, day_start_utc)

    async def accuracy_7d(self, user_id: int, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        good, total = await self.review_log_repo.stats_for_window(user_id, since)
        if total == 0:
            return 0.0
        return good / total

    async def streak(self, user_id: int, now: Optional[datetime] = None) -> int:
        now = now or datetime.now(timezone.utc)
        since = now - timedelta(days=60)
        days = await self.review_log_repo.distinct_days(user_id, since)
        if not days:
            return 0
        unique_dates = sorted({d.date() for d in days}, reverse=True)
        today = now.date()
        # Allow streak to start either today or yesterday
        if unique_dates[0] not in (today, today - timedelta(days=1)):
            return 0
        streak = 1
        cursor = unique_dates[0]
        for d in unique_dates[1:]:
            if d == cursor - timedelta(days=1):
                streak += 1
                cursor = d
            else:
                break
        return streak

    async def cefr_progress(self, user_id: int) -> dict[str, dict[str, int]]:
        """CEFR progress based on cards that passed first interval (review + graduated)."""
        ranks = await self.cards_repo.learned_ranks(user_id)
        return cefr_progress(ranks)

    @staticmethod
    def cefr_for_rank(rank: int) -> str:
        return cefr_for_rank(rank)
