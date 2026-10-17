from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import insert

from bot.constants import DEFAULT_REMINDER_TIME, DEFAULT_TZ
from bot.container import build_container
from bot.db.models import Word
from bot.handlers.settings import set_reminder, set_tz
from bot.handlers.start import onboard_apply_skip_n, onboard_from_zero
from tests.conftest import make_words


@pytest.fixture
async def scheduler():
    scheduler = AsyncIOScheduler(timezone="UTC")
    # Exercise APScheduler's real job replacement without executing callbacks.
    scheduler.start(paused=True)
    yield scheduler
    scheduler.shutdown(wait=False)


@pytest.fixture
async def container(session_factory, scheduler):
    async with session_factory() as session:
        await session.execute(insert(Word), make_words(70))
        await session.commit()
    return build_container(
        session_factory, scheduler=scheduler, send_reminder=AsyncMock()
    )


async def onboard(container, path, user_id=1):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id), text="50", answer=AsyncMock()
    )
    state = AsyncMock()
    i18n = MagicMock()
    if path == "zero":
        callback = SimpleNamespace(
            from_user=message.from_user, message=message, answer=AsyncMock()
        )
        await onboard_from_zero(callback, state, container, i18n)
    else:
        await onboard_apply_skip_n(message, state, container, i18n)
    return await container.users_repo.get(user_id)


def assert_schedule(job, user_id, reminder_time, tz):
    assert job is not None
    assert job.id == f"reminder:{user_id}"
    assert job.args == (user_id,)
    assert str(job.trigger.timezone) == tz
    next_run = job.trigger.get_next_fire_time(
        None, datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert next_run.astimezone(ZoneInfo(tz)).strftime("%H:%M") == reminder_time


@pytest.mark.parametrize("path", ["zero", "skip"])
@pytest.mark.parametrize("saved_settings", [False, True])
async def test_onboarding_schedules_reminder(container, scheduler, path, saved_settings):
    reminder_time, tz = DEFAULT_REMINDER_TIME, DEFAULT_TZ
    if saved_settings:
        await container.users_repo.create_if_absent(1)
        reminder_time, tz = "08:45", "Asia/Yekaterinburg"
        await container.users_repo.update(1, reminder_time=reminder_time, tz=tz)

    user = await onboard(container, path)

    assert user["initial_rank"] == (1 if path == "zero" else 51)
    assert user["current_batch_id"] is not None
    assert len(scheduler.get_jobs()) == 1
    job = scheduler.get_job("reminder:1")
    assert_schedule(job, 1, reminder_time, tz)
    assert job.func is container.reminder.send_reminder
    container.reminder.send_reminder.assert_not_called()


@pytest.mark.parametrize("path", ["zero", "skip"])
async def test_repeated_onboarding_keeps_one_job_and_progress(container, scheduler, path):
    first = await onboard(container, path)
    await container.users_repo.update(1, reminder_time="21:17", tz="America/New_York")

    second = await onboard(container, path)

    assert len(scheduler.get_jobs()) == 1
    assert_schedule(scheduler.get_job("reminder:1"), 1, "21:17", "America/New_York")
    assert second["current_batch_id"] == first["current_batch_id"]
    assert second["next_batch_start_rank"] == first["next_batch_start_rank"]
    assert await container.cards_repo.count_pending_in_batch(1, first["current_batch_id"]) == 10
    container.reminder.send_reminder.assert_not_called()


@pytest.mark.parametrize(
    ("handler", "text", "reminder_time", "tz"),
    [
        (set_reminder, "07:35", "07:35", DEFAULT_TZ),
        (set_tz, "Asia/Tokyo", DEFAULT_REMINDER_TIME, "Asia/Tokyo"),
    ],
)
async def test_settings_only_reschedule_the_current_user(
    container, scheduler, handler, text, reminder_time, tz
):
    for user_id in (1, 2):
        await container.users_repo.create_if_absent(user_id)
    await container.users_repo.update(2, reminder_time="12:34", tz="Europe/Berlin")
    await container.reminder.reschedule_all()
    other_job = scheduler.get_job("reminder:2")
    other_next_run = other_job.next_run_time
    other_user = await container.users_repo.get(2)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1), text=text, answer=AsyncMock()
    )

    await handler(message, AsyncMock(), container, MagicMock())

    assert len(scheduler.get_jobs()) == 2
    assert_schedule(scheduler.get_job("reminder:1"), 1, reminder_time, tz)
    user = await container.users_repo.get(1)
    assert (user["reminder_time"], user["tz"]) == (reminder_time, tz)
    assert scheduler.get_job("reminder:2") is other_job
    assert other_job.next_run_time == other_next_run
    assert await container.users_repo.get(2) == other_user
    assert_schedule(other_job, 2, "12:34", "Europe/Berlin")
    container.reminder.send_reminder.assert_not_called()


async def test_startup_restores_existing_users_without_changing_data(
    container, scheduler, session_factory, caplog
):
    await onboard(container, "zero", user_id=1)
    await onboard(container, "skip", user_id=2)
    await container.users_repo.update(1, reminder_time="09:23", tz="Asia/Tokyo")
    await container.users_repo.update(2, reminder_time="22:46", tz="Europe/Berlin")
    saved_users = await container.users_repo.all()
    # A new container/scheduler represents the in-memory schedule after restart.
    scheduler.remove_all_jobs()
    restarted = build_container(
        session_factory, scheduler=scheduler, send_reminder=AsyncMock()
    )

    with caplog.at_level("INFO", logger="bot.services.reminder_service"):
        await restarted.reminder.reschedule_all()
        await restarted.reminder.reschedule_all()

    assert len(scheduler.get_jobs()) == 2
    assert_schedule(scheduler.get_job("reminder:1"), 1, "09:23", "Asia/Tokyo")
    assert_schedule(scheduler.get_job("reminder:2"), 2, "22:46", "Europe/Berlin")
    assert await restarted.users_repo.all() == saved_users
    assert "reminders_scheduled count=2" in caplog.text
    restarted.reminder.send_reminder.assert_not_called()
