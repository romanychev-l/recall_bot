"""Integration tests for the repository layer against a real SQLite database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert

from bot.constants import STATE_GRADUATED, STATE_LEARNING, STATE_NEW, STATE_REVIEW
from bot.db.models import Word
from bot.domain.srs import SrsService
from bot.repositories.batches_repo import BatchesRepo
from bot.repositories.cards_repo import CardsRepo
from bot.repositories.review_log_repo import ReviewLogRepo
from bot.repositories.users_repo import UsersRepo
from bot.repositories.words_repo import WordsRepo

NOW = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
USER_ID = 555


async def _insert_words(session_factory, n: int = 5) -> None:
    async with session_factory() as s:
        await s.execute(
            insert(Word),
            [
                {
                    "english": f"word{i}",
                    "translation": f"слово{i}",
                    "frequency_rank": i,
                    "pos": "noun",
                    "example": "",
                    "is_phrasal": False,
                }
                for i in range(1, n + 1)
            ],
        )
        await s.commit()


async def _setup(session_factory, n_words: int = 5):
    """User + words + one batch of cards. Returns (repos, batch_id, cards)."""
    await _insert_words(session_factory, n_words)
    users = UsersRepo(session_factory)
    words = WordsRepo(session_factory)
    cards = CardsRepo(session_factory)
    batches = BatchesRepo(session_factory)
    await users.create_if_absent(USER_ID)
    batch_id = await batches.create(USER_ID, NOW)
    all_words = await words.next_n_with_rank_gte(1, n_words)
    created = await cards.bulk_create_new(
        USER_ID, all_words, batch_id, SrsService().new_card_dict, NOW
    )
    return users, words, cards, batches, batch_id, created


async def test_create_if_absent_is_idempotent(session_factory) -> None:
    users = UsersRepo(session_factory)
    first = await users.create_if_absent(USER_ID, initial_rank=42)
    second = await users.create_if_absent(USER_ID, initial_rank=99)
    assert first["id"] == second["id"] == USER_ID
    # Second call must not overwrite the existing row.
    assert second["initial_rank"] == 42
    assert len(await users.all()) == 1


async def test_datetimes_round_trip_tz_aware(session_factory) -> None:
    """Regression guard: SQLite drops tzinfo unless the type coerces it back."""
    users = UsersRepo(session_factory)
    await users.create_if_absent(USER_ID)
    user = await users.get(USER_ID)
    assert user["created_at"].tzinfo is not None
    assert user["created_at"].utcoffset() == timedelta(0)

    _, _, cards, _, _, created = await _setup(session_factory)
    card = await cards.get(USER_ID, created[0]["word_id"])
    assert card["due"].tzinfo is not None


async def test_words_ordering_and_lookup(session_factory) -> None:
    await _insert_words(session_factory, 10)
    words = WordsRepo(session_factory)
    assert await words.count() == 10
    page = await words.next_n_with_rank_gte(4, 3)
    assert [w["frequency_rank"] for w in page] == [4, 5, 6]
    by_ids = await words.by_ids([page[0]["id"], page[2]["id"]])
    assert {w["frequency_rank"] for w in by_ids} == {4, 6}
    assert await words.by_ids([]) == []


async def test_find_due_respects_due_state_and_skip(session_factory) -> None:
    _, _, cards, _, _, created = await _setup(session_factory, 4)
    # Cards start as "new" — find_due only looks at learning/review.
    assert await cards.find_due(USER_ID, NOW, 10) == []

    srs = SrsService()
    first, second = created[0], created[1]
    for card in (first, second):
        update = srs.review(
            fsrs_state=card["fsrs"],
            prev_my_state=STATE_NEW,
            prev_consecutive=0,
            first_reached_review_at=None,
            correct=False,  # wrong answer keeps it in learning
            now=NOW,
        )
        await cards.update_after_review(
            USER_ID,
            card["word_id"],
            fsrs=update.fsrs,
            my_state=update.my_state,
            consecutive_successes_at_review=0,
            first_reached_review_at=None,
            now=NOW,
        )

    later = NOW + timedelta(days=2)
    due = await cards.find_due(USER_ID, later, 10)
    assert {c["word_id"] for c in due} == {first["word_id"], second["word_id"]}

    # Skipping past `later` removes it from the due set.
    await cards.set_skip_until(USER_ID, first["word_id"], later + timedelta(days=1))
    due_after_skip = await cards.find_due(USER_ID, later, 10)
    assert {c["word_id"] for c in due_after_skip} == {second["word_id"]}


async def test_find_due_puts_hard_cards_first(session_factory) -> None:
    _, _, cards, _, _, created = await _setup(session_factory, 3)
    srs = SrsService()
    for card in created:
        update = srs.review(
            fsrs_state=card["fsrs"], prev_my_state=STATE_NEW, prev_consecutive=0,
            first_reached_review_at=None, correct=False, now=NOW,
        )
        await cards.update_after_review(
            USER_ID, card["word_id"], fsrs=update.fsrs, my_state=update.my_state,
            consecutive_successes_at_review=0, first_reached_review_at=None, now=NOW,
        )
    # Mark the lowest-priority word (highest rank) hard — it must jump the queue.
    hardest = created[-1]
    await cards.set_hard(USER_ID, hardest["word_id"], True)

    due = await cards.find_due(USER_ID, NOW + timedelta(days=2), 10)
    assert due[0]["word_id"] == hardest["word_id"]
    assert due[0]["is_hard"] is True


async def test_update_after_review_keeps_due_column_in_sync(session_factory) -> None:
    _, _, cards, _, _, created = await _setup(session_factory, 2)
    card = created[0]
    srs = SrsService()
    update = srs.review(
        fsrs_state=card["fsrs"], prev_my_state=STATE_NEW, prev_consecutive=0,
        first_reached_review_at=None, correct=True, now=NOW,
    )
    await cards.update_after_review(
        USER_ID, card["word_id"], fsrs=update.fsrs, my_state=update.my_state,
        consecutive_successes_at_review=1, first_reached_review_at=NOW, now=NOW,
    )
    fresh = await cards.get(USER_ID, card["word_id"])
    # The indexed column must match what is inside the JSON blob.
    assert fresh["due"] == datetime.fromisoformat(fresh["fsrs"]["due"])
    assert fresh["due"] > NOW


async def test_count_by_state_and_batch_helpers(session_factory) -> None:
    _, _, cards, _, batch_id, created = await _setup(session_factory, 4)
    counts = await cards.count_by_state(USER_ID)
    assert counts == {STATE_NEW: 4, STATE_LEARNING: 0, STATE_REVIEW: 0, STATE_GRADUATED: 0}
    assert await cards.count_pending_in_batch(USER_ID, batch_id) == 4

    in_batch = await cards.find_new_in_batch(USER_ID, batch_id, 2)
    assert [c["frequency_rank"] for c in in_batch] == [1, 2]

    srs = SrsService()
    update = srs.review(
        fsrs_state=created[0]["fsrs"], prev_my_state=STATE_NEW, prev_consecutive=0,
        first_reached_review_at=None, correct=True, now=NOW,
    )
    await cards.update_after_review(
        USER_ID, created[0]["word_id"], fsrs=update.fsrs, my_state=STATE_GRADUATED,
        consecutive_successes_at_review=5, first_reached_review_at=NOW, now=NOW,
    )
    assert await cards.count_graduated(USER_ID) == 1
    assert await cards.graduated_ranks(USER_ID) == [1]
    assert sorted(await cards.learned_ranks(USER_ID)) == [1]


async def test_review_log_stats_and_days(session_factory) -> None:
    _, _, _, _, batch_id, created = await _setup(session_factory, 2)
    log = ReviewLogRepo(session_factory)
    word_id = created[0]["word_id"]
    for result, days in [("good", 0), ("good", 0), ("again", 1), ("good", 3)]:
        await log.append(
            user_id=USER_ID, word_id=word_id, batch_id=batch_id,
            result=result, user_input="x", reviewed_at=NOW - timedelta(days=days),
        )
    good, total = await log.stats_for_window(USER_ID, NOW - timedelta(days=7))
    assert (good, total) == (3, 4)

    # Empty window must not blow up on SUM(NULL).
    assert await log.stats_for_window(USER_ID, NOW + timedelta(days=1)) == (0, 0)

    days = await log.distinct_days(USER_ID, NOW - timedelta(days=7))
    assert len(days) == 3  # today, -1, -3
    assert days == sorted(days, reverse=True)


async def test_set_current_batch_and_update(session_factory) -> None:
    users, _, _, _, batch_id, _ = await _setup(session_factory, 2)
    await users.set_current_batch(USER_ID, batch_id, 17)
    user = await users.get(USER_ID)
    assert user["current_batch_id"] == batch_id
    assert user["next_batch_start_rank"] == 17

    await users.update(USER_ID, batch_size=25, tz="UTC")
    user = await users.get(USER_ID)
    assert user["batch_size"] == 25 and user["tz"] == "UTC"

    # No-op update must not fail.
    await users.update(USER_ID)


async def test_missing_rows_return_none(session_factory) -> None:
    users = UsersRepo(session_factory)
    cards = CardsRepo(session_factory)
    words = WordsRepo(session_factory)
    assert await users.get(999) is None
    assert await words.by_id(999) is None
    assert await cards.get(999, 999) is None
    assert await cards.by_word_ids(999, []) == []
