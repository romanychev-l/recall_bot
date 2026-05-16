from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from bot.domain.srs import SrsService
from bot.repositories.cards_repo import CardsRepo
from bot.repositories.users_repo import UsersRepo
from bot.repositories.words_repo import WordsRepo

logger = logging.getLogger(__name__)


class BatchService:
    def __init__(
        self,
        users_repo: UsersRepo,
        words_repo: WordsRepo,
        cards_repo: CardsRepo,
        srs: SrsService,
    ) -> None:
        self.users_repo = users_repo
        self.words_repo = words_repo
        self.cards_repo = cards_repo
        self.srs = srs

    async def issue_next_batch(
        self, user: dict, now: Optional[datetime] = None
    ) -> Optional[ObjectId]:
        now = now or datetime.now(timezone.utc)
        start_rank = user.get("next_batch_start_rank", user.get("initial_rank", 0))
        words = await self.words_repo.next_n_with_rank_gte(
            start_rank, user["batch_size"]
        )
        if not words:
            logger.info("no_more_words user_id=%s start_rank=%s", user["_id"], start_rank)
            return None
        batch_id = ObjectId()
        await self.cards_repo.bulk_create_new(
            user["_id"], words, batch_id, self.srs.new_card_dict, now
        )
        next_start = max(w["frequency_rank"] for w in words) + 1
        await self.users_repo.set_current_batch(user["_id"], batch_id, next_start)
        logger.info(
            "batch_issued user_id=%s batch_id=%s size=%s next_start=%s",
            user["_id"], batch_id, len(words), next_start,
        )
        return batch_id

    async def maybe_issue_next_batch(
        self, user_id: int, batch_id: ObjectId
    ) -> Optional[ObjectId]:
        pending = await self.cards_repo.count_pending_in_batch(user_id, batch_id)
        if pending > 0:
            return None
        user = await self.users_repo.get(user_id)
        if user is None:
            return None
        return await self.issue_next_batch(user)
