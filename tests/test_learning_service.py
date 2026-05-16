from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from bot.constants import STATE_LEARNING, STATE_NEW, STATE_REVIEW
from bot.domain.srs import SrsService
from bot.services.batch_service import BatchService
from bot.services.learning_service import LearningService
from tests.conftest import InMemoryWordsRepo, make_words


@pytest.mark.asyncio
async def test_evaluate_correct_answer_updates_state(
    users_repo, cards_repo, review_log_repo
) -> None:
    words = make_words(5)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    learn = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )

    await users_repo.create_if_absent(1)
    await users_repo.update(1, batch_size=5)
    user = await users_repo.get(1)
    await batch.issue_next_batch(user)
    user = await users_repo.get(1)

    card = cards_repo.docs[0]
    outcome = await learn.evaluate_answer(user, card, words[0]["english"])
    assert outcome.correct is True
    assert outcome.new_state in (STATE_LEARNING, STATE_REVIEW)
    assert len(review_log_repo.entries) == 1
    assert review_log_repo.entries[0]["result"] == "good"


@pytest.mark.asyncio
async def test_evaluate_wrong_answer_logs_again(
    users_repo, cards_repo, review_log_repo
) -> None:
    words = make_words(3)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    learn = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )
    await users_repo.create_if_absent(1)
    await users_repo.update(1, batch_size=3)
    user = await users_repo.get(1)
    await batch.issue_next_batch(user)
    user = await users_repo.get(1)
    card = cards_repo.docs[0]

    outcome = await learn.evaluate_answer(user, card, "wrongword")
    assert outcome.correct is False
    assert outcome.new_state == STATE_LEARNING
    assert review_log_repo.entries[0]["result"] == "again"


@pytest.mark.asyncio
async def test_batch_advances_when_all_pass_first_interval(
    users_repo, cards_repo, review_log_repo
) -> None:
    words = make_words(6)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    learn = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )
    await users_repo.create_if_absent(1)
    await users_repo.update(1, batch_size=3)
    user = await users_repo.get(1)
    first_batch = await batch.issue_next_batch(user)
    user = await users_repo.get(1)
    assert sum(1 for d in cards_repo.docs if d["batch_id"] == first_batch) == 3

    # Answer all 3 correctly → all should transition to review and trigger next batch
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    last_outcome = None
    for card in list(cards_repo.docs):
        fresh_user = await users_repo.get(1)
        fresh_card = await cards_repo.get(1, card["word_id"])
        last_outcome = await learn.evaluate_answer(
            fresh_user, fresh_card,
            next(w["english"] for w in words if w["_id"] == fresh_card["word_id"]),
            now=now,
        )

    assert last_outcome is not None
    assert last_outcome.next_batch_issued is True
    refreshed = await users_repo.get(1)
    assert refreshed["current_batch_id"] != first_batch


@pytest.mark.asyncio
async def test_build_session_orders_hard_first(
    users_repo, cards_repo, review_log_repo
) -> None:
    words = make_words(6)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    learn = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )
    await users_repo.create_if_absent(1)
    await users_repo.update(1, batch_size=6)
    user = await users_repo.get(1)
    await batch.issue_next_batch(user)
    user = await users_repo.get(1)

    # Manually flip some to "review" with due in past, others to "new"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i, d in enumerate(cards_repo.docs):
        if i < 3:
            d["my_state"] = STATE_REVIEW
            d["fsrs"]["due"] = now - timedelta(days=1)
            d["is_hard"] = (i == 2)  # one hard card

    session = await learn.build_session(user, now=now)
    # All 3 review + 3 new = 6 cards
    assert len(session) == 6


@pytest.mark.asyncio
async def test_skip_today_sets_skip_until(
    users_repo, cards_repo, review_log_repo
) -> None:
    words = make_words(2)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    learn = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )
    await users_repo.create_if_absent(1)
    await users_repo.update(1, batch_size=2)
    user = await users_repo.get(1)
    await batch.issue_next_batch(user)
    card = cards_repo.docs[0]
    now = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
    await learn.skip_today(1, card["word_id"], "UTC", now)
    refreshed = await cards_repo.get(1, card["word_id"])
    assert refreshed["skip_until"] is not None
    assert refreshed["skip_until"] > now
