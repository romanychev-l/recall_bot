from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bson import ObjectId
from fluentogram import TranslatorRunner

from bot.container import Container
from bot.states.learning import LearnSG
from bot.utils.keyboards import answer_actions_kb

logger = logging.getLogger(__name__)
router = Router(name="learn")


def _hex_ids(cards: list[dict]) -> list[str]:
    return [str(c["word_id"]) for c in cards]


async def _show_next(
    chat_id: int,
    bot,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> bool:
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    user_id = data.get("user_id")
    if not queue:
        await bot.send_message(chat_id, i18n.message.session_done())
        await state.clear()
        return False
    word_id_hex = queue[0]
    card = await container.cards_repo.get(user_id, ObjectId(word_id_hex))
    if card is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n)
    word = await container.words_repo.by_id(card["word_id"])
    if word is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n)
    text = i18n.message.prompt_word(
        translation=word["translation"],
        remaining=len(queue),
        pos=word.get("pos") or "—",
    )
    await bot.send_message(chat_id, text, reply_markup=answer_actions_kb(i18n, word_id_hex))
    return True


@router.message(Command("learn"))
async def cmd_learn(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    user = await container.users_repo.get(message.from_user.id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    session = await container.learning.build_session(user)
    if not session:
        await message.answer(i18n.message.nothing_due())
        return
    await state.set_state(LearnSG.waiting_answer)
    await state.update_data(
        user_id=message.from_user.id,
        queue=_hex_ids(session),
    )
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.message(Command("cram"))
async def cmd_cram(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    """Force-issue a custom-size batch of NEW words and start a session.

    Use when you want to blast through known vocabulary faster than the
    daily SRS schedule allows. Usage: /cram [N], default 50, max 500.
    """
    user = await container.users_repo.get(message.from_user.id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    parts = (message.text or "").split()
    try:
        n = int(parts[1]) if len(parts) > 1 else 50
    except ValueError:
        n = 50
    if n < 1 or n > 500:
        await message.answer(i18n.message.cram_bad_n())
        return

    batch_id = await container.batch.issue_next_batch(user, size_override=n)
    if batch_id is None:
        await message.answer(i18n.message.no_more_words())
        return
    user = await container.users_repo.get(message.from_user.id)
    session = await container.learning.build_session(user, cap=n)
    if not session:
        await message.answer(i18n.message.nothing_due())
        return
    await state.set_state(LearnSG.waiting_answer)
    await state.update_data(
        user_id=message.from_user.id,
        queue=_hex_ids(session),
    )
    await message.answer(i18n.message.cram_started(n=len(session)))
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.message(LearnSG.waiting_answer, F.text)
async def on_answer(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    if not queue:
        await state.clear()
        return
    word_id_hex = queue[0]
    word_id = ObjectId(word_id_hex)
    user = await container.users_repo.get(message.from_user.id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        await state.clear()
        return
    card = await container.cards_repo.get(message.from_user.id, word_id)
    if card is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        await _show_next(message.chat.id, message.bot, state, container, i18n)
        return

    outcome = await container.learning.evaluate_answer(user, card, message.text)
    if outcome.correct:
        await message.answer(i18n.message.answer_correct(word=outcome.correct_english))
    else:
        await message.answer(
            i18n.message.answer_wrong(
                expected=outcome.correct_english,
                got=message.text,
            )
        )
    if outcome.next_batch_issued:
        await message.answer(i18n.message.new_batch_issued())

    queue.pop(0)
    await state.update_data(queue=queue)
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.callback_query(LearnSG.waiting_answer, F.data.startswith("card:skip:"))
async def on_skip(
    callback: CallbackQuery,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    word_id_hex = callback.data.split(":", 2)[2]
    user = await container.users_repo.get(callback.from_user.id)
    if user is None:
        await callback.answer()
        return
    await container.learning.skip_today(
        callback.from_user.id,
        ObjectId(word_id_hex),
        user["tz"],
        datetime.now(timezone.utc),
    )
    await callback.answer(i18n.message.skipped_today())
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    if queue and queue[0] == word_id_hex:
        queue.pop(0)
        await state.update_data(queue=queue)
    await _show_next(callback.message.chat.id, callback.message.bot, state, container, i18n)


@router.callback_query(LearnSG.waiting_answer, F.data.startswith("card:hard:"))
async def on_hard(
    callback: CallbackQuery,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    word_id_hex = callback.data.split(":", 2)[2]
    await container.learning.mark_hard(callback.from_user.id, ObjectId(word_id_hex), True)
    await callback.answer(i18n.message.marked_hard())
