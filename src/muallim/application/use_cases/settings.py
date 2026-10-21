"""Настройки ученика: прочитать и поменять одну (FR-51, ADR-0061).

Каждая смена пишет событие ``setting_changed`` (``{"name", "value"}``): при каких настройках
сделана попытка, восстанавливается по журналу (QAS-09, В6). Смещение от UTC — данные работы
сервиса: в журнал без значения (ADR-0061, круг 2).
"""

import re
from dataclasses import dataclass
from typing import Final

from muallim.application.ports.repositories import LearnerSettingsRepository, UnitOfWork
from muallim.application.ports.system import EventLog
from muallim.domain.learner import Learner
from muallim.domain.settings import (
    MAX_UTC_OFFSET_MIN,
    MIN_UTC_OFFSET_MIN,
    MINUTES_PER_DAY,
    HowToRead,
    LearnerSettings,
    offset_on_grid,
    reminder_on_grid,
)

HOW_TO_READ: Final = "how_to_read"
TOGGLES: Final = ("auto_reference", "daily_opening", "large_font", "research_block")
REMINDER_MINUTE: Final = "reminder_minute"
UTC_OFFSET: Final = "utc_offset_min"
REMINDER_OFF: Final = "off"  # значение кнопки «выключить напоминание»
_BOOL: Final = {"true": True, "false": False}
_INT: Final = re.compile(r"-?\d{1,4}", re.ASCII)

SettingValue = bool | HowToRead | int | None


def _int(name: str, value: str, low: int, high: int) -> int:
    if _INT.fullmatch(value) and low <= (number := int(value)) <= high:
        return number
    raise ValueError(f"нет настройки {name}={value}")


def parse(name: str, value: str) -> SettingValue:
    """Значение из кнопки в границах CHECK таблицы (ADR-0055); иначе — ``ValueError``.

    Белый список: кнопкой меняются только настройки, не состояние экрана.
    """
    if name == HOW_TO_READ:
        return HowToRead(value)
    if name in TOGGLES and value in _BOOL:
        return _BOOL[value]
    if name == REMINDER_MINUTE:
        return None if value == REMINDER_OFF else _int(name, value, 0, MINUTES_PER_DAY - 1)
    if name == UTC_OFFSET:
        return _int(name, value, MIN_UTC_OFFSET_MIN, MAX_UTC_OFFSET_MIN)
    raise ValueError(f"нет настройки {name}={value}")


def _on_screen_grid(name: str, parsed: SettingValue) -> bool:
    """Час и смещение — только из сетки экрана 🔔 (ADR-0061 п. 3)."""
    if name == REMINDER_MINUTE:
        return reminder_on_grid(parsed if isinstance(parsed, int) else None)
    if name == UTC_OFFSET:
        return isinstance(parsed, int) and offset_on_grid(parsed)
    return True


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
        if not _on_screen_grid(name, parsed):
            raise ValueError(f"не с экрана: {name}={value}")
        current = await self.settings.get(learner.id)
        if getattr(current, name) == parsed:
            return current
        await self.settings.change(learner.id, {name: parsed})
        payload: dict[str, str | int | None] = {"name": name}
        if name != UTC_OFFSET:  # смещение — данные работы сервиса, без значения
            payload["value"] = parsed.value if isinstance(parsed, HowToRead) else parsed
        await self.events.record("setting_changed", learner.id, payload)
        await self.uow.commit()
        return await self.settings.get(learner.id)
