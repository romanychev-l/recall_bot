from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.dialects.sqlite import insert

from bot.db.models import ChatPractice, ChatPracticePraise, User, UserCard, Word, WordSense
from bot.domain.chat_practice import CONTENT_POS
from bot.domain.parts_of_speech import POS_BITS
from bot.repositories.base import BaseRepo, rows

PRAISE_COOLDOWN = timedelta(minutes=15)


class PracticeRepo(BaseRepo):
    async def vocabulary(self) -> list[dict]:
        content = sum(POS_BITS[pos] for pos in ('noun', 'verb', 'adj', 'adv'))
        named = select(1).where(WordSense.word_id == Word.id, WordSense.pos_mask.op('&')(POS_BITS['name']) != 0).exists()
        meaningful = select(1).where(WordSense.word_id == Word.id, WordSense.pos_mask.op('&')(content) != 0).exists()
        async with self._sf() as session:
            return rows(await session.execute(select(Word.id, Word.english, Word.pos, Word.frequency_rank).where(
                Word.pos.in_(CONTENT_POS), ~(named & ~meaningful),
            )))

    async def record(self, user_id: int, word_ids: list[int], chat_id: int, message_id: int,
                     practice_day: str, used_at: datetime, now: datetime) -> tuple[list[int], bool]:
        """Eligibility, daily deduplication and praise reservation commit together.

        SQLite's conflict handling keeps retries and concurrent chat deliveries
        from granting the same credit twice. No cards or reviews are written.
        """
        if not word_ids:
            return [], False
        async with self._sf() as session:
            pending = rows(await session.execute(select(Word.id, UserCard.my_state).select_from(Word).join(
                User, User.id == user_id,
            ).outerjoin(UserCard, and_(UserCard.word_id == Word.id, UserCard.user_id == user_id)).where(
                Word.id.in_(word_ids),
                or_(UserCard.my_state.in_(['new', 'learning']),
                    and_(UserCard.id.is_(None), Word.frequency_rank >= User.initial_rank)),
            )))
            if not pending:
                return [], False
            added = []
            # Keep every word in a long message, including on SQLite builds
            # with the older 999-parameter limit.
            for start in range(0, len(pending), 100):
                added.extend((await session.scalars(insert(ChatPractice).values([
                    dict(user_id=user_id, word_id=row['id'], practice_day=practice_day,
                         chat_id=chat_id, message_id=message_id, used_at=used_at,
                         study_state=row['my_state'] or 'unseen') for row in pending[start:start + 100]
                ]).on_conflict_do_nothing().returning(ChatPractice.word_id))).all())
            praise = False
            if added:
                result = await session.scalar(insert(ChatPracticePraise).values(
                    user_id=user_id, chat_id=chat_id, last_praised_at=now,
                ).on_conflict_do_update(
                    index_elements=['user_id', 'chat_id'], set_={'last_praised_at': now},
                    where=ChatPracticePraise.last_praised_at <= now - PRAISE_COOLDOWN,
                ).returning(ChatPracticePraise.user_id))
                praise = result is not None
            await session.commit()
            return added, praise

    async def stats(self, user_id: int, since: datetime, now: datetime) -> dict:
        async with self._sf() as session:
            total = await session.scalar(select(func.count(distinct(ChatPractice.word_id))).where(
                ChatPractice.user_id == user_id, ChatPractice.used_at <= now))
            today = await session.scalar(select(func.count(distinct(ChatPractice.word_id))).where(
                ChatPractice.user_id == user_id, ChatPractice.used_at >= since, ChatPractice.used_at <= now))
            return {'today': today, 'total': total}
