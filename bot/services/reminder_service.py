from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.repositories.users_repo import UsersRepo

logger = logging.getLogger(__name__)


def _job_id(user_id: int) -> str:
    return f"reminder:{user_id}"


class ReminderService:
    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        users_repo: UsersRepo,
        send_reminder,
    ) -> None:
        self.scheduler = scheduler
        self.users_repo = users_repo
        self.send_reminder = send_reminder

    async def reschedule_all(self) -> None:
        users = await self.users_repo.all()
        for user in users:
            self.schedule_user(user)
        logger.info("reminders_scheduled count=%s", len(users))

    def schedule_user(self, user: dict) -> None:
        try:
            hh, mm = user["reminder_time"].split(":")
            tz = ZoneInfo(user["tz"])
        except Exception as exc:  # noqa: BLE001 — bad user data shouldn't crash
            logger.warning("reminder_skip user_id=%s reason=%s", user["_id"], exc)
            return
        trigger = CronTrigger(hour=int(hh), minute=int(mm), timezone=tz)
        self.scheduler.add_job(
            self.send_reminder,
            trigger=trigger,
            args=[user["_id"]],
            id=_job_id(user["_id"]),
            replace_existing=True,
        )

    def cancel_user(self, user_id: int) -> None:
        try:
            self.scheduler.remove_job(_job_id(user_id))
        except Exception:  # noqa: BLE001
            pass
