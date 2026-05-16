from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from bson import ObjectId

# Ensure project root is on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Provide a TOKEN so Settings() doesn't fail on import
os.environ.setdefault("TOKEN", "test-token")

from bot.constants import STATE_LEARNING, STATE_NEW, STATE_REVIEW


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class InMemoryUsersRepo:
    def __init__(self) -> None:
        self.docs: dict[int, dict[str, Any]] = {}

    async def get(self, telegram_id: int):
        return self.docs.get(telegram_id)

    async def create_if_absent(self, telegram_id: int, *, initial_rank: int = 0, language: str = "ru"):
        if telegram_id in self.docs:
            return self.docs[telegram_id]
        from bot.constants import (
            DEFAULT_BATCH_SIZE,
            DEFAULT_DAILY_GOAL,
            DEFAULT_REMINDER_TIME,
            DEFAULT_TZ,
        )
        self.docs[telegram_id] = {
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
        return self.docs[telegram_id]

    async def update(self, telegram_id: int, **fields):
        if telegram_id in self.docs:
            self.docs[telegram_id].update(fields)

    async def set_current_batch(self, telegram_id: int, batch_id, next_start_rank: int):
        await self.update(
            telegram_id, current_batch_id=batch_id, next_batch_start_rank=next_start_rank
        )

    async def all(self):
        return list(self.docs.values())


class InMemoryWordsRepo:
    def __init__(self, words: Optional[list[dict[str, Any]]] = None) -> None:
        self.words = words or []

    async def by_id(self, word_id):
        for w in self.words:
            if w["_id"] == word_id:
                return w
        return None

    async def by_ids(self, word_ids):
        ids = set(word_ids)
        return [w for w in self.words if w["_id"] in ids]

    async def next_n_with_rank_gte(self, min_rank, n):
        candidates = sorted(
            (w for w in self.words if w["frequency_rank"] >= min_rank),
            key=lambda w: w["frequency_rank"],
        )
        return candidates[:n]

    async def count(self):
        return len(self.words)

    async def ensure_indexes(self):
        return None


class InMemoryCardsRepo:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def ensure_indexes(self):
        return None

    def _find(self, user_id, word_id):
        for d in self.docs:
            if d["user_id"] == user_id and d["word_id"] == word_id:
                return d
        return None

    async def get(self, user_id, word_id):
        return self._find(user_id, word_id)

    async def bulk_create_new(self, user_id, words, batch_id, fsrs_factory, now):
        created = []
        for w in words:
            doc = {
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
            }
            self.docs.append(doc)
            created.append(doc)
        return created

    async def update_after_review(
        self, user_id, word_id, *, fsrs, my_state,
        consecutive_successes_at_review, first_reached_review_at, now,
    ):
        d = self._find(user_id, word_id)
        if d is None:
            return
        d.update({
            "fsrs": fsrs,
            "my_state": my_state,
            "consecutive_successes_at_review": consecutive_successes_at_review,
            "first_reached_review_at": first_reached_review_at,
            "updated_at": now,
        })

    async def set_hard(self, user_id, word_id, value):
        d = self._find(user_id, word_id)
        if d is not None:
            d["is_hard"] = value

    async def set_skip_until(self, user_id, word_id, until):
        d = self._find(user_id, word_id)
        if d is not None:
            d["skip_until"] = until

    async def count_pending_in_batch(self, user_id, batch_id):
        return sum(
            1 for d in self.docs
            if d["user_id"] == user_id
            and d["batch_id"] == batch_id
            and d["my_state"] in (STATE_NEW, STATE_LEARNING)
        )

    async def find_due(self, user_id, now, limit):
        candidates = [
            d for d in self.docs
            if d["user_id"] == user_id
            and d["my_state"] in (STATE_LEARNING, STATE_REVIEW)
            and d["fsrs"]["due"] <= now
            and (d["skip_until"] is None or d["skip_until"] <= now)
        ]
        candidates.sort(key=lambda d: (not d["is_hard"], d["frequency_rank"]))
        return candidates[:limit]

    async def find_new_in_batch(self, user_id, batch_id, limit):
        candidates = [
            d for d in self.docs
            if d["user_id"] == user_id
            and d["batch_id"] == batch_id
            and d["my_state"] == STATE_NEW
        ]
        candidates.sort(key=lambda d: d["frequency_rank"])
        return candidates[:limit]

    async def count_graduated(self, user_id):
        return sum(
            1 for d in self.docs
            if d["user_id"] == user_id and d["my_state"] == "graduated"
        )

    async def graduated_ranks(self, user_id):
        return [
            d["frequency_rank"] for d in self.docs
            if d["user_id"] == user_id and d["my_state"] == "graduated"
        ]


class InMemoryReviewLogRepo:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def ensure_indexes(self):
        return None

    async def append(self, **fields):
        self.entries.append({**fields, "_id": ObjectId()})

    async def stats_for_window(self, user_id, since):
        good, total = 0, 0
        for e in self.entries:
            if e["user_id"] == user_id and e["reviewed_at"] >= since:
                total += 1
                if e["result"] == "good":
                    good += 1
        return good, total

    async def distinct_days(self, user_id, since):
        ts = [
            e["reviewed_at"] for e in self.entries
            if e["user_id"] == user_id and e["reviewed_at"] >= since
        ]
        return sorted(ts, reverse=True)


@pytest.fixture
def users_repo():
    return InMemoryUsersRepo()


@pytest.fixture
def cards_repo():
    return InMemoryCardsRepo()


@pytest.fixture
def review_log_repo():
    return InMemoryReviewLogRepo()


def make_words(n: int, start_rank: int = 1) -> list[dict[str, Any]]:
    words = []
    for i in range(n):
        rank = start_rank + i
        words.append({
            "_id": ObjectId(),
            "english": f"word{rank}",
            "translation": f"слово{rank}",
            "frequency_rank": rank,
            "pos": "noun",
            "example": "",
            "is_phrasal": False,
        })
    return words


@pytest.fixture
def words_factory():
    return make_words
