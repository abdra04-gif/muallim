"""Настройки ученика и состояние экрана на SQL (ADR-0061): одна строка ``learner_settings``."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import LearnerSettingsRepository
from muallim.application.ports.system import Clock
from muallim.domain.settings import HowToRead, LearnerSettings
from muallim.infrastructure.db.tables import learner_settings

_FIELDS = tuple(asdict(LearnerSettings()))


@dataclass(frozen=True, slots=True)
class SqlLearnerSettingsRepository(LearnerSettingsRepository):
    session: AsyncSession
    clock: Clock

    async def get(self, learner_id: UUID) -> LearnerSettings:
        query = select(learner_settings).where(learner_settings.c.learner_id == learner_id)
        row = (await self.session.execute(query)).mappings().first()
        if row is None:
            return LearnerSettings()
        values: dict[str, Any] = {name: row[name] for name in _FIELDS}
        values["how_to_read"] = HowToRead(values["how_to_read"])
        return LearnerSettings(**values)

    async def save(self, learner_id: UUID, settings: LearnerSettings) -> None:
        await self.change(learner_id, {name: getattr(settings, name) for name in _FIELDS})

    async def change(self, learner_id: UUID, fields: Mapping[str, Any]) -> None:
        values: dict[str, Any] = {name: fields[name] for name in _FIELDS if name in fields}
        if unknown := set(fields) - set(_FIELDS):
            raise KeyError(sorted(unknown))
        if "how_to_read" in values:
            values["how_to_read"] = str(values["how_to_read"])
        values["updated_at"] = self.clock.now()
        if await self._update(learner_id, values):
            return
        try:
            async with self.session.begin_nested():  # два апдейта ученика разом: вставит один
                await self.session.execute(
                    insert(learner_settings).values(learner_id=learner_id, **values)
                )
        except IntegrityError:
            if not await self._update(learner_id, values):  # не гонка, а нарушение CHECK/FK
                raise

    async def _update(self, learner_id: UUID, values: dict[str, Any]) -> bool:
        result = await self.session.execute(
            update(learner_settings)
            .where(learner_settings.c.learner_id == learner_id)
            .values(values)
        )
        return bool(getattr(result, "rowcount", 0))
