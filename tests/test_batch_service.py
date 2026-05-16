from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.constants import STATE_NEW, STATE_REVIEW
from bot.domain.srs import SrsService
from bot.services.batch_service import BatchService
from tests.conftest import InMemoryWordsRepo, make_words


@pytest.mark.asyncio
async def test_issue_first_batch(users_repo, cards_repo) -> None:
    words = make_words(50)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)

    await users_repo.create_if_absent(1, initial_rank=10)
    user = await users_repo.get(1)
    user["batch_size"] = 5
    await users_repo.update(1, batch_size=5)
    user = await users_repo.get(1)
    assert user["next_batch_start_rank"] == 10

    batch_id = await batch.issue_next_batch(user, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert batch_id is not None
    refreshed = await users_repo.get(1)
    assert refreshed["current_batch_id"] == batch_id
    assert refreshed["next_batch_start_rank"] == 15  # 10..14 issued, next starts at 15
    assert len(cards_repo.docs) == 5
    assert all(d["my_state"] == STATE_NEW for d in cards_repo.docs)


@pytest.mark.asyncio
async def test_maybe_issue_next_batch_no_op_if_pending(users_repo, cards_repo) -> None:
    words = make_words(20)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    await users_repo.create_if_absent(1)
    user = await users_repo.get(1)
    user["batch_size"] = 5
    await users_repo.update(1, batch_size=5)
    user = await users_repo.get(1)
    bid = await batch.issue_next_batch(user)
    assert bid is not None
    # Some cards still pending — maybe_issue should NOT issue
    new_bid = await batch.maybe_issue_next_batch(1, bid)
    assert new_bid is None


@pytest.mark.asyncio
async def test_maybe_issue_next_batch_progresses_when_all_review(
    users_repo, cards_repo
) -> None:
    words = make_words(20)
    words_repo = InMemoryWordsRepo(words)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    await users_repo.create_if_absent(1)
    await users_repo.update(1, batch_size=3)
    user = await users_repo.get(1)
    bid = await batch.issue_next_batch(user)
    # Force all to review
    for d in cards_repo.docs:
        d["my_state"] = STATE_REVIEW
    new_bid = await batch.maybe_issue_next_batch(1, bid)
    assert new_bid is not None
    assert new_bid != bid
    # 3 new cards added in new batch
    assert sum(1 for d in cards_repo.docs if d["batch_id"] == new_bid) == 3
