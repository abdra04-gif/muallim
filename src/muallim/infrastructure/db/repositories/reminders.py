"""Кому может прийти напоминание — на SQL (ADR-0061 п. 4)."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import ReminderRecipients
from muallim.domain.learner import Learner
from muallim.infrastructure.db.repositories.learners import _FIELDS
from muallim.infrastructure.db.tables import learner_settings, learners


@dataclass(frozen=True, slots=True)
class SqlReminderRecipients(ReminderRecipients):
    session: AsyncSession

    async def candidates(self) -> list[UUID]:
        query = (
            select(learner_settings.c.learner_id)
            .join(learners, learners.c.id == learner_settings.c.learner_id)
            .where(
                learner_settings.c.reminder_minute.is_not(None), learners.c.blocked_bot.is_(False)
            )
            .order_by(learner_settings.c.learner_id)
        )
        return list((await self.session.scalars(query)).all())

    async def learner(self, learner_id: UUID) -> Learner | None:
        query = select(learners).where(learners.c.id == learner_id)
        row = (await self.session.execute(query)).mappings().first()
        return Learner(**{name: row[name] for name in _FIELDS}) if row else None
