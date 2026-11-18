from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fluentogram import TranslatorRunner

from bot.container import Container
from bot.domain.parts_of_speech import ALL_POS, study_word
from bot.states.learning import LearnSG
from bot.states.settings import SettingsSG
from bot.utils.keyboards import answer_actions_kb, learning_actions_kb

logger = logging.getLogger(__name__)
router = Router(name="learn")


def _with_examples(text: str, example: str, i18n: TranslatorRunner) -> str:
    """Keep examples in the answer message, safely inside Telegram HTML."""
    examples = [line.strip() for line in example.splitlines() if line.strip()][:2]
    if not examples:
        return text
    rendered = "\n".join(f"• <i>{escape(line)}</i>" for line in examples)
    return text + "\n\n" + i18n.message.usage_examples(examples=rendered)


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
    *, notify_done: bool = True,
) -> bool:
    data = await state.get_data()
    reverse = data.get("reverse", False)
    queue: list[str] = data.get("queue", [])
    user_id = data.get("user_id")
    if not queue:
        if notify_done:
            await bot.send_message(
                chat_id, i18n.message.session_done(),
                reply_markup=learning_actions_kb(i18n, can_continue=True, reverse=reverse),
            )
        await state.clear()
        await state.update_data(reverse=reverse)
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
        return await _show_next(chat_id, bot, state, container, i18n, notify_done=notify_done)
    word = await container.words_repo.by_id(card["word_id"])
    if word is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n, notify_done=notify_done)
    user = await container.users_repo.get(user_id)
    mask = (user or {}).get("pos_filter", ALL_POS) & card.get("study_pos_filter", ALL_POS)
    word = study_word(word, await container.words_repo.senses(card["word_id"]), mask)
    if word is None:
        queue.pop(0)
        await state.update_data(queue=queue)
        return await _show_next(chat_id, bot, state, container, i18n, notify_done=notify_done)
    if reverse:
        text = i18n.message.prompt_reverse(
            word=escape(word["english"]), remaining=len(queue),
            pos=escape(word.get("pos") or "—"),
        )
    else:
        text = i18n.message.prompt_word(
            translation=escape(word["translation"]), remaining=len(queue),
            pos=escape(word.get("pos") or "—"),
        )
    sent = await bot.send_message(
        chat_id, text, reply_markup=answer_actions_kb(i18n, word_id_str, reverse=reverse),
    )
    logger.info("study_prompt_sent user_id=%s word_id=%s remaining=%s message_id=%s reverse=%s",
                user_id, word_id_str, len(queue), getattr(sent, "message_id", None), reverse)
    return True


async def _answer_card_callback(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest as error:
        # A delayed callback acknowledgement must not prevent the next card.
        if not any(reason in error.message.lower() for reason in ("query is too old", "query id is invalid")):
            raise
        logger.info("card_callback_expired user_id=%s", callback.from_user.id)


async def _refresh_card(callback: CallbackQuery, state: FSMContext,
                        container: Container, i18n: TranslatorRunner) -> None:
    await _answer_card_callback(callback, i18n.message.card_refreshed())
    data = await state.get_data()
    logger.info("card_button_stale user_id=%s callback=%s current_word=%s",
                callback.from_user.id, callback.data, (data.get("queue") or [None])[0])
    if await state.get_state() == LearnSG.waiting_answer.state and data.get("queue"):
        await _show_next(callback.message.chat.id, callback.message.bot, state, container, i18n)
    else:
        await _start_learning(callback.message, callback.from_user.id, state, container, i18n,
                              reverse=callback.data.startswith("reversecard:"))


async def send_learning_reminder(
    bot, state: FSMContext, container: Container, i18n: TranslatorRunner, user: dict,
) -> bool:
    """Send one answerable card, preserving active sessions and other dialogs.

    The caller holds the dispatcher's event-isolation lock for this user.
    """
    previous_state = await state.get_state()
    if previous_state not in (None, LearnSG.waiting_answer.state, SettingsSG.menu.state):
        return False
    previous_data = deepcopy(await state.get_data())
    try:
        if previous_state != LearnSG.waiting_answer.state or not previous_data.get("queue"):
            session = await container.learning.build_session(user)
            if not session:
                return False
            await state.set_state(LearnSG.waiting_answer)
            await state.set_data({
                "user_id": user["id"], "queue": _queue_ids(session),
                "reverse": previous_data.get("reverse", False),
            })
        return await _show_next(user["id"], bot, state, container, i18n, notify_done=False)
    except Exception:
        # A failed Telegram delivery must not replace the user's current dialog.
        await state.set_data(previous_data)
        await state.set_state(previous_state)
        raise


@router.message(Command("learn"))
async def cmd_learn(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    await _start_learning(message, message.from_user.id, state, container, i18n)


@router.message(Command("reverse"))
async def cmd_reverse(
    message: Message, state: FSMContext, container: Container,
    i18n: TranslatorRunner,
) -> None:
    await _start_learning(message, message.from_user.id, state, container, i18n, reverse=True)


async def _start_learning(
    message: Message, user_id: int, state: FSMContext,
    container: Container, i18n: TranslatorRunner,
    *, reverse: bool = False,
) -> None:
    user = await container.users_repo.get(user_id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    session = await container.learning.build_session(user)
    if not session:
        await state.clear()
        await state.update_data(reverse=reverse)
        await message.answer(
            (i18n.message.nothing_due_filtered() if user.get("pos_filter", ALL_POS) != ALL_POS
             else i18n.message.nothing_due()),
            reply_markup=learning_actions_kb(i18n, reverse=reverse),
        )
        return
    await state.set_state(LearnSG.waiting_answer)
    await state.set_data({"user_id": user_id, "queue": _queue_ids(session), "reverse": reverse})
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

    reverse = (await state.get_data()).get("reverse", False)
    await _add_words(message, user, n, state, container, i18n, reverse=reverse)


async def _add_words(
    message: Message, user: dict, n: int, state: FSMContext,
    container: Container, i18n: TranslatorRunner,
    *, reverse: bool = False,
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
    await state.set_data({"user_id": user["id"], "queue": _queue_ids(session), "reverse": reverse})
    await message.answer(i18n.message.cram_started(n=len(session)))
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.callback_query(F.data.in_({"learn:more", "reverse:more"}))
async def on_more_words(
    callback: CallbackQuery, state: FSMContext, container: Container,
    i18n: TranslatorRunner,
) -> None:
    await callback.answer()
    user = await container.users_repo.get(callback.from_user.id)
    if user is None:
        await callback.message.answer(i18n.message.not_onboarded())
        return
    await _add_words(
        callback.message, user, user["batch_size"], state, container, i18n,
        reverse=callback.data == "reverse:more",
    )


@router.callback_query(F.data.in_({"learn:continue", "reverse:continue"}))
async def on_continue_learning(
    callback: CallbackQuery, state: FSMContext, container: Container,
    i18n: TranslatorRunner,
) -> None:
    await callback.answer()
    await _start_learning(
        callback.message, callback.from_user.id, state, container, i18n,
        reverse=callback.data == "reverse:continue",
    )


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

    reverse = data.get("reverse", False)
    outcome = await container.learning.evaluate_answer(user, card, message.text, reverse=reverse)
    expected = escape(outcome.correct_translation if reverse else outcome.correct_english)
    if outcome.correct:
        feedback = i18n.message.answer_correct(word=expected)
    else:
        feedback = i18n.message.answer_wrong(
            expected=expected,
            got=escape(message.text),
        )
    await message.answer(_with_examples(feedback, outcome.example, i18n))
    if outcome.next_batch_issued:
        await message.answer(i18n.message.new_batch_issued())

    queue.pop(0)
    await state.update_data(queue=queue)
    await _show_next(message.chat.id, message.bot, state, container, i18n)


@router.callback_query(LearnSG.waiting_answer, F.data.startswith(("card:skip:", "reversecard:skip:")))
async def on_skip(
    callback: CallbackQuery,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    word_id_str = callback.data.split(":", 2)[2]
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    if (not queue or queue[0] != word_id_str
            or callback.data.startswith("reversecard:") != data.get("reverse", False)):
        await _refresh_card(callback, state, container, i18n)
        return
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
    await _answer_card_callback(callback, i18n.message.skipped_today())
    if queue and queue[0] == word_id_str:
        queue.pop(0)
        await state.update_data(queue=queue)
    await _show_next(callback.message.chat.id, callback.message.bot, state, container, i18n)


@router.callback_query(LearnSG.waiting_answer, F.data.startswith(("card:dontknow:", "reversecard:dontknow:")))
async def on_dont_know(
    callback: CallbackQuery,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    """User gives up — reveal the word, count as wrong, mark hard, advance."""
    word_id_str = callback.data.split(":", 2)[2]
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])
    reverse = data.get("reverse", False)
    if (not queue or queue[0] != word_id_str
            or callback.data.startswith("reversecard:") != reverse):
        await _refresh_card(callback, state, container, i18n)
        return
    word_id = _parse_id(word_id_str)
    user = await container.users_repo.get(callback.from_user.id)
    if user is None or word_id is None:
        await callback.answer()
        return
    card = await container.cards_repo.get(callback.from_user.id, word_id)
    if card is None:
        await callback.answer()
        return

    await _answer_card_callback(callback)
    outcome = await container.learning.evaluate_answer(user, card, "", reverse=reverse)
    await container.learning.mark_hard(callback.from_user.id, word_id, True)
    # The answer is already committed. A failed feedback send must not let
    # another click record the same answer again.
    queue.pop(0)
    await state.update_data(queue=queue)
    await callback.message.answer(
        _with_examples(
            i18n.message.answer_revealed(word=escape(
                outcome.correct_translation if reverse else outcome.correct_english
            )),
            outcome.example, i18n,
        )
    )

    await _show_next(callback.message.chat.id, callback.message.bot, state, container, i18n)


@router.callback_query(F.data.startswith(("card:skip:", "card:dontknow:",
                                         "reversecard:skip:", "reversecard:dontknow:")))
async def recover_card_button(
    callback: CallbackQuery, state: FSMContext, container: Container, i18n: TranslatorRunner,
) -> None:
    # After a restart or another dialog, show an answerable card without
    # treating an old click as a new review or postponing the wrong word.
    await _refresh_card(callback, state, container, i18n)
