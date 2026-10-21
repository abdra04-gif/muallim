"""Напоминание о занятии: кому пора и что записать (FR-51, ADR-0061 п. 4, В2–В4).

Правило «пора ли» — ``domain.settings.reminder_due``. Дата напоминания ставится и коммитится по
одному ученику **до** отправки: не больше одного напоминания в местный день даже при сбое
(если Telegram отказал — сегодня без напоминания). Отправляет presentation.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerRepository,
    LearnerSettingsRepository,
    ReminderRecipients,
    UnitOfWork,
)
from muallim.application.ports.system import EventLog
from muallim.domain.learner import Learner
from muallim.domain.settings import local_date, reminder_due


@dataclass(frozen=True, slots=True)
class DueReminders:
    recipients: ReminderRecipients
    settings: LearnerSettingsRepository
    learners: LearnerRepository
    attempts: AttemptRepository
    uow: UnitOfWork
    events: EventLog

    async def _due(self, learner_id: UUID, now: datetime) -> bool:
        current = await self.settings.get(learner_id)
        days = await self.attempts.activity(learner_id)  # местные дни ученика
        return reminder_due(now, current, max(days, default=None))

    async def due(self, now: datetime) -> list[UUID]:
        """Кому пора напомнить в момент ``now``."""
        return [i for i in await self.recipients.candidates() if await self._due(i, now)]

    async def claim(self, learner_id: UUID, now: datetime) -> Learner | None:
        """Отметить «сегодня напомнили» и закоммитить; None — уже не пора (другой тик успел)."""
        learner = await self.recipients.learner(learner_id)
        if learner is None or learner.blocked_bot or not await self._due(learner_id, now):
            return None
        offset = (await self.settings.get(learner_id)).utc_offset_min
        if not await self.settings.claim_reminder(learner_id, local_date(now, offset)):
            return None  # снимок устарел: дату уже поставил другой тик или процесс
        await self.uow.commit()
        return learner

    async def delivered(self, learner: Learner) -> None:
        await self.events.record("reminder_sent", learner.id, {})
        await self.uow.commit()

    async def blocked(self, learner: Learner) -> None:
        """Ученик заблокировал бота: больше не пишем, пока он сам не напишет (ADR-0061 п. 4)."""
        learner.blocked_bot = True
        await self.learners.save(learner)
        await self.uow.commit()
