"""Снимок учебной программы в БД при старте бота (ADR-0023)."""

from dataclasses import dataclass

from muallim.application.ports.repositories import CurriculumSnapshots, UnitOfWork
from muallim.domain.curriculum import Curriculum


@dataclass(frozen=True, slots=True)
class PublishCurriculum:
    curriculum: Curriculum
    snapshots: CurriculumSnapshots
    uow: UnitOfWork

    async def execute(self) -> int:
        added = await self.snapshots.publish(self.curriculum)
        await self.uow.commit()
        return added
