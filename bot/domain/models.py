from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from bot.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DAILY_GOAL,
    DEFAULT_REMINDER_TIME,
    DEFAULT_TZ,
    STATE_NEW,
)


class _Model(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)


class User(_Model):
    telegram_id: int = Field(alias="_id")
    batch_size: int = DEFAULT_BATCH_SIZE
    daily_goal: int = DEFAULT_DAILY_GOAL
    reminder_time: str = DEFAULT_REMINDER_TIME
    tz: str = DEFAULT_TZ
    language: str = "ru"
    initial_rank: int = 0
    current_batch_id: Optional[ObjectId] = None
    next_batch_start_rank: int = 0
    streak_days: int = 0
    last_session_date: Optional[datetime] = None
    created_at: datetime


class Word(_Model):
    id: ObjectId = Field(alias="_id")
    english: str
    translation: str
    frequency_rank: int
    pos: str = ""
    example: str = ""
    is_phrasal: bool = False


class UserCard(_Model):
    id: ObjectId = Field(alias="_id", default_factory=ObjectId)
    user_id: int
    word_id: ObjectId
    batch_id: ObjectId
    frequency_rank: int
    fsrs: dict[str, Any]
    my_state: str = STATE_NEW
    consecutive_successes_at_review: int = 0
    first_reached_review_at: Optional[datetime] = None
    is_hard: bool = False
    skip_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ReviewLogEntry(_Model):
    id: ObjectId = Field(alias="_id", default_factory=ObjectId)
    user_id: int
    word_id: ObjectId
    batch_id: ObjectId
    result: str
    user_input: str
    reviewed_at: datetime
