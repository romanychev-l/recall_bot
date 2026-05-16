from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from fluentogram import TranslatorRunner

from bot.container import Container

router = Router(name="actions")


@router.message(Command("skip"))
async def cmd_skip_help(
    message: Message,
    i18n: TranslatorRunner,
) -> None:
    await message.answer(i18n.message.skip_only_inline())


@router.message(Command("hard"))
async def cmd_hard_help(
    message: Message,
    i18n: TranslatorRunner,
) -> None:
    await message.answer(i18n.message.hard_only_inline())
