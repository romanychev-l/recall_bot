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
    counts = await container.stats.state_counts(uid)
    accuracy = await container.stats.accuracy_7d(uid)
    streak = await container.stats.streak(uid)
    today_correct, today_total = await container.stats.today_counts(uid, user["tz"])
    cefr = await container.stats.cefr_progress(uid)
    cefr_lines = "\n".join(
        f"  {level}: {v['graduated']}/{v['total']}"
        for level, v in cefr.items()
    )
    text = i18n.message.stats_summary(
        learning=counts.get("learning", 0),
        review=counts.get("review", 0),
        graduated=counts.get("graduated", 0),
        today_correct=today_correct,
        today_total=today_total,
        accuracy=f"{accuracy * 100:.0f}%" if today_total > 0 or counts.get("review", 0) > 0 else "—",
        streak=streak,
        next_rank=user.get("next_batch_start_rank", 0),
        cefr=cefr_lines,
    )
    await message.answer(text)
