import asyncio
import logging
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fluentogram import TranslatorHub

from bot.config_data.config import config_settings, db
from bot.container import build_container
from bot.handlers.actions import router as actions_router
from bot.handlers.fallback import router as fallback_router
from bot.handlers.help import router as help_router
from bot.handlers.learn import router as learn_router
from bot.handlers.settings import router as settings_router
from bot.handlers.start import router as start_router
from bot.handlers.stats import router as stats_router
from bot.logging_setup import configure_logging
from bot.middlewares.container import ContainerMiddleware
from bot.middlewares.i18n import TranslatorRunnerMiddleware
from bot.scheduler.jobs import daily_reminder
from bot.utils.i18n import create_translator_hub

configure_logging(config_settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(
        token=config_settings.TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    translator_hub: TranslatorHub = create_translator_hub()

    scheduler = AsyncIOScheduler(timezone=config_settings.SCHEDULER_TZ)
    # Bind bot+container later: send_reminder needs container, container needs scheduler.
    container_ref: dict = {}

    async def send_reminder(user_id: int) -> None:
        c = container_ref.get("container")
        if c is None:
            return
        await daily_reminder(bot, c, user_id)

    container = build_container(
        db, scheduler=scheduler, send_reminder=send_reminder
    )
    container_ref["container"] = container

    # Ensure indexes
    await container.words_repo.ensure_indexes()
    await container.cards_repo.ensure_indexes()
    await container.review_log_repo.ensure_indexes()

    dp.include_router(start_router)
    dp.include_router(help_router)
    dp.include_router(learn_router)
    dp.include_router(stats_router)
    dp.include_router(settings_router)
    dp.include_router(actions_router)
    dp.include_router(fallback_router)

    dp.update.middleware(ContainerMiddleware(container))
    dp.update.middleware(TranslatorRunnerMiddleware())

    scheduler.start()
    await container.reminder.reschedule_all()
    logger.info("Bot starting...")

    try:
        await dp.start_polling(bot, _translator_hub=translator_hub)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped")


asyncio.run(main())
