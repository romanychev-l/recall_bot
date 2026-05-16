from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from fluentogram import TranslatorRunner

from bot.container import Container

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    container: Container,
    i18n: TranslatorRunner,
) -> None:
    uid = message.from_user.id
    user = await container.users_repo.get(uid)
    if user is None:
        await message.answer(i18n.message.not_onboarded())
        return
    graduated = await container.stats.graduated_count(uid)
    accuracy = await container.stats.accuracy_7d(uid)
    streak = await container.stats.streak(uid)
    cefr = await container.stats.cefr_progress(uid)
    cefr_lines = "\n".join(
        f"  {level}: {v['graduated']}/{v['total']}"
        for level, v in cefr.items()
    )
    text = i18n.message.stats_summary(
        graduated=graduated,
        accuracy=f"{accuracy * 100:.0f}%",
        streak=streak,
        cefr=cefr_lines,
    )
    await message.answer(text)
