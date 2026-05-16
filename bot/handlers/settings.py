from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fluentogram import TranslatorRunner

from bot.container import Container
from bot.states.settings import SettingsSG
from bot.utils.keyboards import settings_kb

router = Router(name="settings")

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


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
        i18n.message.settings_summary(
            batch=user["batch_size"],
            reminder=user["reminder_time"],
            tz=user["tz"],
        ),
        reply_markup=settings_kb(i18n),
    )


@router.callback_query(SettingsSG.menu, F.data == "settings:batch")
async def ask_batch(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.set_state(SettingsSG.edit_batch_size)
    await callback.message.answer(i18n.message.ask_batch_size())
    await callback.answer()


@router.message(SettingsSG.edit_batch_size)
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


@router.message(SettingsSG.edit_reminder_time)
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


@router.message(SettingsSG.edit_tz)
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
