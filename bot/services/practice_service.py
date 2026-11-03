"""Credit unmastered English vocabulary used by registered users in groups."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.domain.chat_practice import PracticeLexicon, authored_text
from bot.repositories.practice_repo import PracticeRepo
from bot.repositories.users_repo import UsersRepo

logger = logging.getLogger(__name__)
FORMS_CSV = Path(__file__).resolve().parents[2] / 'data/dictionary_forms.csv'


class PracticeService:
    def __init__(self, repository: PracticeRepo, users: UsersRepo) -> None:
        self.repository = repository
        self.users = users
        self.lexicon: PracticeLexicon | None = None
        self._load_lock = asyncio.Lock()

    async def prepare(self) -> None:
        async with self._load_lock:
            if self.lexicon is None:
                words = await self.repository.vocabulary()
                self.lexicon = await asyncio.to_thread(PracticeLexicon.from_csv, words, FORMS_CSV)
                logger.info('chat_practice_ready words=%s forms=%s', len(words), len(self.lexicon.forms))

    async def observe(self, message, *, now: datetime | None = None) -> list[str]:
        sender = message.from_user
        if (message.chat.type not in {'group', 'supergroup'}
                or not sender or sender.is_bot or message.sender_chat or message.forward_origin
                or message.is_automatic_forward or message.via_bot or message.edit_date):
            return []
        text = message.text or message.caption or ''
        if not text or text.lstrip().startswith('/'):
            return []
        text = authored_text(text, (message.entities if message.text else message.caption_entities) or ())
        if not any('a' <= c.lower() <= 'z' for c in text):
            return []
        user = await self.users.get(sender.id)
        if user is None:
            return []
        await self.prepare()
        words = self.lexicon.extract(text)
        now = now or datetime.now(timezone.utc)
        used_at = message.date
        day = used_at.astimezone(ZoneInfo(user['tz'])).date().isoformat()
        added, praise = await self.repository.record(sender.id, [w['id'] for w in words],
            message.chat.id, message.message_id, day, used_at, now)
        if not praise:
            return []
        added_set = set(added)
        return [word['english'] for word in words if word['id'] in added_set]

    async def stats(self, user_id: int, zone: str, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        since = now.astimezone(ZoneInfo(zone)).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.repository.stats(user_id, since.astimezone(timezone.utc), now)
