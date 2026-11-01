"""Meaning-level filtering against SQLite, including persistent card progress."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import insert, select, update

from bot.container import build_container
from bot.db.models import UserCard, Word, WordSense
from bot.db.seed import seed_from_csv, seed_word_senses
from bot.domain.parts_of_speech import ALL_POS, POS_BITS, pos_mask, study_word
from bot.repositories.users_repo import UsersRepo
from data.build_word_senses import build_senses

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
NOUN, VERB, ADV = (POS_BITS[p] for p in ("noun", "verb", "adv"))


@pytest.fixture
async def vocabulary(session_factory):
    words = [
        ("light", "свет", "noun"), ("light", "зажигать", "verb"),
        ("back", "спина; назад", "noun"), ("quiet", "тихий", "adj"),
        ("mystery", "неизвестно", ""), ("can", "мочь", "modal"),
    ]
    async with session_factory() as session:
        await session.execute(insert(Word), [dict(id=index, frequency_rank=index,
            english=en, translation=ru, pos=pos) for index, (en, ru, pos) in enumerate(words, 1)])
        await session.execute(insert(WordSense), [
            dict(word_id=3, position=0, translation="спина", pos_mask=NOUN),
            dict(word_id=3, position=1, translation="назад", pos_mask=ADV),
        ])
        await session.commit()
    container = build_container(session_factory, scheduler=None, send_reminder=AsyncMock())
    await container.users_repo.create_if_absent(1, initial_rank=1)
    await container.users_repo.update(1, batch_size=10, daily_goal=10)
    return container


@pytest.mark.parametrize("mask,expected", [
    (ALL_POS, [1, 2, 3, 4, 5, 6]), (NOUN, [1, 3]), (VERB, [2, 6]),
    (NOUN | VERB, [1, 2, 3, 6]), (NOUN | ADV, [1, 3]), (ADV, [3]),
    (POS_BITS["other"], [5]),
])
async def test_or_matching_and_count_use_card_meanings(vocabulary, mask, expected):
    words = vocabulary.words_repo
    candidates = await words.next_available(1, 1, 50, mask)
    assert [word["id"] for word in candidates] == expected
    assert await words.available_count(1, 1, mask) == len(expected)
    for word in candidates:
        prompt = study_word(word, await words.senses(word["id"]), mask)
        if word["id"] == 3 and mask == ADV:
            assert prompt["translation"] == "назад"
            assert prompt["pos"] == "adv"
        if word["id"] == 3 and mask == NOUN:
            assert prompt["translation"] == "спина"


async def test_filter_switch_recovers_skipped_ranks_without_duplicates(vocabulary, session_factory):
    c = vocabulary
    for mask, expected, remaining in [(NOUN, {1, 3}, 0), (VERB, {2, 6}, 0), (ALL_POS, {4, 5}, 0)]:
        await c.users_repo.update(1, pos_filter=mask)
        assert (await UsersRepo(session_factory).get(1))["pos_filter"] == mask
        user = await c.users_repo.get(1)
        count = await c.words_repo.available_count(1, 1, mask)
        batch = await c.batch.issue_next_batch(user, now=NOW)
        cards = await c.cards_repo.find_new_in_batch(1, batch, 20)
        assert {card["word_id"] for card in cards} == expected
        assert count == len(cards)
        assert all(card["study_pos_filter"] == mask for card in cards)
        assert await c.words_repo.available_count(1, 1, mask) == remaining
    # New repository instance simulates a restart; preferences live in SQLite.
    assert (await UsersRepo(session_factory).get(1))["pos_filter"] == ALL_POS


async def test_counter_excludes_cards_and_onboarding_skip(vocabulary):
    c = vocabulary
    await c.users_repo.update(1, initial_rank=4, pos_filter=ALL_POS)
    user = await c.users_repo.get(1)
    assert await c.words_repo.available_count(1, 4, ALL_POS) == 3
    batch = await c.batch.issue_next_batch(user, now=NOW, size_override=2)
    cards = await c.cards_repo.find_new_in_batch(1, batch, 20)
    assert {card["word_id"] for card in cards} == {4, 5}
    assert await c.words_repo.available_count(1, 4, ALL_POS) == 1
    # Another learner's cards do not reduce this user's counter.
    assert await c.words_repo.available_count(2, 1, ALL_POS) == 6


async def test_issued_new_and_due_cards_hide_and_return_without_changes(vocabulary, session_factory):
    c = vocabulary
    batch = await c.batch.issue_next_batch(await c.users_repo.get(1), now=NOW)
    async with session_factory() as session:
        await session.execute(update(UserCard).where(UserCard.word_id.in_([2, 3])).values(
            my_state="review", due=NOW - timedelta(days=1), consecutive_successes_at_review=3))
        await session.commit()
    before = await c.cards_repo.by_word_ids(1, [1, 2, 3, 4, 5, 6])
    for mask, expected in [(ADV, {3}), (VERB, {2, 6}), (NOUN, {1, 3}), (ALL_POS, set(range(1, 7)))]:
        await c.users_repo.update(1, pos_filter=mask)
        user = await c.users_repo.get(1)
        cards = await c.learning.build_session(user, now=NOW, cap=20)
        assert {card["word_id"] for card in cards} == expected
        new = await c.cards_repo.find_new_in_batch(1, batch, 20, mask)
        assert {card["word_id"] for card in new} == expected - {2, 3}
    assert await c.cards_repo.by_word_ids(1, [1, 2, 3, 4, 5, 6]) == before


async def test_card_keeps_issued_meaning_when_filter_changes(vocabulary):
    c = vocabulary
    await c.users_repo.update(1, pos_filter=NOUN)
    await c.batch.issue_next_batch(await c.users_repo.get(1), now=NOW)
    before = await c.cards_repo.by_word_ids(1, [1, 3])
    await c.users_repo.update(1, pos_filter=ADV)
    assert await c.learning.build_session(await c.users_repo.get(1), now=NOW) == []
    # back has an adverb sense but this card was issued as a noun.
    await c.users_repo.update(1, pos_filter=ALL_POS)
    cards = await c.learning.build_session(await c.users_repo.get(1), now=NOW)
    assert {card["word_id"] for card in cards} == {1, 3}
    card = await c.cards_repo.get(1, 3)
    word = await c.words_repo.by_id(3)
    prompt = study_word(word, await c.words_repo.senses(3), card["study_pos_filter"])
    assert prompt["translation"] == "спина"
    assert await c.cards_repo.by_word_ids(1, [1, 3]) == before


async def test_empty_result_does_not_advance_batch_or_progress(vocabulary):
    c = vocabulary
    await c.users_repo.update(1, pos_filter=POS_BITS["num"])
    user = await c.users_repo.get(1)
    assert await c.batch.issue_next_batch(user, now=NOW) is None
    assert await c.users_repo.get(1) == user
    assert await c.cards_repo.count_by_state(1) == {"new": 0, "learning": 0, "review": 0, "graduated": 0}


async def test_automatic_batch_uses_filter_and_hidden_cards_do_not_block_it(vocabulary):
    c = vocabulary
    await c.users_repo.update(1, batch_size=3)
    await c.batch.issue_next_batch(await c.users_repo.get(1), now=NOW)
    hidden = await c.cards_repo.by_word_ids(1, [1, 3])
    await c.users_repo.update(1, pos_filter=VERB)
    outcome = await c.learning.evaluate_answer(
        await c.users_repo.get(1), await c.cards_repo.get(1, 2), "light", now=NOW
    )
    assert outcome.next_batch_issued
    user = await c.users_repo.get(1)
    new = await c.cards_repo.find_new_in_batch(1, user["current_batch_id"], 10)
    assert [card["word_id"] for card in new] == [6]
    assert await c.cards_repo.by_word_ids(1, [1, 3]) == hidden


@pytest.mark.parametrize("invalid", [0, -1, ALL_POS + 1])
async def test_empty_or_unknown_preferences_are_not_saved(vocabulary, invalid):
    with pytest.raises(ValueError):
        await vocabulary.users_repo.update(1, pos_filter=invalid)
    assert (await vocabulary.users_repo.get(1))["pos_filter"] == ALL_POS


async def test_seed_sense_metadata_on_existing_database_is_idempotent(session_factory, tmp_path):
    dictionary = tmp_path / "custom.csv"
    dictionary.write_text("english,translation,frequency_rank,pos\nback,спина; назад,1,noun\nmystery,неизвестно,2,\n")
    sidecar = tmp_path / "custom_senses.csv"
    sidecar.write_text("english,translation,parts_of_speech\nback,спина,noun\nback,назад,adv\n")
    # Existing volume just migrated: words and cards exist, sense metadata does not.
    async with session_factory() as session:
        await session.execute(insert(Word), [
            dict(id=1, english="back", translation="спина; назад", frequency_rank=1, pos="noun"),
            dict(id=2, english="mystery", translation="неизвестно", frequency_rank=2, pos=""),
        ])
        await session.commit()
    c = build_container(session_factory, scheduler=None, send_reminder=AsyncMock())
    await c.users_repo.create_if_absent(1)
    await c.batch.issue_next_batch(await c.users_repo.get(1), now=NOW)
    before = await c.cards_repo.by_word_ids(1, [1, 2])
    assert await seed_word_senses(session_factory, sidecar) == 3
    assert await seed_word_senses(session_factory, sidecar) == 0
    async with session_factory() as session:
        senses = (await session.execute(select(WordSense).order_by(WordSense.word_id, WordSense.position))).scalars().all()
        assert [(s.translation, s.pos_mask) for s in senses] == [("спина", NOUN), ("назад", ADV), ("неизвестно", POS_BITS["other"])]
    assert await c.cards_repo.by_word_ids(1, [1, 2]) == before
    assert await seed_from_csv(session_factory, dictionary) == (0, 2)
    assert [sense["pos_mask"] for sense in await c.words_repo.senses(1)] == [NOUN, ADV]
    assert await c.cards_repo.by_word_ids(1, [1, 2]) == before


def test_builder_classifies_exact_translations_and_leaves_unknowns_unclassified(tmp_path):
    dictionary = tmp_path / "dictionary.csv"
    dictionary.write_text("english,translation,frequency_rank,pos\nback,спина; назад; другой перевод,1,noun\n")
    dump = tmp_path / "kaikki.jsonl"
    entries = [dict(word="back", pos=pos, translations=[dict(lang_code="ru", word=ru)])
               for pos, ru in [("noun", "спина"), ("adv", "назад")]]
    dump.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries))
    output = tmp_path / "senses.csv"
    build_senses(dictionary, dump, output)
    rows = list(csv.DictReader(output.open()))
    assert [(row["translation"], row["parts_of_speech"]) for row in rows] == [
        ("спина", "noun"), ("назад", "adv"), ("другой перевод", "other")]


def test_shipped_metadata_covers_each_dictionary_translation():
    root = Path(__file__).resolve().parents[1]
    with (root / "data/dictionary_senses.csv").open() as source:
        metadata = {(row["english"], row["translation"]): row["parts_of_speech"] for row in csv.DictReader(source)}
    with (root / "data/dictionary.csv").open() as source:
        for word in csv.DictReader(source):
            for translation in word["translation"].split(";"):
                assert (word["english"], translation.strip()) in metadata
    assert metadata["back", "назад"] == "adv"
    assert "noun" in metadata["back", "спина"]
    assert pos_mask("phrasal") == pos_mask("modal") == VERB


def test_stale_queue_cannot_render_a_meaning_outside_filter():
    word = dict(english="light", translation="свет", pos="noun")
    assert study_word(word, [], VERB) is None
    assert study_word(word, [dict(translation="свет", pos_mask=NOUN)], VERB) is None
