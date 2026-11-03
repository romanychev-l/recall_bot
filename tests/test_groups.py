from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import SendMessage, EditMessageText
from aiogram.types import Chat, Message, Update, User, CallbackQuery, ChatMemberUpdated, ChatMemberMember, ChatMemberLeft
from sqlalchemy import insert, select, update

from bot.container import build_container
from bot.db.models import GroupChat, GroupMember, ReviewLog, UserCard, Word
from bot.handlers.groups import router as group_router
from bot.repositories.groups_repo import GroupsRepo
from bot.services.group_service import GroupService, PAGE_SIZE, next_report_at, ranking_text, validate_schedule
from bot.states.learning import LearnSG
from tests.conftest import make_words
from tests.test_learning_commands import RecordingSession

NOW = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
CHAT = -1001234567890
LEARNER = User(id=123, is_bot=False, first_name="Леонид")
OTHER = User(id=456, is_bot=False, first_name="Анна")


def group_data(chat_id=CHAT, **extra):
    return {"id": chat_id, "title": "English", "creator_id": LEARNER.id,
            "timezone": "Europe/Moscow", "report_time": "21:00", "enabled": True,
            "bot_present": True, "thread_id": 7, "message_id": None,
            "next_report_at": NOW, "created_at": NOW, **extra}


@pytest.fixture(scope="module")
def group_dispatcher():
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    dp.include_router(group_router)
    sentinel = Router(name="personal_sentinel")

    @sentinel.message()
    async def personal(message, personal_calls):
        personal_calls.append(message.text)

    dp.include_router(sentinel)
    return dp


@pytest.fixture
async def harness(session_factory, group_dispatcher):
    recording = RecordingSession()
    bot = Bot("123456:TEST_token_for_local_tests", session=recording)
    container = build_container(session_factory, scheduler=None, send_reminder=AsyncMock(), bot=bot)
    state = group_dispatcher.fsm.get_context(bot=bot, chat_id=CHAT, user_id=LEARNER.id)
    await state.clear()
    personal_calls = []

    async def send(text=None, *, user=LEARNER, chat_id=CHAT, callback=None, membership=None,
                   message_id=100, sent_at=NOW, **fields):
        chat = Chat(id=chat_id, type="private" if chat_id > 0 else "supergroup", title="English")
        message = Message(message_id=message_id, date=sent_at, chat=chat, from_user=user,
                          message_thread_id=7 if chat_id < 0 else None, text=text, **fields)
        if membership:
            event = ChatMemberUpdated(chat=chat, from_user=user, date=NOW,
                old_chat_member=ChatMemberLeft(user=User(id=bot.id, is_bot=True, first_name="Recall")),
                new_chat_member=ChatMemberMember(user=User(id=bot.id, is_bot=True, first_name="Recall")))
            event = event if membership == "add" else event.model_copy(update={
                "old_chat_member": event.new_chat_member, "new_chat_member": event.old_chat_member})
            request = Update(update_id=100, my_chat_member=event)
        elif callback:
            request = Update(update_id=100, callback_query=CallbackQuery(
                id="callback", from_user=user, chat_instance="chat", data=callback, message=message))
        else:
            request = Update(update_id=100, message=message)
        await group_dispatcher.feed_update(bot, request, container=container, personal_calls=personal_calls)

    yield SimpleNamespace(container=container, groups=container.groups, repo=container.groups.repository,
                          send=send, bot=bot, sent=recording.sent, state=state,
                          session_factory=session_factory, personal_calls=personal_calls)
    await state.clear()
    await bot.session.close()


async def test_create_join_refresh_leave_and_private_link(harness):
    h = harness
    await h.send("/challenge")
    group = await h.repo.get(CHAT)
    assert group["timezone"] == "Europe/Moscow" and group["report_time"] == "21:00"
    assert group["thread_id"] == 7
    rows = await h.repo.standings(CHAT, NOW-timedelta(days=1), NOW)
    assert [(r["user_id"], r["learned"], r["today"]) for r in rows] == [(LEARNER.id, 0, 0)]
    post = next(m for m in h.sent if isinstance(m, SendMessage))
    assert post.message_thread_id == 7
    assert post.reply_markup.inline_keyboard[0][1].url == "https://t.me/recall_test_bot"
    assert "startapp" not in post.reply_markup.inline_keyboard[0][1].url
    await h.send(callback="group:join", user=OTHER)
    await h.send(callback="group:join", user=OTHER)
    assert len(await h.repo.standings(CHAT, NOW-timedelta(days=1), NOW)) == 2
    # Joining does not reset or create personal learning progress.
    assert await h.container.users_repo.get(OTHER.id) is None
    await h.send("/leave", user=OTHER)
    assert [r["user_id"] for r in await h.repo.standings(CHAT, NOW-timedelta(days=1), NOW)] == [LEARNER.id]
    await h.send("/join", user=OTHER)
    assert len(await h.repo.standings(CHAT, NOW-timedelta(days=1), NOW)) == 2
    await h.send("/leaders")
    assert any(isinstance(m, EditMessageText) for m in h.sent)


async def test_groups_and_private_states_do_not_mix(harness):
    h = harness
    await h.state.set_state(LearnSG.waiting_answer)
    await h.state.set_data({"queue": ["99"]})
    await h.send("English answer")
    await h.send("/more")
    await h.send(callback="learn:more")
    assert h.personal_calls == []
    assert await h.state.get_data() == {"queue": ["99"]}
    assert await h.container.users_repo.get(LEARNER.id) is None
    await h.send("/learn", chat_id=LEARNER.id)
    assert h.personal_calls == ["/learn"]


async def test_memberships_independent_and_names_escaped(harness):
    h = harness
    await h.repo.create(group_data())
    await h.repo.create(group_data(CHAT-1))
    person = User(id=999, is_bot=False, first_name="<b>A & B</b>")
    await h.groups.join(CHAT, person, NOW)
    await h.groups.join(CHAT-1, person, NOW)
    assert await h.repo.leave(CHAT, person.id)
    assert await h.repo.standings(CHAT, NOW, NOW) == []
    rows = await h.repo.standings(CHAT-1, NOW, NOW)
    text, _, _ = ranking_text(group_data(), rows, NOW)
    assert "&lt;b&gt;A &amp; B&lt;/b&gt;" in text
    assert len(rows) == 1


async def test_correct_distinct_words_group_day_bounds_and_no_other_users(harness):
    h = harness
    await h.repo.create(group_data())
    await h.groups.join(CHAT, LEARNER, NOW)
    await h.groups.join(CHAT, OTHER, NOW)
    async with h.session_factory() as session:
        await session.execute(insert(Word), make_words(6))
        await session.commit()
    for user in (LEARNER, OTHER, User(id=789, is_bot=False, first_name="Hidden")):
        await h.container.users_repo.create_if_absent(user.id)
        await h.container.users_repo.update(user.id, batch_size=6)
        await h.container.batch.issue_next_batch(await h.container.users_repo.get(user.id), now=NOW)
    first = await h.container.cards_repo.find_new_in_batch(LEARNER.id, (await h.container.users_repo.get(LEARNER.id))["current_batch_id"], 6)
    since = datetime(2026, 10, 22, 21, tzinfo=timezone.utc)  # midnight Moscow, Oct 23
    async with h.session_factory() as session:
        await session.execute(update(UserCard).where(UserCard.user_id == LEARNER.id,
                              UserCard.word_id.in_([first[0]["word_id"], first[1]["word_id"]])).values(my_state="review"))
        for card, result, ts in [
            (first[0], "good", since), (first[0], "good", since+timedelta(hours=1)),
            (first[1], "again", since+timedelta(hours=2)),
            (first[2], "good", since-timedelta(seconds=1)),
            (first[3], "good", NOW+timedelta(seconds=1)),
        ]:
            session.add(ReviewLog(user_id=LEARNER.id, word_id=card["word_id"], batch_id=card["batch_id"],
                                  result=result, user_input="private-answer", reviewed_at=ts))
        await session.commit()
    rows = await h.repo.standings(CHAT, since, NOW)
    assert {r["user_id"] for r in rows} == {LEARNER.id, OTHER.id}
    assert rows[0]["learned"] == 2 and rows[0]["today"] == 1
    text, _, _ = ranking_text(group_data(), rows, NOW)
    assert "private-answer" not in text and "word" not in text


async def test_evening_delivery_survives_restart_and_is_not_duplicated(harness):
    h = harness
    await h.repo.create(group_data())
    await h.groups.join(CHAT, LEARNER, NOW)
    # Reconstruct manager/repository to mimic a restart; schedule is in SQLite.
    restored = GroupService(h.bot, GroupsRepo(h.session_factory), None)
    await asyncio.gather(restored.tick(NOW), restored.tick(NOW))
    assert len([m for m in h.sent if isinstance(m, SendMessage)]) == 1
    group = await h.repo.get(CHAT)
    assert group["next_report_at"] == NOW+timedelta(days=1)
    await restored.tick(NOW+timedelta(hours=1))
    assert len([m for m in h.sent if isinstance(m, SendMessage)]) == 1
    await h.repo.update(CHAT, next_report_at=NOW, enabled=False)
    await restored.tick(NOW+timedelta(days=2))
    assert len([m for m in h.sent if isinstance(m, SendMessage)]) == 1


async def test_schedule_permissions_and_pause_resume(harness):
    h = harness
    await h.send("/challenge")
    before = await h.repo.get(CHAT)
    # RecordingSession's admin endpoint returns True by default; provide a list.
    original = h.bot.session.make_request
    async def request(bot, method, timeout=None):
        if method.__api_method__ == "getChatAdministrators":
            return []
        return await original(bot, method, timeout)
    h.bot.session.make_request = request
    await h.send("/settings 20:30 UTC", user=OTHER)
    assert (await h.repo.get(CHAT))["report_time"] == before["report_time"]
    await h.send("/pause", user=OTHER)
    assert (await h.repo.get(CHAT))["enabled"]
    await h.send("/settings 20:30 UTC")
    group = await h.repo.get(CHAT)
    assert group["report_time"] == "20:30" and group["timezone"] == "UTC"
    await h.send("/settings 25:00 UTC")
    assert (await h.repo.get(CHAT))["report_time"] == "20:30"
    await h.send("/pause")
    assert not (await h.repo.get(CHAT))["enabled"]
    await h.send("/resume")
    assert (await h.repo.get(CHAT))["enabled"]


async def test_bot_membership_removal_and_group_migration(harness):
    h = harness
    await h.send(membership="add")
    assert any(isinstance(m, SendMessage) and "/challenge@recall_test_bot" in m.text for m in h.sent)
    await h.send("/challenge")
    await h.send(membership="remove")
    assert not (await h.repo.get(CHAT))["bot_present"]
    await h.send(membership="add")
    assert (await h.repo.get(CHAT))["bot_present"]
    new_id=CHAT-100
    await h.send(migrate_to_chat_id=new_id)
    assert await h.repo.get(CHAT) is None
    moved = await h.repo.get(new_id)
    assert moved["message_id"] is None and moved["thread_id"] is None
    assert [r["user_id"] for r in await h.repo.standings(new_id, NOW, NOW)] == [LEARNER.id]
    await h.send(chat_id=new_id, left_chat_member=LEARNER)
    assert await h.repo.standings(new_id, NOW, NOW) == []


@pytest.mark.parametrize("kind", ["forbidden", "retry"])
async def test_delivery_errors_do_not_break_other_groups(harness, kind):
    h = harness
    await h.repo.create(group_data())
    await h.repo.create(group_data(CHAT-1))
    original = h.bot.session.make_request
    async def request(bot, method, timeout=None):
        if isinstance(method, SendMessage) and method.chat_id == CHAT:
            if kind == "forbidden":
                raise TelegramForbiddenError(method=method, message="bot was kicked")
            raise TelegramRetryAfter(method=method, message="rate limit", retry_after=60)
        return await original(bot, method, timeout)
    h.bot.session.make_request = request
    await h.groups.tick(NOW)
    group = await h.repo.get(CHAT)
    if kind == "forbidden":
        assert not group["bot_present"]
    else:
        assert group["next_report_at"] == NOW+timedelta(seconds=60)
    assert (await h.repo.get(CHAT-1))["next_report_at"] == NOW+timedelta(days=1)


def test_pagination_and_timezone_schedule():
    rows=[{"user_id":i,"display_name":"&"*32,"learned":30-i,"today":2} for i in range(30)]
    text,page,pages=ranking_text(group_data(),rows,NOW,page=2)
    assert (page,pages)==(2,2) and f"{PAGE_SIZE+1}." in text and "1." not in text.splitlines()[4]
    assert len(text)<4096
    assert next_report_at("21:00","Europe/Moscow",NOW)==NOW+timedelta(days=1)
    assert next_report_at("21:00","Europe/Moscow",NOW-timedelta(seconds=1))==NOW
    for time,zone in [("25:00","UTC"),("9:00","UTC"),("21:00","Not/AZone")]:
        with pytest.raises(ValueError):
            validate_schedule(time,zone)


async def seed_chat_practice_words(h):
    async with h.session_factory() as session:
        await session.execute(insert(Word), [
            dict(english='work', translation='работать', pos='verb', frequency_rank=100),
            dict(english='child', translation='ребёнок', pos='noun', frequency_rank=101),
            dict(english='discover', translation='открывать', pos='verb', frequency_rank=102),
        ])
        await session.commit()
    await h.container.users_repo.create_if_absent(LEARNER.id)


async def test_practice_without_challenge_or_join_praise_reply_statistics_and_dedup(harness):
    from bot.db.models import ChatPractice
    h = harness
    await seed_chat_practice_words(h)
    assert await h.repo.get(CHAT) is None
    await h.send('I am working with children.')
    replies = [m for m in h.sent if isinstance(m, SendMessage)]
    assert len(replies) == 1
    assert 'Английский в деле' in replies[0].text and '<b>work</b>' in replies[0].text
    assert '<b>child</b>' in replies[0].text
    assert replies[0].reply_parameters.message_id == 100
    assert replies[0].message_thread_id == 7
    await h.send('I am working with children.')
    await h.send('I discover something.', message_id=101)
    assert len([m for m in h.sent if isinstance(m, SendMessage)]) == 1  # cooldown
    assert await h.container.practice.stats(LEARNER.id, 'Europe/Moscow', NOW) == {'today': 3, 'total': 3}
    async with h.session_factory() as session:
        assert len((await session.scalars(select(ChatPractice))).all()) == 3
        assert (await session.scalars(select(UserCard))).all() == []
        assert (await session.scalars(select(ReviewLog))).all() == []
    # The public table remains opt-in, even though usage credit is automatic.
    await h.repo.create(group_data())
    assert await h.repo.standings(CHAT, NOW-timedelta(days=1), NOW) == []
    await h.groups.join(CHAT, LEARNER, NOW)
    standings = await h.repo.standings(CHAT, NOW-timedelta(days=1), NOW)
    assert standings[0]['practice'] == 3 and standings[0]['learned'] == standings[0]['today'] == 0


async def test_failed_praise_does_not_lose_credit_or_send_generic_table_error(harness):
    h = harness
    await seed_chat_practice_words(h)
    h.bot.session.make_request = AsyncMock(side_effect=TelegramForbiddenError(
        method=SendMessage(chat_id=CHAT, text='test'), message='not allowed'))
    await h.send('I discover something.')
    assert h.bot.session.make_request.await_count == 1
    assert (await h.container.practice.stats(LEARNER.id, 'Europe/Moscow', NOW))['total'] == 1


async def test_caption_is_detected_and_command_is_not_practice(harness):
    h = harness
    await seed_chat_practice_words(h)
    await h.send(None, caption='I discover something.')
    assert any(isinstance(m, SendMessage) and '<b>discover</b>' in m.text for m in h.sent)
    await h.send('/work child', message_id=101)
    assert (await h.container.practice.stats(LEARNER.id, 'Europe/Moscow', NOW))['total'] == 1
