"""Regressions for real dictionary ordering and progress-safe re-ranking."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import insert, select

from bot.db.models import ReviewLog, Word
from bot.db.seed import seed_from_csv, seed_if_empty
from bot.domain.srs import SrsService
from bot.repositories.batches_repo import BatchesRepo
from bot.repositories.cards_repo import CardsRepo
from bot.repositories.review_log_repo import ReviewLogRepo
from bot.repositories.users_repo import UsersRepo
from bot.repositories.words_repo import WordsRepo
from bot.services.batch_service import BatchService
from data.rank_dictionary import rank_rows

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["english", "translation", "frequency_rank", "pos"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_shipped_dictionary_is_frequency_ranked():
    with (ROOT / "data/dictionary.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 20070
    assert len({row["english"] for row in rows}) == len(rows)
    assert [int(row["frequency_rank"]) for row in rows] == list(range(1, len(rows) + 1))
    words = [row for row in rows if row["is_phrasal"] == "false"]
    counts = [int(row["frequency_count"]) for row in words]
    assert counts == sorted(counts, reverse=True)
    assert all(count > 0 for count in counts)
    assert [row["english"] for row in rows[:6]] == ["you", "i", "the", "to", "a", "it"]
    ranks = {row["english"]: int(row["frequency_rank"]) for row in rows}
    assert ranks["know"] < ranks["account"] < ranks["apparatus"]
    assert all(row["is_phrasal"] == "true" for row in rows[len(words):])


def test_rank_rows_uses_counts_and_preserves_translations_and_phrases():
    rows = [dict(english=word, translation=f"перевод {word}", frequency_rank=rank,
                 pos="verb", is_phrasal=str(" " in word).lower())
            for rank, word in enumerate(["apple", "zebra", "go on", "act", "come in"], 1)]
    result = rank_rows(rows, {"apple": 50, "zebra": 100, "act": 10})
    assert [row["english"] for row in result] == ["zebra", "apple", "act", "go on", "come in"]
    assert {row["english"]: row["translation"] for row in result} == {row["english"]: row["translation"] for row in rows}
    with pytest.raises(ValueError, match="Missing corpus frequency"):
        rank_rows(rows, {"apple": 50})


async def setup_legacy(session_factory, tmp_path):
    old = [dict(english=word, translation=translation, frequency_rank=rank, pos="noun")
           for rank, (word, translation) in enumerate([
               ("account", "счёт"), ("act", "действие"), ("know", "знать"), ("you", "ты")], 1)]
    path = write_csv(tmp_path / "dictionary.csv", old)
    await seed_from_csv(session_factory, path)
    users, words, cards = UsersRepo(session_factory), WordsRepo(session_factory), CardsRepo(session_factory)
    batches = BatchesRepo(session_factory)
    await users.create_if_absent(1, initial_rank=1)
    await users.update(1, batch_size=2, daily_goal=1)
    batch = await batches.create(1, NOW)
    by_word = {row["english"]: row for row in await words.next_n_with_rank_gte(1, 100)}
    created = await cards.bulk_create_new(1, [by_word["account"], by_word["know"]], batch, SrsService().new_card_dict, NOW)
    for card in created:
        await cards.update_after_review(1, card["word_id"], fsrs=card["fsrs"], my_state="review",
                                        consecutive_successes_at_review=3, first_reached_review_at=NOW, now=NOW)
        await cards.set_hard(1, card["word_id"], True)
        await cards.set_skip_until(1, card["word_id"], NOW + timedelta(days=1))
    await users.set_current_batch(1, batch, 4)
    log = ReviewLogRepo(session_factory)
    await log.append(user_id=1, word_id=by_word["account"]["id"], batch_id=batch,
                     result="good", user_input="account", reviewed_at=NOW)
    new = [dict(row, frequency_rank={"you": 1, "know": 2, "act": 3, "account": 4}[row["english"]]) for row in old]
    write_csv(path, new)
    return path, users, words, cards, batches, by_word


async def test_startup_reranks_without_changing_identity_or_progress(session_factory, tmp_path):
    path, users, words, cards, _, old = await setup_legacy(session_factory, tmp_path)
    before = await cards.by_word_ids(1, [row["id"] for row in old.values()])
    async with session_factory() as session:
        logs = (await session.execute(select(ReviewLog.__table__))).mappings().all()
    # Startup only syncs ranks, not edited dictionary content.
    content = list(csv.DictReader(path.open()))
    content[0]["translation"] = "изменённый перевод"
    write_csv(path, content)
    assert await seed_if_empty(session_factory, path) == 0
    after = await cards.by_word_ids(1, [row["id"] for row in old.values()])
    assert [{k: v for k, v in c.items() if k != "frequency_rank"} for c in after] == [
        {k: v for k, v in c.items() if k != "frequency_rank"} for c in before]
    for word, previous in old.items():
        current = await words.by_id(previous["id"])
        assert current["english"] == word
        assert current["translation"] == previous["translation"]
    assert {c["frequency_rank"] for c in after} == {2, 4}
    assert (await users.get(1))["next_batch_start_rank"] == 1
    async with session_factory() as session:
        assert (await session.execute(select(ReviewLog.__table__))).mappings().all() == logs
    assert await seed_if_empty(session_factory, path) == 0
    assert await cards.by_word_ids(1, [row["id"] for row in old.values()]) == after


async def test_manual_and_automatic_batches_select_unseen_words_after_reranking(session_factory, tmp_path):
    path, users, words, cards, batches, old = await setup_legacy(session_factory, tmp_path)
    await seed_if_empty(session_factory, path)
    batch_service = BatchService(users, words, cards, batches, SrsService())
    # Simulate a stale user snapshot, as well as a persisted stale cursor.
    await users.update(1, next_batch_start_rank=999)
    user = await users.get(1)
    batch = await batch_service.issue_next_batch(user, now=NOW, size_override=1)
    allocated = await cards.find_new_in_batch(1, batch, 10)
    assert [c["word_id"] for c in allocated] == [old["you"]["id"]]
    assert [c["frequency_rank"] for c in allocated] == [1]
    card = allocated[0]
    await cards.update_after_review(1, card["word_id"], fsrs=card["fsrs"], my_state="review",
                                    consecutive_successes_at_review=0, first_reached_review_at=NOW, now=NOW)
    next_batch = await batch_service.maybe_issue_next_batch(1, batch)
    assert [c["word_id"] for c in await cards.find_new_in_batch(1, next_batch, 10)] == [old["act"]["id"]]
    assert await batch_service.issue_next_batch(await users.get(1)) is None


async def test_seed_reorders_and_inserts_by_english_identity(session_factory, tmp_path):
    path, _, words, cards, _, old = await setup_legacy(session_factory, tmp_path)
    rows = list(csv.DictReader(path.open()))
    rows.append(dict(english="zebra", translation="зебра", frequency_rank=5, pos="noun"))
    write_csv(path, rows)
    assert await seed_from_csv(session_factory, path) == (1, 4)
    assert await words.count() == 5
    for word, previous in old.items():
        assert (await words.by_id(previous["id"]))["english"] == word
    assert {c["frequency_rank"] for c in await cards.by_word_ids(1, [w["id"] for w in old.values()])} == {2, 4}
    assert await seed_from_csv(session_factory, path) == (0, 5)


@pytest.mark.parametrize("bad", ["rank", "english", "collision"])
async def test_ambiguous_seed_is_rejected_without_partial_writes(session_factory, tmp_path, bad):
    path, _, words, _, _, _ = await setup_legacy(session_factory, tmp_path)
    before = await words.next_n_with_rank_gte(1, 100)
    rows = list(csv.DictReader(path.open()))
    if bad == "rank":
        rows[0]["frequency_rank"] = rows[1]["frequency_rank"]
    elif bad == "english":
        rows[0]["english"] = rows[1]["english"]
    else:
        rows = [dict(rows[0], frequency_rank=2)]  # rank still belongs to "act"
    write_csv(path, rows)
    with pytest.raises(ValueError):
        await seed_from_csv(session_factory, path)
    assert await words.next_n_with_rank_gte(1, 100) == before


async def test_startup_preserves_supplementary_words_and_initial_level(session_factory, tmp_path):
    path, users, words, _, _, _ = await setup_legacy(session_factory, tmp_path)
    async with session_factory() as session:
        await session.execute(insert(Word).values(english="custom phrase", translation="фраза", frequency_rank=30001))
        await session.commit()
    await users.create_if_absent(2, initial_rank=3)
    await users.update(2, next_batch_start_rank=999)
    await seed_if_empty(session_factory, path)
    available = await words.next_available(2, 3, 10)
    assert [row["english"] for row in available] == ["act", "account", "custom phrase"]
    assert (await users.get(2))["next_batch_start_rank"] == 3
    assert await words.count() == 5
