from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fluentogram import TranslatorRunner

from bot.container import Container
from bot.states.onboarding import OnboardSG

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    await state.clear()
    from bot.utils.keyboards import onboarding_kb
    await message.answer(i18n.message.welcome(), reply_markup=onboarding_kb(i18n))
    await state.set_state(OnboardSG.choose_start)


@router.callback_query(OnboardSG.choose_start, F.data == "onboard:zero")
async def onboard_from_zero(
    callback: CallbackQuery,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    await container.onboarding.start(callback.from_user.id, initial_rank=1)
    await callback.message.answer(i18n.message.onboarded_zero())
    await callback.message.answer(i18n.message.try_learn_hint())
    await state.clear()
    await callback.answer()


@router.callback_query(OnboardSG.choose_start, F.data == "onboard:skip")
async def onboard_ask_skip_n(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await callback.message.answer(i18n.message.ask_skip_n())
    await state.set_state(OnboardSG.enter_skip_n)
    await callback.answer()


@router.message(OnboardSG.enter_skip_n)
async def onboard_apply_skip_n(
    message: Message,
    state: FSMContext,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    try:
        n = int(message.text.strip())
        if n < 0 or n > 100000:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer(i18n.message.bad_skip_n())
        return
    await container.onboarding.start(
        message.from_user.id, initial_rank=n + 1
    )
    await message.answer(i18n.message.onboarded_skip(n=n))
    await message.answer(i18n.message.try_learn_hint())
    await state.clear()
