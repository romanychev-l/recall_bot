from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, insert, or_, select, update

from bot.constants import (
    STATE_GRADUATED,
    STATE_LEARNING,
    STATE_NEW,
    STATE_REVIEW,
)
from bot.db.models import UserCard
from bot.domain.srs import card_due
from bot.repositories.base import BaseRepo, one, rows


def _fsrs_for_storage(fsrs: dict[str, Any]) -> dict[str, Any]:
    """Make an FSRS state dict JSON-serializable.

    ``SrsService`` hands back real datetimes for ``due``/``last_review``; JSON
    columns cannot hold those. Store them as ISO strings — ``_card_from_doc``
    already parses that form back.
    """
    return {
        key: (value.isoformat() if isinstance(value, datetime) else value)
        for key, value in fsrs.items()
    }


class CardsRepo(BaseRepo):
    async def get(self, user_id: int, word_id: int) -> Optional[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.__table__).where(
                    UserCard.user_id == user_id, UserCard.word_id == word_id
                )
            )
            return one(res)

    async def by_word_ids(
        self, user_id: int, word_ids: list[int]
    ) -> list[dict[str, Any]]:
        if not word_ids:
            return []
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.__table__).where(
                    UserCard.user_id == user_id, UserCard.word_id.in_(word_ids)
                )
            )
            return rows(res)

    async def bulk_create_new(
        self,
        user_id: int,
        words: list[dict[str, Any]],
        batch_id: int,
        fsrs_factory,
        now: datetime,
    ) -> list[dict[str, Any]]:
        if not words:
            return []
        payload = []
        for w in words:
            fsrs = _fsrs_for_storage(fsrs_factory(now))
            payload.append({
                "user_id": user_id,
                "word_id": w["id"],
                "batch_id": batch_id,
                "frequency_rank": w["frequency_rank"],
                "fsrs": fsrs,
                "due": card_due(fsrs),
                "my_state": STATE_NEW,
                "consecutive_successes_at_review": 0,
                "first_reached_review_at": None,
                "is_hard": False,
                "skip_until": None,
                "created_at": now,
                "updated_at": now,
            })
        async with self._sf() as s:
            await s.execute(insert(UserCard), payload)
            await s.commit()
        return await self.by_word_ids(user_id, [w["id"] for w in words])

    async def update_after_review(
        self,
        user_id: int,
        word_id: int,
        *,
        fsrs: dict[str, Any],
        my_state: str,
        consecutive_successes_at_review: int,
        first_reached_review_at: Optional[datetime],
        now: datetime,
    ) -> None:
        stored = _fsrs_for_storage(fsrs)
        async with self._sf() as s:
            await s.execute(
                update(UserCard)
                .where(UserCard.user_id == user_id, UserCard.word_id == word_id)
                .values(
                    fsrs=stored,
                    # Keep the indexed column in step with the blob.
                    due=card_due(stored),
                    my_state=my_state,
                    consecutive_successes_at_review=consecutive_successes_at_review,
                    first_reached_review_at=first_reached_review_at,
                    updated_at=now,
                )
            )
            await s.commit()

    async def set_hard(self, user_id: int, word_id: int, value: bool) -> None:
        async with self._sf() as s:
            await s.execute(
                update(UserCard)
                .where(UserCard.user_id == user_id, UserCard.word_id == word_id)
                .values(is_hard=value, updated_at=datetime.now(timezone.utc))
            )
            await s.commit()

    async def set_skip_until(
        self, user_id: int, word_id: int, until: datetime
    ) -> None:
        async with self._sf() as s:
            await s.execute(
                update(UserCard)
                .where(UserCard.user_id == user_id, UserCard.word_id == word_id)
                .values(skip_until=until, updated_at=datetime.now(timezone.utc))
            )
            await s.commit()

    async def count_pending_in_batch(self, user_id: int, batch_id: int) -> int:
        async with self._sf() as s:
            res = await s.execute(
                select(func.count())
                .select_from(UserCard.__table__)
                .where(
                    UserCard.user_id == user_id,
                    UserCard.batch_id == batch_id,
                    UserCard.my_state.in_([STATE_NEW, STATE_LEARNING]),
                )
            )
            return int(res.scalar_one())

    async def find_due(
        self, user_id: int, now: datetime, limit: int
    ) -> list[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.__table__)
                .where(
                    UserCard.user_id == user_id,
                    UserCard.my_state.in_([STATE_LEARNING, STATE_REVIEW]),
                    UserCard.due <= now,
                    or_(
                        UserCard.skip_until.is_(None),
                        UserCard.skip_until <= now,
                    ),
                )
                # Hard cards first, then most frequent words.
                .order_by(
                    UserCard.is_hard.desc(), UserCard.frequency_rank.asc()
                )
                .limit(limit)
            )
            return rows(res)

    async def find_new_in_batch(
        self, user_id: int, batch_id: int, limit: int
    ) -> list[dict[str, Any]]:
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.__table__)
                .where(
                    UserCard.user_id == user_id,
                    UserCard.batch_id == batch_id,
                    UserCard.my_state == STATE_NEW,
                )
                .order_by(UserCard.frequency_rank.asc())
                .limit(limit)
            )
            return rows(res)

    async def count_graduated(self, user_id: int) -> int:
        async with self._sf() as s:
            res = await s.execute(
                select(func.count())
                .select_from(UserCard.__table__)
                .where(
                    UserCard.user_id == user_id,
                    UserCard.my_state == STATE_GRADUATED,
                )
            )
            return int(res.scalar_one())

    async def count_by_state(self, user_id: int) -> dict[str, int]:
        """Return {state: count} for all four states."""
        out = {
            STATE_NEW: 0,
            STATE_LEARNING: 0,
            STATE_REVIEW: 0,
            STATE_GRADUATED: 0,
        }
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.my_state, func.count())
                .where(UserCard.user_id == user_id)
                .group_by(UserCard.my_state)
            )
            for state, count in res.all():
                out[state] = int(count)
        return out

    async def graduated_ranks(self, user_id: int) -> list[int]:
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.frequency_rank).where(
                    UserCard.user_id == user_id,
                    UserCard.my_state == STATE_GRADUATED,
                )
            )
            return [int(r) for r in res.scalars()]

    async def learned_ranks(self, user_id: int) -> list[int]:
        """Ranks of cards in review OR graduated state — 'made it past first interval'."""
        async with self._sf() as s:
            res = await s.execute(
                select(UserCard.frequency_rank).where(
                    UserCard.user_id == user_id,
                    UserCard.my_state.in_([STATE_REVIEW, STATE_GRADUATED]),
                )
            )
            return [int(r) for r in res.scalars()]
