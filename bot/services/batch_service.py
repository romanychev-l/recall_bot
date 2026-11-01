from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bot.domain.parts_of_speech import ALL_POS
from bot.domain.srs import SrsService
from bot.repositories.batches_repo import BatchesRepo
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
        batches_repo: BatchesRepo,
        srs: SrsService,
    ) -> None:
        self.users_repo = users_repo
        self.words_repo = words_repo
        self.cards_repo = cards_repo
        self.batches_repo = batches_repo
        self.srs = srs

    async def issue_next_batch(
        self,
        user: dict,
        now: Optional[datetime] = None,
        size_override: Optional[int] = None,
    ) -> Optional[int]:
        now = now or datetime.now(timezone.utc)
        # Revisit words skipped by older filters; never allocate an existing card.
        start_rank = user.get("initial_rank", 0)
        size = size_override or user["batch_size"]
        pos_filter = user.get("pos_filter", ALL_POS)
        words = await self.words_repo.next_available(user["id"], start_rank, size, pos_filter)
        if not words:
            logger.info("no_more_words user_id=%s start_rank=%s", user["id"], start_rank)
            return None
        batch_id = await self.batches_repo.create(user["id"], now)
        words = [{**word, "study_pos_filter": pos_filter} for word in words]
        await self.cards_repo.bulk_create_new(
            user["id"], words, batch_id, self.srs.new_card_dict, now
        )
        next_start = max(
            user.get("next_batch_start_rank", start_rank),
            max(w["frequency_rank"] for w in words) + 1,
        )
        await self.users_repo.set_current_batch(user["id"], batch_id, next_start)
        logger.info(
            "batch_issued user_id=%s batch_id=%s size=%s next_start=%s",
            user["id"], batch_id, len(words), next_start,
        )
        return batch_id

    async def maybe_issue_next_batch(
        self, user_id: int, batch_id: int
    ) -> Optional[int]:
        user = await self.users_repo.get(user_id)
        if user is None:
            return None
        pending = await self.cards_repo.count_pending_in_batch(
            user_id, batch_id, user.get("pos_filter", ALL_POS)
        )
        if pending > 0:
            return None
        return await self.issue_next_batch(user)
