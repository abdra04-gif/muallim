"""«🔁 Повторение» на сегодня (FR-52 (б), ADR-0062 вариант A): строки к сроку по 1·3·7 дней и
строки пройденных уроков с буквами, в которых ученик чаще всего ошибается. Всё — из попыток."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from muallim.application.ports.repositories import AttemptRepository, LearnerSettingsRepository
from muallim.application.ports.system import Clock
from muallim.domain import review
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.domain.settings import DEFAULT_UTC_OFFSET_MIN, local_date


@dataclass(frozen=True, slots=True)
class GetReview:
    curriculum: Curriculum
    attempts: AttemptRepository
    policy: GradingPolicy
    clock: Clock
    settings: LearnerSettingsRepository | None = None  # нет — «сегодня» по UTC+3

    async def execute(self, learner: Learner) -> tuple[review.ReviewEntry, ...]:
        best = await self.attempts.best_scores(learner.id)
        passed = [
            lesson.id
            for lesson in self.curriculum.lessons
            if lesson.practice_items
            and all(
                item.id in best and self.policy.is_mastered(best[item.id])
                for item in lesson.practice_items
            )
        ]  # уроки, пройденные целиком (LessonStatus.DONE)
        return await self.for_day(learner, await self.today(learner), passed)

    async def for_day(
        self, learner: Learner, today: date, passed_lessons: Collection[str]
    ) -> tuple[review.ReviewEntry, ...]:
        """Отбор на день, когда пройденные уроки уже известны (``GetProgress``)."""
        states = review.schedule(await self.attempts.outcomes(learner.id))
        errors = await self.attempts.recent_errors(learner.id, review.RECENT_ATTEMPTS_FOR_LETTERS)
        return review.due_today(
            states,
            today,
            self.curriculum,
            passed_lessons=passed_lessons,
            letter_errors=review.error_letters(errors),
        )

    async def today(self, learner: Learner) -> date:
        """Местная дата ученика (ADR-0061); без настроек — UTC+3, как дни попыток в БД."""
        now = self.clock.now()
        if self.settings is None:
            return local_date(now, DEFAULT_UTC_OFFSET_MIN)
        return local_date(now, (await self.settings.get(learner.id)).utc_offset_min)
