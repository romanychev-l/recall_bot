from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, GetMe, EditMessageText, AnswerCallbackQuery
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from sqlalchemy import delete, insert, select, update

from bot.container import build_container
from bot.db.models import Word, WordSense, UserCard, ReviewLog
from bot.db.seed import seed_from_csv
from bot.domain.parts_of_speech import ALL_POS, POS_BITS
from bot.handlers import actions, fallback, help, learn, settings, start, stats
from bot.states.learning import LearnSG
from bot.states.onboarding import OnboardSG
from bot.states.settings import SettingsSG
from bot.utils.commands import COMMANDS, register_commands
from bot.utils.i18n import create_translator_hub
from tests.conftest import make_words

NOW = datetime.now(timezone.utc)
USER = User(id=123, is_bot=False, first_name="Learner", language_code="ru")


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, GetMe):
            return User(id=bot.id, is_bot=True, first_name="Recall", username="recall_test_bot")
        if isinstance(method, SendMessage):
            return Message(message_id=len(self.sent), date=NOW,
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""


@pytest.fixture(scope="module")
def translator_hub():
    return create_translator_hub()


@pytest.fixture(scope="module")
def dispatcher():
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    for module in (start, help, learn, stats, settings, actions, fallback):
        dp.include_router(module.router)
    return dp


@pytest.fixture
async def harness(session_factory, dispatcher, translator_hub):
    async with session_factory() as session:
        await session.execute(insert(Word), make_words(80))
        await session.commit()
    container = build_container(session_factory, scheduler=None, send_reminder=AsyncMock())
    await container.users_repo.create_if_absent(USER.id)
    await container.users_repo.update(USER.id, batch_size=3, daily_goal=3)
    recording = RecordingSession()
    bot = Bot("123456:TEST_token_for_local_tests", session=recording)
    state = dispatcher.fsm.get_context(bot=bot, chat_id=USER.id, user_id=USER.id)
    await state.clear()
    async def send(text=None, callback=None, locale="ru"):
        message = Message(message_id=1, date=NOW, chat=Chat(id=USER.id, type="private"),
                          from_user=USER, text=text)
        if callback:
            update = Update(update_id=1, callback_query=CallbackQuery(
                id="test", from_user=USER, chat_instance="test",
                data=callback, message=message.model_copy(update={"from_user": User(
                    id=bot.id, is_bot=True, first_name="Recall"
                )}),
            ))
        else:
            update = Update(update_id=1, message=message)
        await dispatcher.feed_update(bot, update, container=container,
                                     i18n=translator_hub.get_translator_by_locale(locale))

    yield SimpleNamespace(container=container, state=state, sent=recording.sent,
                          send=send, session_factory=session_factory)
    await state.clear()
    await bot.session.close()


async def test_nothing_due_button_adds_words_and_starts_session(harness):
    h = harness
    user = await h.container.users_repo.get(USER.id)
    batch_id = await h.container.batch.issue_next_batch(user)
    future = NOW + timedelta(days=3)
    async with h.session_factory() as session:
        await session.execute(update(UserCard).values(my_state="review", due=future))
        await session.commit()
    before = await h.container.cards_repo.find_new_in_batch(USER.id, batch_id, 10)
    assert before == []
    await h.send("/learn")
    empty = [m for m in h.sent if isinstance(m, SendMessage)][-1]
    assert "/more" in empty.text
    assert empty.reply_markup.inline_keyboard[0][0].callback_data == "learn:more"

    await h.send(callback="learn:more")
    assert await h.state.get_state() == LearnSG.waiting_answer.state
    data = await h.state.get_data()
    assert data["user_id"] == USER.id  # callback message's author is the bot
    assert len(data["queue"]) == 3
    user = await h.container.users_repo.get(USER.id)
    new = await h.container.cards_repo.find_new_in_batch(USER.id, user["current_batch_id"], 10)
    assert {str(c["word_id"]) for c in new} == set(data["queue"])
    async with h.session_factory() as session:
        old = (await session.scalars(select(UserCard).where(UserCard.batch_id == batch_id))).all()
        assert all(c.due == future and c.my_state == "review" for c in old)


@pytest.mark.parametrize("command,count", [("/more", 3), ("/more 7", 7), ("/cram", 50), ("/cram 4", 4)])
async def test_more_and_cram_start_requested_new_words(harness, command, count):
    h = harness
    await h.send(command)
    assert len((await h.state.get_data())["queue"]) == count
    assert await h.state.get_state() == LearnSG.waiting_answer.state


@pytest.mark.parametrize("args", ["0", "501", "nope", "2 3", "2.5", "-1"])
async def test_invalid_count_does_not_allocate_words(harness, args):
    h = harness
    before = await h.container.users_repo.get(USER.id)
    await h.send("/more " + args)
    assert await h.container.users_repo.get(USER.id) == before
    assert "1 до 500" in h.sent[-1].text


async def test_new_words_not_starved_by_due_cards_and_older_new_survive(harness):
    h = harness
    await h.send("/more 3")
    older = (await h.state.get_data())["queue"]
    await h.send("/more 2")
    newer = (await h.state.get_data())["queue"]
    assert set(older).isdisjoint(newer)
    user = await h.container.users_repo.get(USER.id)
    # All five unseen words remain available through ordinary /learn.
    session = await h.container.learning.build_session(user, cap=10)
    assert {str(c["word_id"]) for c in session} == set(older + newer)
    # A full backlog of due cards must not consume a request for new words.
    async with h.session_factory() as session:
        await session.execute(update(UserCard).values(my_state="learning", due=NOW-timedelta(days=1)))
        await session.commit()
    await h.send("/more 2")
    ids = (await h.state.get_data())["queue"]
    assert set(ids).isdisjoint(older + newer)
    for word_id in ids:
        assert (await h.container.cards_repo.get(USER.id, int(word_id)))["my_state"] == "new"


async def test_skipped_unseen_word_stays_hidden_until_tomorrow(harness):
    h = harness
    await h.send("/more 2")
    word_id = int((await h.state.get_data())["queue"][0])
    await h.container.cards_repo.set_skip_until(USER.id, word_id, NOW+timedelta(days=1))
    user = await h.container.users_repo.get(USER.id)
    session = await h.container.learning.build_session(user, now=NOW)
    assert word_id not in {c["word_id"] for c in session}


async def test_dictionary_exhaustion_does_not_replace_session(harness):
    h = harness
    await h.send("/more 80")
    before = await h.state.get_data()
    user = await h.container.users_repo.get(USER.id)
    await h.send("/more")
    assert "больше нет слов" in h.sent[-1].text
    assert await h.state.get_data() == before
    assert await h.container.users_repo.get(USER.id) == user


async def test_end_of_session_offers_continue_and_more(harness):
    h = harness
    await h.send("/more 1")
    word_id = int((await h.state.get_data())["queue"][0])
    word = await h.container.words_repo.by_id(word_id)
    await h.send(word["english"])
    done = [m for m in h.sent if isinstance(m, SendMessage)][-1]
    buttons = {b.callback_data for row in done.reply_markup.inline_keyboard for b in row}
    assert buttons == {"learn:continue", "learn:more"}
    assert await h.state.get_state() is None
    await h.send(callback="learn:continue")
    assert await h.state.get_state() == LearnSG.waiting_answer.state


@pytest.mark.parametrize("state", [LearnSG.waiting_answer, OnboardSG.enter_skip_n,
                                  SettingsSG.edit_batch_size, SettingsSG.edit_reminder_time,
                                  SettingsSG.edit_tz, SettingsSG.edit_pos])
async def test_menu_commands_are_not_consumed_as_answers(harness, state):
    h = harness
    await h.send("/more 1")
    await h.state.set_state(state)
    await h.send("/stats")
    assert "Твоя статистика" in h.sent[-1].text
    async with h.session_factory() as session:
        assert (await session.scalars(select(ReviewLog))).all() == []
    await h.send("/settings")
    assert await h.state.get_state() == SettingsSG.menu.state


async def test_commands_published_for_both_languages_and_default(translator_hub):
    bot = AsyncMock()
    await register_commands(bot, translator_hub)
    assert {c.kwargs["language_code"] for c in bot.set_my_commands.call_args_list} == {"", "ru", "en"}
    for call in bot.set_my_commands.call_args_list:
        commands = call.args[0]
        if call.kwargs["scope"].type == "default":
            assert [c.command for c in commands] == list(COMMANDS)
        else:
            assert call.kwargs["scope"].type == "all_group_chats"
            assert [c.command for c in commands] == ["challenge", "leaders", "join", "leave", "settings", "pause", "resume", "help_group"]
        assert all(1 <= len(c.description) <= 256 for c in commands)
    assert bot.set_chat_menu_button.call_args.kwargs["menu_button"].type == "commands"


def latest_menu(h):
    return [method for method in h.sent if isinstance(method, (SendMessage, EditMessageText))][-1]


def latest_menu_text(h):
    return latest_menu(h).text.replace("\u2068", "").replace("\u2069", "")


@pytest.mark.parametrize("locale", ["ru", "en"])
async def test_pos_menu_multiselect_counter_empty_guard_all_and_persistence(harness, locale):
    h = harness
    async with h.session_factory() as session:
        await session.execute(update(Word).where(Word.frequency_rank > 40).values(pos="verb"))
        await session.commit()
    await h.send("/settings", locale=locale)
    assert "80" in latest_menu(h).text
    assert "settings:pos" in {b.callback_data for row in latest_menu(h).reply_markup.inline_keyboard for b in row}
    await h.send(callback="settings:pos", locale=locale)
    assert await h.state.get_state() == SettingsSG.edit_pos.state
    await h.send(callback="pos:toggle:verb", locale=locale)
    assert "<b>40</b>" in latest_menu_text(h)
    assert (await h.container.users_repo.get(USER.id))["pos_filter"] == POS_BITS["verb"]
    await h.send(callback="pos:toggle:noun", locale=locale)
    assert "<b>80</b>" in latest_menu_text(h)
    assert (await h.container.users_repo.get(USER.id))["pos_filter"] == POS_BITS["verb"] | POS_BITS["noun"]
    await h.send(callback="pos:toggle:verb", locale=locale)
    await h.send(callback="pos:toggle:noun", locale=locale)
    assert isinstance(h.sent[-1], AnswerCallbackQuery) and h.sent[-1].show_alert
    assert (await h.container.users_repo.get(USER.id))["pos_filter"] == POS_BITS["noun"]
    await h.send(callback="pos:done", locale=locale)
    await h.send("/settings", locale=locale)
    await h.send(callback="settings:pos", locale=locale)
    assert "<b>40</b>" in latest_menu_text(h)
    await h.send(callback="pos:all", locale=locale)
    assert (await h.container.users_repo.get(USER.id))["pos_filter"] == ALL_POS
    assert "<b>80</b>" in latest_menu_text(h)
    # Repeated all button must not try an identical Telegram edit.
    edits = sum(isinstance(method, EditMessageText) for method in h.sent)
    await h.send(callback="pos:all", locale=locale)
    assert sum(isinstance(method, EditMessageText) for method in h.sent) == edits


@pytest.mark.parametrize("entrypoint", ["/more 7", "/cram 7", "button"])
async def test_all_new_word_entry_points_respect_pos_filter(harness, entrypoint):
    h = harness
    async with h.session_factory() as session:
        await session.execute(update(Word).where(Word.frequency_rank % 2 == 0).values(pos="verb"))
        await session.commit()
    await h.container.users_repo.update(USER.id, pos_filter=POS_BITS["verb"], batch_size=7)
    if entrypoint == "button":
        await h.send(callback="learn:more")
    else:
        await h.send(entrypoint)
    queue = (await h.state.get_data())["queue"]
    assert len(queue) == 7
    words = await h.container.words_repo.by_ids([int(word_id) for word_id in queue])
    assert all(word["pos"] == "verb" for word in words)
    await h.send("/settings")
    assert "33" in latest_menu(h).text


async def test_prompt_filters_mixed_meanings_and_preserves_card_on_change(harness):
    h = harness
    async with h.session_factory() as session:
        word = (await session.scalars(select(Word).order_by(Word.frequency_rank).limit(1))).one()
        word.translation = "свет; лёгкий"
        word_id = word.id
        await session.execute(insert(WordSense), [
            dict(word_id=word_id, position=0, translation="свет", pos_mask=POS_BITS["noun"]),
            dict(word_id=word_id, position=1, translation="лёгкий", pos_mask=POS_BITS["adj"]),
        ])
        await session.commit()
    await h.container.users_repo.update(USER.id, pos_filter=POS_BITS["adj"])
    await h.send("/more 1")
    assert "лёгкий" in latest_menu(h).text and "свет" not in latest_menu(h).text
    card = await h.container.cards_repo.get(USER.id, word_id)
    await h.send("/settings")
    await h.send(callback="settings:pos")
    await h.send(callback="pos:toggle:adj")  # Empty choice is rejected.
    await h.send(callback="pos:toggle:noun")
    await h.send(callback="pos:toggle:adj")
    await h.send("/learn")
    assert "нет подходящих карточек" in latest_menu(h).text
    assert await h.container.cards_repo.get(USER.id, word_id) == card


async def test_empty_pos_selection_results_are_explained(harness):
    h = harness
    await h.container.users_repo.update(USER.id, pos_filter=POS_BITS["num"])
    await h.send("/settings")
    await h.send(callback="settings:pos")
    assert "<b>0</b>" in latest_menu_text(h) and "/settings" in latest_menu_text(h)
    user = await h.container.users_repo.get(USER.id)
    await h.send("/more")
    assert "выбранных частей речи нет" in latest_menu(h).text
    assert await h.container.users_repo.get(USER.id) == user


async def test_stats_next_word_uses_current_filter_instead_of_high_water_rank(harness):
    h = harness
    async with h.session_factory() as session:
        await session.execute(update(Word).where(Word.frequency_rank == 2).values(pos="verb"))
        await session.commit()
    await h.container.users_repo.update(USER.id, pos_filter=POS_BITS["verb"])
    await h.send("/more 1")
    await h.container.users_repo.update(USER.id, pos_filter=POS_BITS["noun"])
    await h.send("/stats")
    assert "#1" in latest_menu(h).text


@pytest.mark.parametrize("entrypoint", ["button", "/more", "/cram 3"])
async def test_finish_daily_session_then_get_frequency_words(harness, entrypoint):
    h = harness
    async with h.session_factory() as session:
        await session.execute(delete(Word))
        await session.commit()
    await seed_from_csv(h.session_factory, Path(__file__).resolve().parents[1] / "data/dictionary.csv")
    await h.container.users_repo.update(USER.id, initial_rank=101)
    await h.container.batch.issue_next_batch(await h.container.users_repo.get(USER.id))
    await h.send('/learn')
    first_queue = (await h.state.get_data())['queue'][:]
    for word_id in first_queue:
        word = await h.container.words_repo.by_id(int(word_id))
        await h.send(word['english'])
    assert await h.state.get_state() is None
    done = [m for m in h.sent if isinstance(m, SendMessage)][-1]
    assert 'learn:more' in {b.callback_data for row in done.reply_markup.inline_keyboard for b in row}
    user = await h.container.users_repo.get(USER.id)
    expected = await h.container.words_repo.next_available(USER.id, user['initial_rank'], 3)
    async with h.session_factory() as session:
        before = (await session.execute(select(UserCard.__table__))).mappings().all()
    if entrypoint == 'button':
        await h.send(callback='learn:more')
    else:
        await h.send(entrypoint)
    queue = (await h.state.get_data())['queue']
    assert queue == [str(w['id']) for w in expected]
    assert not set(queue) & set(first_queue)
    first_prompt = [m for m in h.sent if isinstance(m, SendMessage)][-1]
    assert expected[0]['translation'] in first_prompt.text
    async with h.session_factory() as session:
        after = (await session.execute(select(UserCard.__table__).where(UserCard.id.in_([c['id'] for c in before])))).mappings().all()
    assert after == before


@pytest.mark.parametrize('locale', ['ru', 'en'])
@pytest.mark.parametrize('answer', ['correct', 'wrong', 'dontknow'])
async def test_examples_revealed_only_after_answer_with_safe_html(harness, locale, answer):
    h = harness
    examples = 'We share bread & butter.\nShe wrote <hello> on the board.'
    async with h.session_factory() as session:
        await session.execute(update(Word).values(example=examples))
        await session.commit()
    await h.send('/more 1', locale=locale)
    prompt = latest_menu(h).text
    assert 'bread' not in prompt and 'hello' not in prompt
    word_id = int((await h.state.get_data())['queue'][0])
    word = await h.container.words_repo.by_id(word_id)
    before = len(h.sent)
    if answer == 'dontknow':
        await h.send(callback=f'card:dontknow:{word_id}', locale=locale)
    else:
        await h.send(word['english'] if answer == 'correct' else '<wrong & answer>', locale=locale)
    messages = [m.text for m in h.sent[before:] if isinstance(m, SendMessage)]
    feedback = messages[0]
    assert ('Примеры употребления:' if locale == 'ru' else 'Usage examples:') in feedback
    assert '• <i>We share bread &amp; butter.</i>' in feedback
    assert '• <i>She wrote &lt;hello&gt; on the board.</i>' in feedback
    if answer == 'wrong':
        assert '&lt;wrong &amp; answer&gt;' in feedback
    assert await h.state.get_state() is None
    async with h.session_factory() as session:
        logs = (await session.scalars(select(ReviewLog))).all()
        assert len(logs) == 1
        assert logs[0].result == ('good' if answer == 'correct' else 'again')


async def test_custom_word_without_examples_still_accepts_answer(harness):
    h = harness
    await h.send('/more 1')
    word_id = int((await h.state.get_data())['queue'][0])
    word = await h.container.words_repo.by_id(word_id)
    before = len(h.sent)
    await h.send(word['english'])
    feedback = [m.text for m in h.sent[before:] if isinstance(m, SendMessage)][0]
    assert '✅' in feedback and '📖' not in feedback
