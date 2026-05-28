from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bot.constants import (
    GRADUATION_MIN_CONSECUTIVE,
    STATE_GRADUATED,
    STATE_LEARNING,
    STATE_NEW,
    STATE_REVIEW,
)
from bot.domain.srs import SrsService


@pytest.fixture
def srs() -> SrsService:
    return SrsService()


def _now() -> datetime:
    return datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_new_card_due_at_now(srs: SrsService) -> None:
    now = _now()
    card = srs.new_card_dict(now)
    assert card["due"] == now


def test_first_correct_moves_to_learning(srs: SrsService) -> None:
    now = _now()
    card = srs.new_card_dict(now)
    update = srs.review(
        fsrs_state=card,
        prev_my_state=STATE_NEW,
        prev_consecutive=0,
        first_reached_review_at=None,
        correct=True,
        now=now,
    )
    assert update.my_state in (STATE_LEARNING, STATE_REVIEW)


def test_wrong_answer_resets_to_learning_and_zero_counter(srs: SrsService) -> None:
    now = _now()
    card = srs.new_card_dict(now)
    # Drive to review first
    fsrs = card
    state = STATE_NEW
    counter = 0
    first_review = None
    for step in range(4):
        cur = now + timedelta(days=step * 3)
        upd = srs.review(fsrs, state, counter, first_review, correct=True, now=cur)
        fsrs = upd.fsrs
        state = upd.my_state
        counter = upd.consecutive_successes_at_review
        first_review = upd.first_reached_review_at
        if state == STATE_REVIEW:
            break
    assert state == STATE_REVIEW

    # Now fail in review state
    upd = srs.review(
        fsrs, state, counter, first_review,
        correct=False, now=now + timedelta(days=30),
    )
    assert upd.my_state == STATE_LEARNING
    assert upd.consecutive_successes_at_review == 0


def test_graduation_requires_5_consecutive_at_30d(srs: SrsService) -> None:
    """After enough good answers with growing intervals, graduates."""
    now = _now()
    card = srs.new_card_dict(now)
    fsrs = card
    state = STATE_NEW
    counter = 0
    first_review = None
    cur = now
    # Simulate up to 30 good answers, advancing time to each card's due date.
    for _ in range(30):
        upd = srs.review(fsrs, state, counter, first_review, correct=True, now=cur)
        fsrs = upd.fsrs
        state = upd.my_state
        counter = upd.consecutive_successes_at_review
        first_review = upd.first_reached_review_at
        if state == STATE_GRADUATED:
            break
        # advance to due
        due = fsrs["due"]
        if isinstance(due, str):
            cur = datetime.fromisoformat(due)
        else:
            cur = due
    assert state == STATE_GRADUATED
    assert counter >= GRADUATION_MIN_CONSECUTIVE


def test_review_with_naive_stored_datetimes(srs: SrsService) -> None:
    """Regression: Mongo returns naive datetimes; reviewing with an aware `now`
    must not raise 'can't subtract offset-naive and offset-aware datetimes'."""
    now = _now()
    card = srs.new_card_dict(now)
    # First review populates last_review (tz-aware in memory)
    upd = srs.review(card, STATE_NEW, 0, None, correct=True, now=now)
    fsrs = upd.fsrs
    # Simulate a Mongo round-trip: BSON dates come back naive (UTC, no tzinfo)
    fsrs = {
        k: (v.replace(tzinfo=None) if isinstance(v, datetime) else v)
        for k, v in fsrs.items()
    }
    assert fsrs["last_review"] is not None and fsrs["last_review"].tzinfo is None

    # Second review with an aware `now` used to crash; now it must work.
    upd2 = srs.review(
        fsrs,
        upd.my_state,
        upd.consecutive_successes_at_review,
        upd.first_reached_review_at,
        correct=False,
        now=now + timedelta(days=2),
    )
    assert upd2.my_state in (STATE_LEARNING, STATE_REVIEW)


def test_consecutive_counter_only_increments_in_review(srs: SrsService) -> None:
    now = _now()
    card = srs.new_card_dict(now)
    # First answer (from new) — counter should stay 0 because prev_state was new
    upd = srs.review(card, STATE_NEW, 0, None, correct=True, now=now)
    assert upd.consecutive_successes_at_review == 0
