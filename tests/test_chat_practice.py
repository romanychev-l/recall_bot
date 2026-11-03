from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, MessageEntity, MessageOriginUser, User
from sqlalchemy import insert, select, update

from bot.container import build_container
from bot.db.models import ChatPractice, ChatPracticePraise, ReviewLog, UserCard, Word
from bot.domain.chat_practice import PracticeLexicon, authored_text
from bot.repositories.practice_repo import PracticeRepo

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
CHAT = -100123
PERSON = User(id=123, is_bot=False, first_name='Learner')
WORDS = [('work', 'verb'), ('walk', 'verb'), ('study', 'verb'), ('child', 'noun'),
         ('discover', 'verb'), ('working', 'adj'), ('saw', 'noun'), ('see', 'verb'),
         ('axe', 'noun'), ('axis', 'noun'), ('unhappy', 'adj'), ('happy', 'adj'),
         ('london', 'name'), ('the', 'det'), ('from', 'prep'), ('give up', 'verb')]
FORMS = [dict(form=form, english=word, pos=pos) for form, word, pos in [
    ('worked', 'work', 'verb'), ('works', 'work', 'verb'), ('working', 'work', 'verb'),
    ('walked', 'walk', 'verb'), ('studies', 'study', 'verb'), ('studying', 'study', 'verb'),
    ('studied', 'study', 'verb'), ('children', 'child', 'noun'), ('saw', 'see', 'verb'),
    ('axes', 'axe', 'noun'), ('axes', 'axis', 'noun'), ('happier', 'happy', 'adj'),
    ('gave up', 'give up', 'verb'),
]]


def vocabulary():
    return [dict(id=i, english=word, translation=word, pos=pos, frequency_rank=100 + i)
            for i, (word, pos) in enumerate(WORDS, 1)]


def message(text=None, *, user=PERSON, at=NOW, chat_id=CHAT, message_id=1, **fields):
    return Message(message_id=message_id, date=at, chat=Chat(id=chat_id, type='supergroup' if chat_id < 0 else 'private'),
                   from_user=user, text=text, **fields)


@pytest.fixture
async def practice(session_factory):
    words = vocabulary()
    async with session_factory() as session:
        await session.execute(insert(Word), words)
        await session.commit()
    container = build_container(session_factory, scheduler=None, send_reminder=AsyncMock())
    await container.users_repo.create_if_absent(PERSON.id)
    await container.users_repo.update(PERSON.id, tz='Europe/Moscow', batch_size=len(words))
    container.practice.lexicon = PracticeLexicon(words, FORMS)
    return SimpleNamespace(service=container.practice, container=container, sf=session_factory,
                           ids={w['english']: w['id'] for w in words})


def test_normalization_closed_words_and_real_boundaries():
    lexicon = PracticeLexicon(vocabulary(), FORMS)
    def extract(text):
        return [w['english'] for w in lexicon.extract(text)]
    assert extract('I am working, worked and studying with children.') == ['work', 'study', 'child']
    assert extract('The unhappy child is happier.') == ['unhappy', 'child', 'happy']
    assert extract('I saw a saw.') == ['see', 'saw']
    assert extract('axes') == []
    assert extract('I gave up.') == ['give up']
    assert extract('The from London YOU good would.') == []
    assert extract('перераworkбота work123 rework') == []
    assert extract("The child's study") == ['child', 'study']
    assert extract('The working day') == ['work']  # No invented prefix/suffix stems.


def test_entities_utf16_links_code_and_quotes_are_excluded():
    text = '😀 https://work.test child study'
    start = len('😀 '.encode('utf-16-le')) // 2
    entities = [MessageEntity(type='url', offset=start, length=len('https://work.test')),
                MessageEntity(type='blockquote', offset=len('😀 https://work.test '.encode('utf-16-le')) // 2,
                              length=len('child'))]
    cleaned = authored_text(text, entities)
    assert 'https' not in cleaned and 'child' not in cleaned and 'study' in cleaned
    assert 'work' not in authored_text('https://work.test user@work.test @work #work `work` ```work```')


async def test_unknown_and_learning_credit_preserves_every_card_and_review(practice):
    h = practice
    user = await h.container.users_repo.get(PERSON.id)
    await h.container.batch.issue_next_batch(user, now=NOW)
    async with h.sf() as session:
        await session.execute(update(UserCard).where(UserCard.word_id == h.ids['work']).values(my_state='review'))
        await session.execute(update(UserCard).where(UserCard.word_id == h.ids['walk']).values(my_state='graduated'))
        before = (await session.execute(select(UserCard.__table__))).mappings().all()
        await session.commit()
    praise = await h.service.observe(message('I worked, walked, studied and discover things with children.'), now=NOW)
    assert set(praise) == {'study', 'discover', 'child'}
    async with h.sf() as session:
        assert (await session.execute(select(UserCard.__table__))).mappings().all() == before
        assert (await session.scalars(select(ReviewLog))).all() == []
        usage = (await session.scalars(select(ChatPractice))).all()
        assert len(usage) == 3 and all(row.study_state == 'new' for row in usage)


async def test_unseen_words_before_initial_level_are_not_claimed_as_new(practice):
    h = practice
    await h.container.users_repo.update(PERSON.id, initial_rank=103)
    result = await h.service.observe(message('work walk study discover'), now=NOW)
    assert set(result) == {'study', 'discover'}
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', NOW) == {'today': 2, 'total': 2}


async def test_retry_daily_deduplication_cooldown_restart_and_next_day(practice):
    h = practice
    assert await h.service.observe(message('working worked work study'), now=NOW) == ['work', 'study']
    assert await h.service.observe(message('working worked work study'), now=NOW) == []
    assert await h.service.observe(message('discover', message_id=2), now=NOW + timedelta(minutes=1)) == []
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', NOW) == {'today': 3, 'total': 3}
    # Reconstruct the service with no in-memory cooldown state.
    restored = type(h.service)(PracticeRepo(h.sf), h.container.users_repo)
    restored.lexicon = h.service.lexicon
    assert await restored.observe(message('child', message_id=3), now=NOW + timedelta(minutes=2)) == []
    assert await restored.observe(message('walk', message_id=4), now=NOW + timedelta(minutes=16)) == ['walk']
    tomorrow = NOW + timedelta(days=1)
    assert await restored.observe(message('work', at=tomorrow, message_id=5), now=tomorrow) == ['work']
    async with h.sf() as session:
        assert len((await session.scalars(select(ChatPractice))).all()) == 6
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', tomorrow) == {'today': 1, 'total': 5}


async def test_same_word_in_different_groups_still_counts_once_and_users_are_independent(practice):
    h = practice
    assert await h.service.observe(message('work'), now=NOW) == ['work']
    assert await h.service.observe(message('work', chat_id=CHAT - 1), now=NOW) == []
    other = User(id=456, is_bot=False, first_name='Other')
    await h.container.users_repo.create_if_absent(other.id)
    assert await h.service.observe(message('work', user=other, message_id=2), now=NOW) == ['work']
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', NOW) == {'today': 1, 'total': 1}


@pytest.mark.parametrize('fields', [
    {'user': User(id=123, is_bot=True, first_name='Bot')},
    {'sender_chat': Chat(id=CHAT, type='supergroup')},
    {'forward_origin': MessageOriginUser(date=NOW, sender_user=PERSON)},
    {'via_bot': User(id=999, is_bot=True, first_name='Inline')},
    {'edit_date': int(NOW.timestamp())}, {'chat_id': PERSON.id},
    {'user': User(id=456, is_bot=False, first_name='Unregistered')},
])
async def test_non_original_or_non_group_or_unknown_authors_ignored(practice, fields):
    assert await practice.service.observe(message('work study', **fields), now=NOW) == []
    assert await practice.service.stats(PERSON.id, 'Europe/Moscow', NOW) == {'today': 0, 'total': 0}


async def test_user_day_boundary_and_message_replay_under_timezone_change(practice):
    h = practice
    before_midnight = datetime(2026, 11, 3, 20, 59, tzinfo=timezone.utc)
    after_midnight = before_midnight + timedelta(minutes=2)
    assert await h.service.observe(message('work', at=before_midnight), now=before_midnight) == ['work']
    await h.service.observe(message('work', at=after_midnight, message_id=2), now=after_midnight)
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', after_midnight) == {'today': 1, 'total': 1}
    await h.container.users_repo.update(PERSON.id, tz='America/New_York')
    await h.service.observe(message('work', at=before_midnight), now=after_midnight)
    async with h.sf() as session:
        assert len((await session.scalars(select(ChatPractice))).all()) == 2


async def test_concurrent_delivery_grants_one_daily_credit(practice):
    h = practice
    await asyncio.gather(h.service.observe(message('work'), now=NOW),
                         h.service.observe(message('work', chat_id=CHAT - 1), now=NOW))
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', NOW) == {'today': 1, 'total': 1}


def test_shipped_forms_and_extractor_cover_actual_dictionary():
    import csv
    from pathlib import Path
    from bot.services.practice_service import FORMS_CSV
    root = Path(__file__).resolve().parents[1]
    words = list(csv.DictReader((root / 'data/dictionary.csv').open()))
    words = [dict(w, id=i) for i, w in enumerate(words, 1)]
    lexicon = PracticeLexicon.from_csv(words, FORMS_CSV)
    assert lexicon.lemma('worked') == 'work'
    assert lexicon.lemma('running') == 'run'
    assert lexicon.lemma('children') == 'child'
    assert lexicon.lemma('studied') == 'study'
    assert lexicon.lemma('axes') is None
    assert lexicon.lemma('unhappy') == 'unhappy'
    assert lexicon.lemma('gave up') == 'give up'


def test_form_builder_excludes_archaic_forms_and_derivations(tmp_path):
    import json
    import csv
    from data.build_word_forms import build_forms
    dictionary = tmp_path / 'dictionary.csv'
    dictionary.write_text('english\nwork\ngan\n', encoding='utf-8')
    dump = tmp_path / 'kaikki.jsonl'
    entries = [dict(word='work', pos='verb', senses=[dict(glosses=['To do work'])], forms=[
        dict(form='worked', tags=['past']), dict(form='worketh', tags=['present', 'archaic']),
        dict(form='worker', tags=['derived']), dict(form='worke', tags=['alternative']),
    ]), dict(word='gan', pos='verb', senses=[dict(tags=['obsolete'])],
             forms=[dict(form='went', tags=['past'])])]
    dump.write_text('\n'.join(json.dumps(e) for e in entries))
    out = tmp_path / 'forms.csv'
    build_forms(dictionary, dump, out)
    assert list(csv.DictReader(out.open())) == [dict(form='worked', english='work', pos='verb')]


async def test_long_message_keeps_all_dictionary_words(practice):
    h = practice
    extra = [dict(id=1000+i, english=f'word{chr(97+i//26)}{chr(97+i%26)}', translation='слово',
                  pos='noun', frequency_rank=1000+i) for i in range(150)]
    async with h.sf() as session:
        await session.execute(insert(Word), extra)
        await session.commit()
    h.service.lexicon = PracticeLexicon(vocabulary() + extra, FORMS)
    credited = await h.service.observe(message(' '.join(w['english'] for w in extra)), now=NOW)
    assert len(credited) == 150
    assert await h.service.stats(PERSON.id, 'Europe/Moscow', NOW) == {'today': 150, 'total': 150}


async def test_name_only_meanings_do_not_create_false_inflection_targets(practice):
    from bot.db.models import WordSense
    from bot.domain.parts_of_speech import POS_BITS
    h = practice
    async with h.sf() as session:
        await session.execute(insert(Word).values(id=999, english='gan', translation='гань', pos='noun', frequency_rank=999))
        await session.execute(insert(WordSense).values(word_id=999, position=0, translation='гань', pos_mask=POS_BITS['name']))
        await session.commit()
    assert 'gan' not in {w['english'] for w in await h.service.repository.vocabulary()}
