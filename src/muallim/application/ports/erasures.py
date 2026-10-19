"""Журнал удалений вне БД (TD-DB-05, ADR-0054).

Восстановленная копия БД не знает об удалениях, сделанных после неё. Журнал хранится отдельно
от БД и от копий и повторяется после восстановления — так право ученика на удаление не теряется.
"""

from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ErasureAction(StrEnum):
    DELETE = "delete"  # «Удалить мои данные»
    WITHDRAW = "withdraw"  # отзыв согласия на запись голоса
    GRANT = "grant"  # согласие дано снова — записи после него не трогать


class ErasureLog(Protocol):
    async def record(self, action: ErasureAction, learner_id: UUID) -> None:
        """Записывает до commit: сбой БД не теряет намерение ученика, повтор безвреден."""
