from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.system import Clock, EventLog
from muallim.infrastructure.db.tables import interaction_events


@dataclass(frozen=True, slots=True)
class SqlEventLog(EventLog):
    session: AsyncSession
    clock: Clock

    async def record(
        self, event: str, learner_id: UUID | None, payload: dict[str, str | int | None]
    ) -> None:
        await self.session.execute(
            insert(interaction_events).values(
                learner_id=learner_id, event=event, payload=payload, created_at=self.clock.now()
            )
        )
