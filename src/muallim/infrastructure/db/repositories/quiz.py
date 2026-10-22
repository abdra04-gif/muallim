"""Ответы «🧠 Закрепления» на SQL (ADR-0066): таблица ``quiz_answers``."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import QuizAnswerRepository
from muallim.domain.quiz import QuizAnswer
from muallim.infrastructure.db.tables import quiz_answers

_FIELDS = tuple(QuizAnswer.__dataclass_fields__)


@dataclass(frozen=True, slots=True)
class SqlQuizAnswerRepository(QuizAnswerRepository):
    session: AsyncSession

    async def add(self, row: QuizAnswer) -> bool:
        values: dict[str, Any] = {name: getattr(row, name) for name in _FIELDS}
        values["options"] = list(row.options)
        try:
            async with self.session.begin_nested():  # UNIQUE (ученик, раунд, место)
                await self.session.execute(insert(quiz_answers).values(values))
        except IntegrityError:
            return False
        return True

    async def get(self, answer_id: UUID) -> QuizAnswer | None:
        query = select(quiz_answers).where(quiz_answers.c.id == answer_id)
        row = (await self.session.execute(query)).mappings().first()
        return None if row is None else _from_row(row)

    async def record(
        self,
        answer_id: UUID,
        *,
        picked: int | None,
        correct: bool | None,
        answered_at: datetime,
        attempt_id: UUID | None = None,
    ) -> bool:
        result = await self.session.execute(
            update(quiz_answers)
            .where(quiz_answers.c.id == answer_id, quiz_answers.c.answered_at.is_(None))
            .values(picked=picked, correct=correct, answered_at=answered_at, attempt_id=attempt_id)
        )
        return bool(getattr(result, "rowcount", 0))

    async def history(self, learner_id: UUID) -> list[QuizAnswer]:
        query = (
            select(quiz_answers)
            .where(quiz_answers.c.learner_id == learner_id)
            .order_by(quiz_answers.c.round_no, quiz_answers.c.position, quiz_answers.c.shown_at)
        )
        return [_from_row(r) for r in (await self.session.execute(query)).mappings()]


def _from_row(row: RowMapping) -> QuizAnswer:
    values: dict[str, Any] = {name: row[name] for name in _FIELDS}
    values["options"] = tuple(row["options"])
    return QuizAnswer(**values)
