from __future__ import annotations

from dataclasses import dataclass

from bot.domain.srs import SrsService
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
    review_log_repo: ReviewLogRepo
    srs: SrsService
    onboarding: OnboardingService
    batch: BatchService
    learning: LearningService
    stats: StatsService
    reminder: ReminderService


def build_container(
    db,
    *,
    scheduler,
    send_reminder,
) -> Container:
    users_repo = UsersRepo(db)
    words_repo = WordsRepo(db)
    cards_repo = CardsRepo(db)
    review_log_repo = ReviewLogRepo(db)
    srs = SrsService()
    batch = BatchService(users_repo, words_repo, cards_repo, srs)
    onboarding = OnboardingService(users_repo, batch)
    learning = LearningService(
        users_repo, words_repo, cards_repo, review_log_repo, srs, batch
    )
    stats = StatsService(users_repo, cards_repo, review_log_repo)
    reminder = ReminderService(scheduler, users_repo, send_reminder)
    return Container(
        users_repo=users_repo,
        words_repo=words_repo,
        cards_repo=cards_repo,
        review_log_repo=review_log_repo,
        srs=srs,
        onboarding=onboarding,
        batch=batch,
        learning=learning,
        stats=stats,
        reminder=reminder,
    )
