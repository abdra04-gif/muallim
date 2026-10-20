"""Закрепление букв: вопросы только по начатым буквам; ответы — в журнал событий (ADR-0025)."""

from dataclasses import dataclass

from muallim.application.ports.repositories import AttemptRepository, UnitOfWork
from muallim.application.ports.system import EventLog
from muallim.domain.curriculum import Curriculum, Lesson
from muallim.domain.learner import Learner
from muallim.domain.quiz import (
    Question,
    QuizError,
    make_question,
    question_from,
    started_lessons,
)


@dataclass(frozen=True, slots=True)
class PracticeQuiz:
    curriculum: Curriculum
    attempts: AttemptRepository
    events: EventLog
    uow: UnitOfWork

    async def next(self, learner: Learner, seed: int) -> Question | None:
        """Вопрос по буквам, которые ученик уже читал (или открыл); None — рано."""
        lessons = await self._started(learner)
        try:
            return make_question(self.curriculum, lessons, seed)
        except QuizError:
            return None

    async def answer(
        self,
        learner: Learner,
        item_id: str,
        vowel: int,
        seed: int,
        picked: int,
        *,
        started: int = -1,
    ) -> Question:
        """``started`` — маска начатых уроков на момент вопроса (из кнопки); -1 — как сейчас."""
        lessons = (
            started_lessons(self.curriculum, started)
            if started >= 0
            else await self._started(learner)
        )
        if vowel not in range(3):  # подделанная кнопка: в данные исследования не пишем
            raise IndexError(vowel)
        q = question_from(self.curriculum, item_id, vowel, seed, lessons)
        if picked not in range(len(q.options)):
            raise IndexError(picked)
        await self.events.record(
            "quiz_answered",
            learner.id,
            {"item_id": item_id, "vowel": vowel, "correct": picked == q.answer},
        )
        await self.uow.commit()
        return q

    async def _started(self, learner: Learner) -> list[Lesson]:
        """Уроки букв, которые ученик читал (или открыл): из них вопрос и отвлекающие варианты."""
        tried = set(await self.attempts.best_scores(learner.id))
        return [
            les
            for les in self.curriculum.lessons
            if les.section == "letter"
            and any(i.id in tried or i.id == learner.current_item_id for i in les.items)
        ]
