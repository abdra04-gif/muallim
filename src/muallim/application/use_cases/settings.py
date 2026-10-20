"""Настройки ученика: прочитать и поменять одну (FR-51, ADR-0061).

Каждая смена пишет событие ``setting_changed`` (``{"name", "value"}``): при каких настройках
сделана попытка, восстанавливается по журналу (QAS-09, В6).
"""

from dataclasses import dataclass
from typing import Final

from muallim.application.ports.repositories import LearnerSettingsRepository, UnitOfWork
from muallim.application.ports.system import EventLog
from muallim.domain.learner import Learner
from muallim.domain.settings import HowToRead, LearnerSettings

HOW_TO_READ: Final = "how_to_read"
TOGGLES: Final = ("auto_reference", "daily_opening", "large_font", "research_block")
_BOOL: Final = {"true": True, "false": False}


def parse(name: str, value: str) -> bool | HowToRead:
    """Значение из кнопки; неизвестная настройка или значение — ``ValueError``."""
    if name == HOW_TO_READ:
        return HowToRead(value)
    if name in TOGGLES and value in _BOOL:
        return _BOOL[value]
    raise ValueError(f"нет настройки {name}={value}")


@dataclass(frozen=True, slots=True)
class GetSettings:
    settings: LearnerSettingsRepository

    async def execute(self, learner: Learner) -> LearnerSettings:
        return await self.settings.get(learner.id)


@dataclass(frozen=True, slots=True)
class ChangeSetting:
    settings: LearnerSettingsRepository
    uow: UnitOfWork
    events: EventLog

    async def execute(self, learner: Learner, name: str, value: str) -> LearnerSettings:
        """Поставить значение; то же самое ещё раз — ничего не пишет."""
        parsed = parse(name, value)
        current = await self.settings.get(learner.id)
        if getattr(current, name) == parsed:
            return current
        await self.settings.change(learner.id, {name: parsed})
        logged = parsed.value if isinstance(parsed, HowToRead) else parsed
        await self.events.record("setting_changed", learner.id, {"name": name, "value": logged})
        await self.uow.commit()
        return await self.settings.get(learner.id)
