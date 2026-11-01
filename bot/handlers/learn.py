from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fluentogram import TranslatorRunner

from bot.container import Container
from bot.domain.parts_of_speech import ALL_POS, study_word
from bot.states.learning import LearnSG
from bot.utils.keyboards import answer_actions_kb, learning_actions_kb

logger = logging.getLogger(__name__)
router = Router(name="learn")


def _queue_ids(cards: list[dict]) -> list[str]:
    """Word ids as strings — FSM storage round-trips them as JSON."""
    return [str(c["word_id"]) for c in cards]


def _parse_id(raw: str) -> Optional[int]:
    """Word id from FSM/callback data, or None if it is not a valid id."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("bad_word_id raw=%r", raw)
        return None


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
        await bot.send_message(
            chat_id, i18n.message.session_done(),
            reply_markup=learning_actions_kb(i18n, can_continue=True),
        )
        await state.clear()
        return False
    word_id_str = queue[0]
    word_id = _parse_id(word_id_str)
    card = (
        await container.cards_repo.get(user_id, word_id)
        if word_id is not None
        else None
    )
    if card is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n)
    word = await container.words_repo.by_id(card["word_id"])
    if word is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n)
    user = await container.users_repo.get(user_id)
    mask = (user or {}).get("pos_filter", ALL_POS) & card.get("study_pos_filter", ALL_POS)
    word = study_word(word, await container.words_repo.senses(card["word_id"]), mask)
    if word is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n)
    text = i18n.message.prompt_word(
        translation=word["translation"],
        remaining=len(queue),
        pos=word.get("pos") or "—",
    )
    await bot.send_message(chat_id, text, reply_markup=answer_actions_kb(i18n, word_id_str))
    return True


@router.message(Command("learn"))
async def cmd_learn(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    await _start_learning(message, message.from_user.id, state, container, i18n)


async def _start_learning(
    message: Message, user_id: int, state: FSMContext,
    container: Container, i18n: TranslatorRunner,
) -> None:
    user = await container.users_repo.get(user_id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    session = await container.learning.build_session(user)
    if not session:
        await state.clear()
        await message.answer(
            (i18n.message.nothing_due_filtered() if user.get("pos_filter", ALL_POS) != ALL_POS
             else i18n.message.nothing_due()), reply_markup=learning_actions_kb(i18n)
        )
        return
    await state.set_state(LearnSG.waiting_answer)
    await state.set_data({"user_id": user_id, "queue": _queue_ids(session)})
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.message(Command("more", "cram"))
async def cmd_cram(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
    command: CommandObject,
) -> None:
    """Force-issue a custom-size batch of NEW words and start a session.

    Use when you want to blast through known vocabulary faster than the
    daily SRS schedule allows. /more defaults to the user's batch size;
    the existing /cram alias keeps its default of 50. Both accept 1..500.
    """
    user = await container.users_repo.get(message.from_user.id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    parts = (command.args or "").split()
    try:
        if len(parts) > 1:
            raise ValueError
        default_size = 50 if command.command == "cram" else user["batch_size"]
        n = int(parts[0]) if parts else default_size
    except ValueError:
        await message.answer(i18n.message.cram_bad_n())
        return
    if n < 1 or n > 500:
        await message.answer(i18n.message.cram_bad_n())
        return

    await _add_words(message, user, n, state, container, i18n)


async def _add_words(
    message: Message, user: dict, n: int, state: FSMContext,
    container: Container, i18n: TranslatorRunner,
) -> None:
    batch_id = await container.batch.issue_next_batch(user, size_override=n)
    if batch_id is None:
        text = (i18n.message.no_matching_words() if user.get("pos_filter", ALL_POS) != ALL_POS
                else i18n.message.no_more_words())
        await message.answer(text)
        return
    # A request for new words starts those words immediately, even if reviews
    # could otherwise fill the entire session. Existing schedules stay intact.
    session = await container.cards_repo.find_new_in_batch(user["id"], batch_id, n)
    if not session:
        await message.answer(i18n.message.nothing_due())
        return
    await state.set_state(LearnSG.waiting_answer)
    await state.set_data({"user_id": user["id"], "queue": _queue_ids(session)})
    await message.answer(i18n.message.cram_started(n=len(session)))
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.callback_query(F.data == "learn:more")
async def on_more_words(
    callback: CallbackQuery, state: FSMContext, container: Container,
    i18n: TranslatorRunner,
) -> None:
    await callback.answer()
    user = await container.users_repo.get(callback.from_user.id)
    if user is None:
        await callback.message.answer(i18n.message.not_onboarded())
        return
    await _add_words(callback.message, user, user["batch_size"], state, container, i18n)


@router.callback_query(F.data == "learn:continue")
async def on_continue_learning(
    callback: CallbackQuery, state: FSMContext, container: Container,
    i18n: TranslatorRunner,
) -> None:
    await callback.answer()
    await _start_learning(callback.message, callback.from_user.id, state, container, i18n)


@router.message(LearnSG.waiting_answer, F.text, ~F.text.startswith("/"))
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
    word_id_str = queue[0]
    word_id = _parse_id(word_id_str)
    user = await container.users_repo.get(message.from_user.id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        await state.clear()
        return
    card = (
        await container.cards_repo.get(message.from_user.id, word_id)
        if word_id is not None
        else None
    )
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
    word_id_str = callback.data.split(":", 2)[2]
    word_id = _parse_id(word_id_str)
    user = await container.users_repo.get(callback.from_user.id)
    if user is None or word_id is None:
        await callback.answer()
        return
    await container.learning.skip_today(
        callback.from_user.id,
        word_id,
        user["tz"],
        datetime.now(timezone.utc),
    )
    await callback.answer(i18n.message.skipped_today())
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    if queue and queue[0] == word_id_str:
        queue.pop(0)
        await state.update_data(queue=queue)
    await _show_next(callback.message.chat.id, callback.message.bot, state, container, i18n)


@router.callback_query(LearnSG.waiting_answer, F.data.startswith("card:dontknow:"))
async def on_dont_know(
    callback: CallbackQuery,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    """User gives up — reveal the word, count as wrong, mark hard, advance."""
    word_id_str = callback.data.split(":", 2)[2]
    word_id = _parse_id(word_id_str)
    user = await container.users_repo.get(callback.from_user.id)
    if user is None or word_id is None:
        await callback.answer()
        return
    card = await container.cards_repo.get(callback.from_user.id, word_id)
    if card is None:
        await callback.answer()
        return

    outcome = await container.learning.evaluate_answer(user, card, "", )
    await container.learning.mark_hard(callback.from_user.id, word_id, True)
    await callback.message.answer(
        i18n.message.answer_revealed(word=outcome.correct_english)
    )

    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    if queue and queue[0] == word_id_str:
        queue.pop(0)
        await state.update_data(queue=queue)
    await callback.answer()
    await _show_next(callback.message.chat.id, callback.message.bot, state, container, i18n)
