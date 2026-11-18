from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from fluentogram import TranslatorHub

from bot.container import Container
from bot.handlers.learn import send_learning_reminder

logger = logging.getLogger(__name__)


async def daily_reminder(
    bot: Bot, container: Container, user_id: int,
    *, dispatcher: Dispatcher, translator_hub: TranslatorHub,
) -> None:
    """Start or resume a private quiz directly in the polling FSM."""
    try:
        state = dispatcher.fsm.get_context(bot=bot, chat_id=user_id, user_id=user_id)
        async with dispatcher.fsm.events_isolation.lock(key=state.key):
            user = await container.users_repo.get(user_id)
            if user is None:
                return
            i18n = translator_hub.get_translator_by_locale(user.get("language") or "ru")
            sent = await send_learning_reminder(bot, state, container, i18n, user)
        logger.info("%s user_id=%s", "reminder_sent" if sent else "reminder_skipped", user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reminder_failed user_id=%s reason=%s", user_id, exc)
