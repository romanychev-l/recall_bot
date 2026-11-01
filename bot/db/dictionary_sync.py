"""Update dictionary ranks by word identity, preserving learning history."""
from __future__ import annotations

from sqlalchemy import func, insert, select, update

from bot.db.models import User, UserCard, Word


def validate_rows(rows: list[dict]) -> None:
    for key in ("english", "frequency_rank"):
        values = [row[key] for row in rows]
        if len(set(values)) != len(values):
            raise ValueError(f"Duplicate dictionary {key}; refusing an ambiguous update")
    if any(row["frequency_rank"] < 1 for row in rows):
        raise ValueError("Dictionary ranks must be positive")


async def apply_dictionary(session, entries: list[dict], *, update_content: bool) -> tuple[int, int]:
    """Validate the whole plan before writes; caller commits the transaction.

    A rank is a mutable priority, never an identity. Move changing ranks through
    a temporary range to support permutations under the unique rank constraint.
    Startup updates only ranks of matching words, preserving custom vocabulary.
    """
    validate_rows(entries)
    existing = (await session.execute(select(Word.__table__))).mappings().all()
    by_english = {row["english"]: row for row in existing}
    if len(by_english) != len(existing):
        raise ValueError("Duplicate English words in database; refusing an ambiguous update")
    incoming = {row["english"]: row for row in entries}
    targets = {word: row for word, row in incoming.items() if update_content or word in by_english}
    untouched_ranks = {row["frequency_rank"] for row in existing if row["english"] not in targets}
    if any(row["frequency_rank"] in untouched_ranks for row in targets.values()):
        raise ValueError("Dictionary ranks collide with vocabulary outside this CSV")
    changed = [row for word, row in targets.items()
               if word in by_english and row["frequency_rank"] != by_english[word]["frequency_rank"]]
    temporary = min([0] + [row["frequency_rank"] for row in existing]) - len(changed) - 1
    changed_words = {row["english"] for row in changed}
    if changed:
        await session.execute(update(Word), [
            {"id": by_english[row["english"]]["id"], "frequency_rank": temporary + offset}
            for offset, row in enumerate(changed)
        ])
    updates = [
        {"id": by_english[word]["id"], **(row if update_content else {"frequency_rank": row["frequency_rank"]})}
        for word, row in targets.items()
        if word in by_english and (update_content or word in changed_words)
    ]
    additions = [row for word, row in targets.items() if word not in by_english]
    if updates:
        await session.execute(update(Word), updates)
    if additions:
        await session.execute(insert(Word), additions)
    if changed:
        rank = select(Word.frequency_rank).where(Word.id == UserCard.word_id).scalar_subquery()
        await session.execute(update(UserCard).where(UserCard.frequency_rank != rank)
                              .values(frequency_rank=rank))
        # The old high-water mark belongs to the old ordering. Recompute it from
        # actual word ownership; never reset FSRS, reviews, skips or batch IDs.
        owned = select(1).where(UserCard.user_id == User.id, UserCard.word_id == Word.id).correlate(User, Word).exists()
        next_rank = select(func.min(Word.frequency_rank)).where(
            Word.frequency_rank >= User.initial_rank, ~owned
        ).correlate(User).scalar_subquery()
        end = (await session.scalar(select(func.max(Word.frequency_rank)))) + 1
        await session.execute(update(User).values(next_batch_start_rank=func.coalesce(next_rank, end)))
    return len(additions), len(updates)
