from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from fluentogram import TranslatorRunner

router = Router(name="fallback")


@router.message()
async def fallback(message: Message, i18n: TranslatorRunner) -> None:
    await message.answer(i18n.message.unknown_command())
