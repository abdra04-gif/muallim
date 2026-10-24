"""Порты разметки в Telegram (FR-17): кто разметчик и что ему размечать."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from muallim.domain.annotation import AnnotationTask, Label


class AnnotatorDirectory(Protocol):
    """Разметчики по приглашению и по /annotate, отозванные коды. ANNOTATOR_IDS сюда не входит."""

    async def bound_code(self, telegram_user_id: int) -> str | None: ...

    async def is_revoked(self, code: str) -> bool: ...

    async def redeem(self, digest: str, telegram_user_id: int, now: datetime) -> str | None:
        """Код приглашения → код разметчика, приглашение гасится. None — нет, истекло, погашено."""

    async def failed_redeems(self, learner_id: UUID, since: datetime) -> int: ...

    async def add_failed_redeem(self, learner_id: UUID, at: datetime) -> None: ...

    async def register(self, telegram_user_id: int, reserved: frozenset[str], now: datetime) -> str:
        """Вход по /annotate: привязать к Telegram новый код (``next_annotator_code``).

        Код не совпадает ни с ``reserved`` (ANNOTATOR_IDS), ни с кодами разметчиков, приглашений и
        меток в БД. Уже привязанному — его код.
        """


class AnnotationTasks(Protocol):
    """Очередь разметки — та же, что у пакета Excel: свои метки разметчик больше не видит."""

    async def next_for(self, annotator: str, exclude: frozenset[UUID]) -> AnnotationTask | None: ...

    async def get(self, attempt_id: UUID) -> AnnotationTask | None:
        """None — попытки нет, у неё нет записи или ученик отозвал согласие."""

    async def remaining(self, annotator: str) -> int: ...

    async def add(self, label: Label) -> None: ...
