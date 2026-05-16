from __future__ import annotations

USERS_COLLECTION = "users"
WORDS_COLLECTION = "words"
USER_CARDS_COLLECTION = "user_cards"
REVIEW_LOG_COLLECTION = "review_log"

DEFAULT_BATCH_SIZE = 10
DEFAULT_DAILY_GOAL = 10
DEFAULT_REMINDER_TIME = "19:00"
DEFAULT_TZ = "Europe/Moscow"

GRADUATION_MIN_INTERVAL_DAYS = 30
GRADUATION_MIN_CONSECUTIVE = 5

LADDER_DAYS = (1, 3, 7, 14, 30, 90, 180)

STATE_NEW = "new"
STATE_LEARNING = "learning"
STATE_REVIEW = "review"
STATE_GRADUATED = "graduated"

RESULT_GOOD = "good"
RESULT_AGAIN = "again"

CEFR_BANDS: tuple[tuple[str, int, int], ...] = (
    ("A1", 1, 500),
    ("A2", 501, 1500),
    ("B1", 1501, 3000),
    ("B2", 3001, 6000),
    ("C1", 6001, 10000),
    ("C2", 10001, 20000),
)
