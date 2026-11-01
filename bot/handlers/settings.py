from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fluentogram import TranslatorRunner

from bot.container import Container
from bot.domain.parts_of_speech import ALL_POS, POS_BITS, selected_parts
from bot.states.settings import SettingsSG
from bot.utils.keyboards import parts_of_speech_kb, settings_kb

router = Router(name="settings")

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _pos_label(i18n, mask: int) -> str:
    if mask == ALL_POS:
        return i18n.button.pos_all()
    return ", ".join(i18n.get("pos-" + pos) for pos in selected_parts(mask))


async def _summary(user: dict, container: Container, i18n) -> str:
    mask = user.get("pos_filter", ALL_POS)
    count = await container.words_repo.available_count(user["id"], user["initial_rank"], mask)
    label = _pos_label(i18n, mask)
    return i18n.message.settings_summary(
        batch=user["batch_size"], reminder=user["reminder_time"], tz=user["tz"],
        parts=label, count=count,
    )


@router.message(Command("settings"))
async def cmd_settings(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    user = await container.users_repo.get(message.from_user.id)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    await state.set_state(SettingsSG.menu)
    await message.answer(
        await _summary(user, container, i18n),
        reply_markup=settings_kb(i18n),
    )


async def _pos_menu(user: dict, container: Container, i18n) -> str:
    mask = user.get("pos_filter", ALL_POS)
    count = await container.words_repo.available_count(user["id"], user["initial_rank"], mask)
    label = _pos_label(i18n, mask)
    text = i18n.message.pos_summary(parts=label, count=count)
    if count == 0:
        text += "\n\n" + i18n.message.no_matching_words()
    return text


@router.callback_query(SettingsSG.menu, F.data == "settings:pos")
async def ask_parts(callback: CallbackQuery, state: FSMContext,
                    container: Container, i18n: TranslatorRunner) -> None:
    user = await container.users_repo.get(callback.from_user.id)
    if user is None:
        await callback.answer(i18n.message.not_onboarded())
        return
    await state.set_state(SettingsSG.edit_pos)
    await callback.message.edit_text(await _pos_menu(user, container, i18n),
                                     reply_markup=parts_of_speech_kb(i18n, user["pos_filter"]))
    await callback.answer()


@router.callback_query(SettingsSG.edit_pos, F.data.startswith("pos:"))
async def set_parts(callback: CallbackQuery, state: FSMContext,
                    container: Container, i18n: TranslatorRunner) -> None:
    user = await container.users_repo.get(callback.from_user.id)
    if user is None:
        await callback.answer(i18n.message.not_onboarded())
        return
    if callback.data == "pos:done":
        await state.set_state(SettingsSG.menu)
        await callback.message.edit_text(await _summary(user, container, i18n), reply_markup=settings_kb(i18n))
        await callback.answer(i18n.message.saved())
        return
    mask = user["pos_filter"]
    if callback.data == "pos:all":
        updated = ALL_POS
    else:
        category = callback.data.removeprefix("pos:toggle:")
        if category not in POS_BITS:
            await callback.answer()
            return
        # One tap from 'all' selects a single category; further taps toggle.
        updated = POS_BITS[category] if mask == ALL_POS else mask ^ POS_BITS[category]
    if not updated:
        await callback.answer(i18n.message.pos_empty(), show_alert=True)
        return
    if updated == mask:
        await callback.answer()
        return
    await container.users_repo.update(user["id"], pos_filter=updated)
    user["pos_filter"] = updated
    await callback.message.edit_text(await _pos_menu(user, container, i18n),
                                     reply_markup=parts_of_speech_kb(i18n, updated))
    await callback.answer()


@router.callback_query(SettingsSG.menu, F.data == "settings:batch")
async def ask_batch(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.set_state(SettingsSG.edit_batch_size)
    await callback.message.answer(i18n.message.ask_batch_size())
    await callback.answer()


@router.message(SettingsSG.edit_batch_size, ~F.text.startswith("/"))
async def set_batch(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    try:
        n = int(message.text.strip())
        if n < 1 or n > 100:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer(i18n.message.bad_batch_size())
        return
    await container.users_repo.update(message.from_user.id, batch_size=n, daily_goal=n)
    await message.answer(i18n.message.saved())
    await state.clear()


@router.callback_query(SettingsSG.menu, F.data == "settings:reminder")
async def ask_reminder(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.set_state(SettingsSG.edit_reminder_time)
    await callback.message.answer(i18n.message.ask_reminder_time())
    await callback.answer()


@router.message(SettingsSG.edit_reminder_time, ~F.text.startswith("/"))
async def set_reminder(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    text = (message.text or "").strip()
    if not TIME_RE.match(text):
        await message.answer(i18n.message.bad_reminder_time())
        return
    await container.users_repo.update(message.from_user.id, reminder_time=text)
    user = await container.users_repo.get(message.from_user.id)
    container.reminder.schedule_user(user)
    await message.answer(i18n.message.saved())
    await state.clear()


@router.callback_query(SettingsSG.menu, F.data == "settings:tz")
async def ask_tz(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.set_state(SettingsSG.edit_tz)
    await callback.message.answer(i18n.message.ask_tz())
    await callback.answer()


@router.message(SettingsSG.edit_tz, ~F.text.startswith("/"))
async def set_tz(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    tz = (message.text or "").strip()
    try:
        ZoneInfo(tz)
    except Exception:
        await message.answer(i18n.message.bad_tz())
        return
    await container.users_repo.update(message.from_user.id, tz=tz)
    user = await container.users_repo.get(message.from_user.id)
    container.reminder.schedule_user(user)
    await message.answer(i18n.message.saved())
    await state.clear()
