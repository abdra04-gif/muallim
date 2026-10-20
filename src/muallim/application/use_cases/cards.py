"""Навигация по карточкам учебника."""

from dataclasses import dataclass

from muallim.application.ports.repositories import LearnerRepository, UnitOfWork
from muallim.application.ports.system import EventLog
from muallim.domain.curriculum import Curriculum, LessonItem
from muallim.domain.learner import Learner


@dataclass(frozen=True, slots=True)
class OpenItem:
    curriculum: Curriculum
    learners: LearnerRepository
    uow: UnitOfWork
    events: EventLog

    async def execute(self, learner: Learner, item_id: str, *, move: bool = True) -> LessonItem:
        """Открыть карточку. ``move=False`` — «Продолжить» не сдвигается (начало занятия, FR-49)."""
        item = self.curriculum.item(item_id)  # KeyError — устаревшая кнопка, ловит presentation
        if move:
            learner.current_item_id = item.id
            await self.learners.save(learner)
        await self.events.record("item_opened", learner.id, {"item_id": item.id})
        await self.uow.commit()
        return item

    def current(self, learner: Learner) -> LessonItem:
        """Текущая карточка; если её убрали из программы — первая карточка."""
        if learner.current_item_id is not None:
            try:
                return self.curriculum.item(learner.current_item_id)
            except KeyError:
                pass
        return self.curriculum.first_item()
