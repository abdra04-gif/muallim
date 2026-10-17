"""Время и генерация идентификаторов — через порты, чтобы тесты были детерминированными."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_id(self) -> UUID: ...


class EventLog(Protocol):
    async def record(
        self, event: str, learner_id: UUID | None, payload: dict[str, str | int | None]
    ) -> None:
        """Журнал действий ученика (FR-12). В payload — без текста сообщений и личных данных."""


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """Версия кода, которая принимает решения: пишется в каждую попытку (ADR-0019)."""

    version: str
