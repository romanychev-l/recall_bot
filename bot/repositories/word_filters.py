"""One meaning predicate for allocation, counts and existing card queues."""
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from bot.db.models import Word, WordSense
from bot.domain.parts_of_speech import POS_ALIASES, POS_BITS


def matches_parts(mask: int | ColumnElement[int]) -> ColumnElement[bool]:
    senses = select(1).where(WordSense.word_id == Word.id).correlate_except(WordSense)
    labels = {**POS_BITS, **{alias: POS_BITS[pos] for alias, pos in POS_ALIASES.items()}}
    fallback = case(labels, value=func.lower(func.trim(Word.pos)), else_=POS_BITS["other"])
    return or_(
        senses.where(WordSense.pos_mask.bitwise_and(mask) != 0).exists(),
        and_(~senses.exists(), fallback.bitwise_and(mask) != 0),
    )
