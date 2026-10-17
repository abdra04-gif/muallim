"""Ученик и его согласия на обработку данных."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ConsentKind(StrEnum):
    # Хранить голосовые записи и использовать их для исследования и обучения модели (FR-09).
    RESEARCH_AUDIO = "research_audio"


@dataclass(slots=True)
class Learner:
    id: UUID
    telegram_user_id: int  # персональные данные: в выгрузки для исследования не попадает
    pseudonym: str  # например "L-7f3a9c"; только он используется в датасетах и отчётах
    language: str
    created_at: datetime
    current_item_id: str | None = None
    research_consent: bool = False
    blocked_bot: bool = False
    feedback_language: str | None = None  # выбран в /language; None — по языку Telegram


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    """Запись журнала согласий: каждое «да» и «нет» хранится, а не перезаписывается."""

    learner_id: UUID
    kind: ConsentKind
    granted: bool
    text_version: str  # версия текста согласия, который видел ученик
    at: datetime
