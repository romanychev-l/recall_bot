from __future__ import annotations

import logging
from datetime import datetime, timezone

from bot.repositories.users_repo import UsersRepo
from bot.services.batch_service import BatchService

logger = logging.getLogger(__name__)


class OnboardingService:
    def __init__(
        self,
        users_repo: UsersRepo,
        batch_service: BatchService,
    ) -> None:
        self.users_repo = users_repo
        self.batch_service = batch_service

    async def start(
        self,
        telegram_id: int,
        *,
        initial_rank: int = 0,
        language: str = "ru",
        batch_size: int | None = None,
    ) -> dict:
        user = await self.users_repo.create_if_absent(
            telegram_id, initial_rank=initial_rank, language=language
        )
        updates: dict = {}
        if batch_size is not None and batch_size != user["batch_size"]:
            updates["batch_size"] = batch_size
        if user["initial_rank"] != initial_rank and user.get("current_batch_id") is None:
            updates["initial_rank"] = initial_rank
            updates["next_batch_start_rank"] = initial_rank
        if updates:
            await self.users_repo.update(telegram_id, **updates)
            user.update(updates)

        if user.get("current_batch_id") is None:
            await self.batch_service.issue_next_batch(user, now=datetime.now(timezone.utc))
        logger.info(
            "user_onboarded user_id=%s initial_rank=%s batch_size=%s",
            telegram_id, user["initial_rank"], user["batch_size"],
        )
        return await self.users_repo.get(telegram_id)  # type: ignore[return-value]
