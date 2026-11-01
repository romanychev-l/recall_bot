"""Publish Telegram's slash suggestions and the command menu at startup."""
import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats, MenuButtonCommands
from fluentogram import TranslatorHub

COMMANDS = ("learn", "more", "stats", "settings", "help", "start", "cram", "skip", "hard")
logger = logging.getLogger(__name__)


async def register_commands(bot: Bot, hub: TranslatorHub) -> None:
    for language_code in ("", "ru", "en"):
        i18n = hub.get_translator_by_locale(language_code or "ru")
        commands = [
            BotCommand(command=name, description=i18n.get(f"command-{name}"))
            for name in COMMANDS
        ]
        await bot.set_my_commands(
            commands, scope=BotCommandScopeDefault(), language_code=language_code
        )
        group_commands = {
            "challenge": "Создать таблицу слов", "leaders": "Статистика участников",
            "join": "Вступить в таблицу чата", "leave": "Выйти из таблицы чата",
            "settings": "Расписание вечерних сводок", "pause": "Приостановить сводки",
            "resume": "Возобновить сводки", "help_group": "Правила и команды группы",
        } if language_code != "en" else {
            "challenge": "Create a group leaderboard", "leaders": "Group vocabulary statistics",
            "join": "Join the group leaderboard", "leave": "Leave this leaderboard",
            "settings": "Evening report schedule", "pause": "Pause evening reports",
            "resume": "Resume evening reports", "help_group": "Group help and commands",
        }
        await bot.set_my_commands(
            [BotCommand(command=name, description=description) for name, description in group_commands.items()],
            scope=BotCommandScopeAllGroupChats(), language_code=language_code,
        )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("bot_commands_registered count=%s group_count=%s languages=default,ru,en",
                len(COMMANDS), len(group_commands))
