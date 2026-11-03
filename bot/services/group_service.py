"""Opt-in group standings and durable evening publication schedules."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from html import escape
from math import ceil
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramMigrateToChat, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.triggers.cron import CronTrigger

from bot.repositories.groups_repo import GroupsRepo

logger = logging.getLogger(__name__)
PAGE_SIZE = 15
GROUP_HELP = (
    "📚 <b>Слова нашего чата</b>\n\n"
    "/challenge — создать таблицу и вступить первым\n"
    "/leaders — показать статистику участников\n"
    "/join — вступить; /leave — выйти из таблицы этого чата\n"
    "/settings — расписание; /settings 21:00 Europe/Moscow — изменить\n"
    "/pause и /resume — приостановить и возобновить сводки\n"
    "/help_group — эта справка\n\n"
    "Учите слова в личном чате с Recall. Здесь видны только имена и счётчики "
    "участников, которые нажали «Вступить». Кнопка «Открыть бота» сама по себе "
    "не добавляет в таблицу.\n\n"
    "Освоено — слова на повторении и полностью выученные. Сегодня — разные слова "
    "с верным ответом за текущий день по часовому поясу группы. Общий счёт "
    "включает обучение до вступления и не сбрасывается по неделям.\n\n"
    "Практика — ещё не освоенные слова, использованные сегодня в сообщениях "
    "в доступных боту группах. Учитываются все пользователи Recall, даже без "
    "вступления в таблицу; сама таблица показывает только участников. "
    "Карточки от этого не считаются выученными.\n\n"
    "Для чтения обычных сообщений бот должен быть администратором группы "
    "или Privacy Mode должен быть отключён в BotFather.\n\n"
    "По умолчанию сводка приходит в 21:00. Расписание меняют организатор "
    "и администраторы. Используй команды с именем бота, если в чате несколько ботов."
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_schedule(report_time: str, zone_name: str) -> None:
    try:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", report_time):
            raise ValueError
        ZoneInfo(zone_name)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Используй время ЧЧ:ММ и часовой пояс: /settings 21:00 Europe/Moscow") from None


def next_report_at(report_time: str, zone_name: str, now: datetime) -> datetime:
    validate_schedule(report_time, zone_name)
    hour, minute = map(int, report_time.split(":"))
    trigger = CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(zone_name))
    # Advance even when called at exactly the previous report's scheduled time.
    return trigger.get_next_fire_time(None, now + timedelta(seconds=1)).astimezone(timezone.utc)


def ranking_text(group: dict, standings: list[dict], now: datetime, page: int = 1) -> tuple[str, int, int]:
    local = now.astimezone(ZoneInfo(group["timezone"]))
    pages = max(1, ceil(len(standings) / PAGE_SIZE))
    page = min(max(page, 1), pages)
    lines = ["📚 <b>Слова нашего чата</b>", local.strftime("%d.%m.%Y"),
             "Освоено всего · правильно сегодня · практика сегодня", ""]
    previous = None
    place = 0
    for index, row in enumerate(standings):
        score = row["learned"], row["today"]
        if score != previous:
            place = index + 1
        previous = score
        if (page - 1) * PAGE_SIZE <= index < page * PAGE_SIZE:
            name = escape(row["display_name"])
            lines.append(f"{place}. {name} — <b>{row['learned']}</b> · {row['today']} · {row.get('practice', 0)}")
    if not standings:
        lines.append("Пока нет участников. Нажми «Вступить» и учи слова в личном чате с ботом.")
    lines += ["", "Освоено: на повторении и полностью выученные слова.",
              "Сегодня: разные слова с верным ответом; день по " + escape(group["timezone"]) + "."]
    lines.append('Практика: разные ещё не освоенные слова, использованные в доступных боту группах.')
    status = "Сводки на паузе" if not group["enabled"] else "Ежедневная сводка в " + group["report_time"]
    lines += [status, "Участие добровольное · /leave — выйти из таблицы."]
    if pages > 1:
        lines.append(f"Страница {page}/{pages} · /leaders НОМЕР")
    return "\n".join(lines), page, pages


class GroupService:
    def __init__(self, bot, repository: GroupsRepo, scheduler) -> None:
        self.bot = bot
        self.repository = repository
        self.scheduler = scheduler
        self._locks: dict[int, asyncio.Lock] = {}
        self._refresh_after: dict[tuple[int, int], float] = {}
        self._username: str | None = None

    def lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    def reserve_refresh(self, chat_id: int, message_id: int) -> int:
        now = monotonic()
        self._refresh_after = {key: until for key, until in self._refresh_after.items() if until > now}
        key = chat_id, message_id
        if key in self._refresh_after:
            return ceil(self._refresh_after[key] - now)
        self._refresh_after[key] = now + 5
        return 0

    async def bot_url(self) -> str:
        if self._username is None:
            self._username = (await self.bot.get_me()).username
        return f"https://t.me/{self._username}"

    async def keyboard(self, page: int = 1, pages: int = 1, *, include_join: bool = True) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text="Вступить", callback_data="group:join"),
                 InlineKeyboardButton(text="Открыть бота", url=await self.bot_url())],
                [InlineKeyboardButton(text="Обновить", callback_data=f"group:refresh:{page}")]]
        navigation = []
        if page > 1:
            navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"group:refresh:{page-1}"))
        if page < pages:
            navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"group:refresh:{page+1}"))
        if navigation:
            rows.append(navigation)
        if not include_join:
            rows = [[rows[0][1]]]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def join(self, chat_id: int, user, now: datetime | None = None) -> bool:
        name = " ".join(user.full_name.split())[:32] or "Участник"
        return await self.repository.join(chat_id, user.id, name, now or utc_now())

    async def create(self, message, user_timezone: str) -> None:
        now = utc_now()
        async with self.lock(message.chat.id):
            created = await self.repository.create({
                "id": message.chat.id, "title": (message.chat.title or "Чат")[:255],
                "creator_id": message.from_user.id, "timezone": user_timezone,
                "report_time": "21:00", "enabled": True, "bot_present": True,
                "thread_id": message.message_thread_id, "message_id": None,
                "next_report_at": next_report_at("21:00", user_timezone, now), "created_at": now,
            })
            group = await self.repository.get(message.chat.id)
            # A retry after an interrupted creation also finishes the creator's join.
            if created or group["creator_id"] == message.from_user.id:
                await self.join(group["id"], message.from_user, now)
            await self.repository.update(group["id"], bot_present=True)
            await self.publish(group, now=now)

    async def publish(self, group: dict, *, now: datetime | None = None,
                      edit: bool = False, message_id: int | None = None, page: int = 1) -> None:
        now = now or utc_now()
        local = now.astimezone(ZoneInfo(group["timezone"]))
        since = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        standings = await self.repository.standings(group["id"], since, now)
        text, page, pages = ranking_text(group, standings, now, page)
        keyboard = await self.keyboard(page, pages)
        target = message_id if message_id is not None else group.get("message_id")
        if (edit or message_id is not None) and target:
            try:
                await self.bot.edit_message_text(chat_id=group["id"], message_id=target,
                                                 text=text, reply_markup=keyboard)
                return
            except TelegramBadRequest as error:
                reason = error.message.lower()
                if "message is not modified" in reason:
                    return
                missing = any(s in reason for s in ("message to edit not found", "message can't be edited"))
                if message_id is not None or not missing:
                    raise
        sent = await self.bot.send_message(chat_id=group["id"], message_thread_id=group.get("thread_id"),
                                          text=text, reply_markup=keyboard)
        await self.repository.update(group["id"], message_id=sent.message_id)

    async def tick(self, now: datetime | None = None) -> None:
        now = now or utc_now()
        try:
            due = await self.repository.due(now)
        except Exception:
            logger.exception("group_reports_load_failed")
            return
        for pending in due:
            async with self.lock(pending["id"]):
                group = await self.repository.get(pending["id"])
                if not group or not group["enabled"] or not group["bot_present"] or group["next_report_at"] > now:
                    continue
                try:
                    await self.publish(group, now=now)
                    await self.repository.update(group["id"], next_report_at=next_report_at(
                        group["report_time"], group["timezone"], now))
                    logger.info("group_report_sent chat_id=%s", group["id"])
                except TelegramForbiddenError:
                    await self.repository.update(group["id"], bot_present=False)
                except TelegramRetryAfter as error:
                    await self.repository.update(group["id"], next_report_at=now + timedelta(seconds=error.retry_after))
                except TelegramMigrateToChat as error:
                    await self.repository.migrate(group["id"], error.migrate_to_chat_id)
                except TelegramBadRequest as error:
                    if any(s in error.message.lower() for s in ("chat not found", "not enough rights", "bot was kicked")):
                        await self.repository.update(group["id"], bot_present=False)
                    else:
                        await self.repository.update(group["id"], next_report_at=now + timedelta(minutes=5))
                    logger.warning("group_report_failed chat_id=%s reason=%s", group["id"], error)
                except Exception:
                    await self.repository.update(group["id"], next_report_at=now + timedelta(minutes=5))
                    logger.exception("group_report_failed chat_id=%s", group["id"])

    def start(self) -> None:
        self.scheduler.add_job(self.tick, "interval", seconds=30, id="group_reports",
                               replace_existing=True, max_instances=1, coalesce=True,
                               misfire_grace_time=60)
        logger.info("group_reports_scheduler_started")
