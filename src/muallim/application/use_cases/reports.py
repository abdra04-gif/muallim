"""«Бот ошибся»: ученик оспаривает проверку (FR-23, ADR-0020)."""

from dataclasses import dataclass
from uuid import UUID

from muallim.application.ports.repositories import AttemptRepository, UnitOfWork
from muallim.application.ports.system import Clock, EventLog
from muallim.domain.learner import Learner
from muallim.domain.report import LearnerReport, ReportReason


@dataclass(frozen=True, slots=True)
class ReportMistake:
    attempts: AttemptRepository
    uow: UnitOfWork
    clock: Clock
    events: EventLog

    async def execute(self, learner: Learner, attempt_id: UUID, reason: ReportReason) -> bool:
        """False — попытка чужая или не существует (кнопку могли подделать)."""
        if await self.attempts.owner(attempt_id) != learner.id:
            return False
        added = await self.attempts.add_report(
            LearnerReport(attempt_id, learner.id, reason, self.clock.now())
        )
        if not added:
            return True  # второе нажатие: жалоба уже принята, считать её дважды нельзя
        await self.events.record(
            "attempt_disputed", learner.id, {"attempt_id": str(attempt_id), "reason": reason}
        )
        await self.uow.commit()
        return True
