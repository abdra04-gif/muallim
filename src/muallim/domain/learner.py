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


class NativeLanguage(StrEnum):
    """Родной язык из анкеты (FR-44) — группа для сравнения ошибок (H2.1)."""

    RU = "ru"
    KK = "kk"
    TT = "tt"
    OTHER = "other"


class ArabicReading(StrEnum):
    """Опыт чтения по-арабски до бота (FR-44): новичок или продолжающий."""

    NONE = "none"
    SOME_LETTERS = "some_letters"
    SLOW_SYLLABLES = "slow_syllables"


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    """Анкета ученика: заполняется один раз. Младшим 18 остальное не задаётся (None)."""

    learner_id: UUID
    adult: bool
    native_language: NativeLanguage | None
    arabic_reading: ArabicReading | None
    questionnaire_version: str
    answered_at: datetime
