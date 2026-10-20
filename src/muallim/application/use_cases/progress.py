"""Прогресс ученика: уроки (пройден / начат / новый), серия дней подряд, «продолжить с места»."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from muallim.application.ports.repositories import AttemptRepository
from muallim.application.ports.system import Clock
from muallim.domain.curriculum import Curriculum, Lesson, LessonItem
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy


class LessonStatus(StrEnum):
    NEW = "new"
    STARTED = "started"
    DONE = "done"  # все строки урока засчитаны


@dataclass(frozen=True, slots=True)
class LessonProgress:
    lesson: Lesson
    mastered: int
    weak: tuple[LessonItem, ...]  # пробовал, но ещё не засчитано

    @property
    def total(self) -> int:
        """Сколько строк урока проверяется чтением (таблица алфавита — не считается)."""
        return len(self.lesson.practice_items)

    @property
    def percent(self) -> int:
        return round(100 * self.mastered / self.total) if self.total else 0

    @property
    def status(self) -> LessonStatus:
        if self.total and self.mastered >= self.total:
            return LessonStatus.DONE
        return LessonStatus.STARTED if self.mastered or self.weak else LessonStatus.NEW


@dataclass(frozen=True, slots=True)
class Progress:
    lessons: tuple[LessonProgress, ...]
    attempts_total: int
    streak_days: int = 0  # сколько дней подряд занимается (сегодня или вчера — серия жива)
    today_attempts: int = 0
    continue_item: LessonItem | None = None  # где остановился
    today: date | None = None  # «сегодня» по часам бота — для начала занятия (ADR-0050)
    week: tuple[bool, ...] = ()  # 7 дней, последний — сегодня: была ли хоть одна попытка

    def of(self, lesson_id: str) -> LessonProgress:
        return next(lp for lp in self.lessons if lp.lesson.id == lesson_id)

    @property
    def done_lessons(self) -> int:
        return sum(1 for lp in self.lessons if lp.status is LessonStatus.DONE)

    @property
    def practice_lessons(self) -> int:
        return sum(1 for lp in self.lessons if lp.total)


@dataclass(frozen=True, slots=True)
class GetProgress:
    curriculum: Curriculum
    attempts: AttemptRepository
    policy: GradingPolicy
    clock: Clock

    async def execute(self, learner: Learner) -> Progress:
        best = await self.attempts.best_scores(learner.id)
        lessons: list[LessonProgress] = []
        for lesson in self.curriculum.lessons:
            items = lesson.practice_items
            tried = [(item, best[item.id]) for item in items if item.id in best]
            mastered = sum(1 for _, score in tried if self.policy.is_mastered(score))
            weak = tuple(item for item, score in tried if not self.policy.is_mastered(score))
            lessons.append(LessonProgress(lesson, mastered, weak))
        days = await self.attempts.activity(learner.id)
        today = self.clock.now().date()
        return Progress(
            lessons=tuple(lessons),
            attempts_total=await self.attempts.count(learner.id),
            streak_days=_streak(set(days), today),
            today_attempts=days.get(today, 0),
            continue_item=self._continue(learner, best, lessons),
            today=today,
            week=tuple(days.get(today - timedelta(days=k), 0) > 0 for k in range(6, -1, -1)),
        )

    def _continue(
        self, learner: Learner, best: Mapping[str, int], lessons: Sequence[LessonProgress]
    ) -> LessonItem:
        """Где остановился; с последнего шага урока — в следующий урок (FR-49, FR-50).

        Последний шаг «пройден», если урок засчитан, по шагу есть попытка (даже неудачная —
        строка остаётся в «повторить») или читать на нём нечего. Последний урок — остаёмся.
        """
        if learner.current_item_id is None:
            return self.curriculum.first_item()
        try:
            item = self.curriculum.item(learner.current_item_id)
        except KeyError:
            return self.curriculum.first_item()
        lesson, i = self.curriculum.locate(item.id)
        if i != len(lesson.items) - 1:
            return item
        done = next(lp for lp in lessons if lp.lesson.id == lesson.id).status is LessonStatus.DONE
        following = self.curriculum.next_lesson(lesson.id)
        if following is not None and (done or item.id in best or not item.is_practice):
            return following.items[0]
        return item


def _streak(days: set[date], today: date) -> int:
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak
