from __future__ import annotations

import logging

from aiogram import Bot

from bot.container import Container

logger = logging.getLogger(__name__)


async def daily_reminder(bot: Bot, container: Container, user_id: int) -> None:
    """Send a daily reminder to a user."""
    user = await container.users_repo.get(user_id)
    if user is None:
        return
    try:
        translator = None
        # Best-effort: use Russian by default for reminders; UI is localized at runtime
        text = "Пора учить слова! /learn" if user.get("language", "ru") == "ru" else "Time to study! /learn"
        await bot.send_message(user_id, text)
        logger.info("reminder_sent user_id=%s", user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reminder_failed user_id=%s reason=%s", user_id, exc)
