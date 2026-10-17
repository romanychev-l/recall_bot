from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.domain.srs import SrsService
from bot.repositories.batches_repo import BatchesRepo
from bot.repositories.cards_repo import CardsRepo
from bot.repositories.review_log_repo import ReviewLogRepo
from bot.repositories.users_repo import UsersRepo
from bot.repositories.words_repo import WordsRepo
from bot.services.batch_service import BatchService
from bot.services.learning_service import LearningService
from bot.services.onboarding_service import OnboardingService
from bot.services.reminder_service import ReminderService
from bot.services.stats_service import StatsService


@dataclass
class Container:
    users_repo: UsersRepo
    words_repo: WordsRepo
    cards_repo: CardsRepo
    batches_repo: BatchesRepo
    review_log_repo: ReviewLogRepo
    srs: SrsService
    onboarding: OnboardingService
    batch: BatchService
    learning: LearningService
    stats: StatsService
    reminder: ReminderService


def build_container(
    session_factory: async_sessionmaker,
    *,
    scheduler,
    send_reminder,
) -> Container:
    users_repo = UsersRepo(session_factory)
    words_repo = WordsRepo(session_factory)
    cards_repo = CardsRepo(session_factory)
    batches_repo = BatchesRepo(session_factory)
    review_log_repo = ReviewLogRepo(session_factory)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, batches_repo, srs)
    reminder = ReminderService(scheduler, users_repo, send_reminder)
    onboarding = OnboardingService(users_repo, batch, reminder)
    learning = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )
    stats = StatsService(users_repo, cards_repo, review_log_repo)
    return Container(
        users_repo=users_repo,
        words_repo=words_repo,
        cards_repo=cards_repo,
        batches_repo=batches_repo,
        review_log_repo=review_log_repo,
        srs=srs,
        onboarding=onboarding,
        batch=batch,
        learning=learning,
        stats=stats,
        reminder=reminder,
    )
