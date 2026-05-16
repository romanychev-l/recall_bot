from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from bot.services.stats_service import StatsService


@pytest.mark.asyncio
async def test_accuracy_7d(users_repo, cards_repo, review_log_repo) -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    wid = ObjectId()
    bid = ObjectId()
    for r in ("good", "good", "again", "good"):
        await review_log_repo.append(
            user_id=1, word_id=wid, batch_id=bid,
            result=r, user_input="x", reviewed_at=now - timedelta(days=1),
        )
    stats = StatsService(users_repo, cards_repo, review_log_repo)
    acc = await stats.accuracy_7d(1, now=now)
    assert abs(acc - 0.75) < 1e-9


@pytest.mark.asyncio
async def test_accuracy_zero_when_no_reviews(users_repo, cards_repo, review_log_repo) -> None:
    stats = StatsService(users_repo, cards_repo, review_log_repo)
    assert await stats.accuracy_7d(1, now=datetime.now(timezone.utc)) == 0.0


@pytest.mark.asyncio
async def test_streak_today_and_yesterday(
    users_repo, cards_repo, review_log_repo
) -> None:
    now = datetime(2026, 6, 10, 20, tzinfo=timezone.utc)
    wid, bid = ObjectId(), ObjectId()
    for d in (0, 1, 2, 3):
        await review_log_repo.append(
            user_id=1, word_id=wid, batch_id=bid,
            result="good", user_input="x",
            reviewed_at=now - timedelta(days=d, hours=1),
        )
    stats = StatsService(users_repo, cards_repo, review_log_repo)
    assert await stats.streak(1, now=now) == 4


@pytest.mark.asyncio
async def test_streak_broken(users_repo, cards_repo, review_log_repo) -> None:
    now = datetime(2026, 6, 10, 20, tzinfo=timezone.utc)
    wid, bid = ObjectId(), ObjectId()
    # only one entry 5 days ago — streak should be 0 (too old)
    await review_log_repo.append(
        user_id=1, word_id=wid, batch_id=bid,
        result="good", user_input="x",
        reviewed_at=now - timedelta(days=5),
    )
    stats = StatsService(users_repo, cards_repo, review_log_repo)
    assert await stats.streak(1, now=now) == 0
