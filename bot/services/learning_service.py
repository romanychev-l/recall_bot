from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from bot.constants import RESULT_AGAIN, RESULT_GOOD, STATE_LEARNING, STATE_REVIEW
from bot.domain.matching import is_correct
from bot.domain.srs import SrsService
from bot.repositories.cards_repo import CardsRepo
from bot.repositories.review_log_repo import ReviewLogRepo
from bot.repositories.users_repo import UsersRepo
from bot.repositories.words_repo import WordsRepo
from bot.services.batch_service import BatchService

logger = logging.getLogger(__name__)


@dataclass
class AnswerOutcome:
    correct: bool
    correct_english: str
    new_state: str
    transitioned_to_review: bool
    next_batch_issued: bool


class LearningService:
    def __init__(
        self,
        users_repo: UsersRepo,
        words_repo: WordsRepo,
        cards_repo: CardsRepo,
        review_log_repo: ReviewLogRepo,
        srs: SrsService,
        batch_service: BatchService,
    ) -> None:
        self.users_repo = users_repo
        self.words_repo = words_repo
        self.cards_repo = cards_repo
        self.review_log_repo = review_log_repo
        self.srs = srs
        self.batch_service = batch_service

    async def build_session(
        self,
        user: dict,
        now: Optional[datetime] = None,
        cap: Optional[int] = None,
    ) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        cap = cap or user.get("daily_goal", user["batch_size"])
        due = await self.cards_repo.find_due(user["_id"], now, cap)
        remaining = max(0, cap - len(due))
        new_cards: list[dict] = []
        if user.get("current_batch_id") is not None and remaining > 0:
            new_cards = await self.cards_repo.find_new_in_batch(
                user["_id"], user["current_batch_id"], remaining
            )
        session = list(due) + list(new_cards)
        random.shuffle(session)
        return session

    async def evaluate_answer(
        self,
        user: dict,
        card: dict,
        user_input: str,
        now: Optional[datetime] = None,
    ) -> AnswerOutcome:
        now = now or datetime.now(timezone.utc)
        word = await self.words_repo.by_id(card["word_id"])
        if word is None:
            raise ValueError(f"word {card['word_id']} not found")

        correct = is_correct(user_input, word["english"])
        prev_state = card["my_state"]
        update = self.srs.review(
            fsrs_state=card["fsrs"],
            prev_my_state=prev_state,
            prev_consecutive=card.get("consecutive_successes_at_review", 0),
            first_reached_review_at=card.get("first_reached_review_at"),
            correct=correct,
            now=now,
        )
        await self.cards_repo.update_after_review(
            user["_id"],
            card["word_id"],
            fsrs=update.fsrs,
            my_state=update.my_state,
            consecutive_successes_at_review=update.consecutive_successes_at_review,
            first_reached_review_at=update.first_reached_review_at,
            now=now,
        )
        await self.review_log_repo.append(
            user_id=user["_id"],
            word_id=card["word_id"],
            batch_id=card["batch_id"],
            result=RESULT_GOOD if correct else RESULT_AGAIN,
            user_input=user_input,
            reviewed_at=now,
        )
        transitioned = prev_state in ("new", STATE_LEARNING) and update.my_state == STATE_REVIEW
        next_batch_issued = False
        if transitioned and card["batch_id"] == user.get("current_batch_id"):
            issued = await self.batch_service.maybe_issue_next_batch(
                user["_id"], card["batch_id"]
            )
            next_batch_issued = issued is not None
        logger.info(
            "answer user_id=%s word_id=%s correct=%s new_state=%s",
            user["_id"], card["word_id"], correct, update.my_state,
        )
        return AnswerOutcome(
            correct=correct,
            correct_english=word["english"],
            new_state=update.my_state,
            transitioned_to_review=transitioned,
            next_batch_issued=next_batch_issued,
        )

    async def skip_today(
        self, user_id: int, word_id: ObjectId, user_tz: str, now: datetime
    ) -> None:
        from zoneinfo import ZoneInfo

        local_now = now.astimezone(ZoneInfo(user_tz))
        end_of_day_local = local_now.replace(hour=23, minute=59, second=59, microsecond=0)
        await self.cards_repo.set_skip_until(
            user_id, word_id, end_of_day_local.astimezone(timezone.utc)
        )

    async def mark_hard(self, user_id: int, word_id: ObjectId, value: bool = True) -> None:
        await self.cards_repo.set_hard(user_id, word_id, value)
