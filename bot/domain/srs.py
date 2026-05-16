from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fsrs import Card, Rating, Scheduler, State

from bot.constants import (
    GRADUATION_MIN_CONSECUTIVE,
    GRADUATION_MIN_INTERVAL_DAYS,
    STATE_GRADUATED,
    STATE_LEARNING,
    STATE_NEW,
    STATE_REVIEW,
)


@dataclass
class CardUpdate:
    fsrs: dict[str, Any]
    my_state: str
    consecutive_successes_at_review: int
    first_reached_review_at: Optional[datetime]
    interval_days: float


def _card_to_doc(card: Card) -> dict[str, Any]:
    """Serialize a Card to a Mongo-friendly dict (datetimes stay as datetime)."""
    return {
        "card_id": card.card_id,
        "state": int(card.state) if hasattr(card.state, "value") else int(card.state),
        "step": card.step,
        "stability": card.stability,
        "difficulty": card.difficulty,
        "due": card.due,
        "last_review": card.last_review,
    }


def _card_from_doc(doc: dict[str, Any]) -> Card:
    due = doc.get("due")
    last_review = doc.get("last_review")
    if isinstance(due, str):
        due = datetime.fromisoformat(due)
    if isinstance(last_review, str):
        last_review = datetime.fromisoformat(last_review)
    state = doc.get("state")
    if isinstance(state, int):
        state = State(state)
    return Card(
        card_id=doc.get("card_id"),
        state=state,
        step=doc.get("step"),
        stability=doc.get("stability"),
        difficulty=doc.get("difficulty"),
        due=due,
        last_review=last_review,
    )


def _interval_days(card: Card) -> float:
    if card.last_review is None or card.due is None:
        return 0.0
    return max(0.0, (card.due - card.last_review).total_seconds() / 86400.0)


def build_scheduler() -> Scheduler:
    return Scheduler(
        learning_steps=(timedelta(days=1),),
        relearning_steps=(timedelta(days=1),),
    )


class SrsService:
    """Wraps py-fsrs Scheduler with our 4-state model.

    Mapping:
      - Pass binary rating: correct → Rating.Good, wrong → Rating.Again.
      - FSRS State.Learning / State.Relearning → my_state "learning".
      - FSRS State.Review → my_state "review", upgraded to "graduated" once the
        user has 5 consecutive successes at interval ≥ 30 days.
    """

    def __init__(self, scheduler: Optional[Scheduler] = None) -> None:
        self.scheduler = scheduler or build_scheduler()

    def new_card_dict(self, now: datetime) -> dict[str, Any]:
        return _card_to_doc(Card(due=now))

    def review(
        self,
        fsrs_state: dict[str, Any],
        prev_my_state: str,
        prev_consecutive: int,
        first_reached_review_at: Optional[datetime],
        correct: bool,
        now: datetime,
    ) -> CardUpdate:
        card = _card_from_doc(fsrs_state)
        rating = Rating.Good if correct else Rating.Again
        card, _log = self.scheduler.review_card(card, rating, now)

        counter = prev_consecutive
        if not correct:
            counter = 0
        elif prev_my_state == STATE_REVIEW:
            counter += 1
        elif prev_my_state in (STATE_NEW, STATE_LEARNING):
            counter = 0

        if card.state in (State.Learning, State.Relearning):
            my_state = STATE_LEARNING
            if prev_my_state == STATE_REVIEW:
                counter = 0
        elif card.state == State.Review:
            interval = _interval_days(card)
            if counter >= GRADUATION_MIN_CONSECUTIVE and interval >= GRADUATION_MIN_INTERVAL_DAYS:
                my_state = STATE_GRADUATED
            else:
                my_state = STATE_REVIEW
        else:
            my_state = STATE_LEARNING

        first_review = first_reached_review_at
        if my_state in (STATE_REVIEW, STATE_GRADUATED) and first_review is None:
            first_review = now

        return CardUpdate(
            fsrs=_card_to_doc(card),
            my_state=my_state,
            consecutive_successes_at_review=counter,
            first_reached_review_at=first_review,
            interval_days=_interval_days(card),
        )


def card_due(fsrs_state: dict[str, Any]) -> datetime:
    due = fsrs_state.get("due")
    if isinstance(due, datetime):
        return due
    if isinstance(due, str):
        return datetime.fromisoformat(due)
    return datetime.now(timezone.utc)
