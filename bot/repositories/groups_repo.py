from __future__ import annotations

from datetime import datetime

from sqlalchemy import distinct, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from bot.constants import RESULT_GOOD, STATE_GRADUATED, STATE_REVIEW
from bot.db.models import GroupChat, GroupMember, ReviewLog, UserCard
from bot.repositories.base import BaseRepo, one, rows


class GroupsRepo(BaseRepo):
    async def get(self, chat_id: int) -> dict | None:
        async with self._sf() as session:
            return one(await session.execute(select(GroupChat.__table__).where(GroupChat.id == chat_id)))

    async def create(self, group: dict) -> bool:
        try:
            async with self._sf() as session:
                await session.execute(insert(GroupChat).values(**group))
                await session.commit()
            return True
        except IntegrityError:
            if await self.get(group["id"]) is None:
                raise
            return False

    async def update(self, chat_id: int, **fields) -> None:
        async with self._sf() as session:
            await session.execute(update(GroupChat).where(GroupChat.id == chat_id).values(**fields))
            await session.commit()

    async def join(self, chat_id: int, user_id: int, name: str, now: datetime) -> bool:
        async with self._sf() as session:
            member = await session.get(GroupMember, (chat_id, user_id))
            if member:
                joined = not member.active
                member.active = True
                member.display_name = name
            else:
                joined = True
                session.add(GroupMember(chat_id=chat_id, user_id=user_id,
                                        display_name=name, active=True, joined_at=now))
            await session.commit()
            return joined

    async def leave(self, chat_id: int, user_id: int) -> bool:
        async with self._sf() as session:
            result = await session.execute(update(GroupMember).where(
                GroupMember.chat_id == chat_id, GroupMember.user_id == user_id,
                GroupMember.active.is_(True),
            ).values(active=False))
            await session.commit()
            return result.rowcount > 0

    async def due(self, now: datetime) -> list[dict]:
        async with self._sf() as session:
            return rows(await session.execute(select(GroupChat.__table__).where(
                GroupChat.enabled.is_(True), GroupChat.bot_present.is_(True),
                GroupChat.next_report_at <= now,
            )))

    async def standings(self, chat_id: int, since: datetime, now: datetime) -> list[dict]:
        members = select(GroupMember.user_id).where(
            GroupMember.chat_id == chat_id, GroupMember.active.is_(True),
        )
        learned = select(UserCard.user_id, func.count().label("learned")).where(
            UserCard.user_id.in_(members),
            UserCard.my_state.in_([STATE_REVIEW, STATE_GRADUATED]),
        ).group_by(UserCard.user_id).subquery()
        today = select(ReviewLog.user_id, func.count(distinct(ReviewLog.word_id)).label("today")).where(
            ReviewLog.user_id.in_(members), ReviewLog.result == RESULT_GOOD,
            ReviewLog.reviewed_at >= since, ReviewLog.reviewed_at <= now,
        ).group_by(ReviewLog.user_id).subquery()
        total = func.coalesce(learned.c.learned, 0)
        daily = func.coalesce(today.c.today, 0)
        async with self._sf() as session:
            return rows(await session.execute(select(
                GroupMember.user_id, GroupMember.display_name,
                total.label("learned"), daily.label("today"),
            ).outerjoin(learned, learned.c.user_id == GroupMember.user_id)
             .outerjoin(today, today.c.user_id == GroupMember.user_id)
             .where(GroupMember.chat_id == chat_id, GroupMember.active.is_(True))
             .order_by(total.desc(), daily.desc(), GroupMember.display_name, GroupMember.user_id)))

    async def migrate(self, old_id: int, new_id: int) -> None:
        # ON UPDATE CASCADE moves memberships in the same transaction.
        await self.update(old_id, id=new_id, message_id=None, thread_id=None)
