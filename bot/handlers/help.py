from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from fluentogram import TranslatorRunner

router = Router(name="help")


@router.message(Command("help"))
async def cmd_help(message: Message, i18n: TranslatorRunner) -> None:
    await message.answer(i18n.message.help())
