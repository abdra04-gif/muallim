"""Закрепление букв: вопросы только по начатым буквам; ответы — в журнал событий (ADR-0025)."""

from dataclasses import dataclass

from muallim.application.ports.repositories import AttemptRepository, UnitOfWork
from muallim.application.ports.system import EventLog
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.quiz import Question, QuizError, make_question, question_from


@dataclass(frozen=True, slots=True)
class PracticeQuiz:
    curriculum: Curriculum
    attempts: AttemptRepository
    events: EventLog
    uow: UnitOfWork

    async def next(self, learner: Learner, seed: int) -> Question | None:
        """Вопрос по буквам, которые ученик уже читал (или открыл); None — рано."""
        tried = set(await self.attempts.best_scores(learner.id))
        lessons = [
            les
            for les in self.curriculum.lessons
            if les.section == "letter"
            and any(i.id in tried or i.id == learner.current_item_id for i in les.items)
        ]
        try:
            return make_question(self.curriculum, lessons, seed)
        except QuizError:
            return None

    async def answer(
        self, learner: Learner, item_id: str, vowel: int, seed: int, picked: int
    ) -> Question:
        q = question_from(self.curriculum, item_id, vowel, seed)
        await self.events.record(
            "quiz_answered",
            learner.id,
            {"item_id": item_id, "vowel": vowel, "correct": picked == q.answer},
        )
        await self.uow.commit()
        return q
