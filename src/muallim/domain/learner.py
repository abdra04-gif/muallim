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
    """Родной язык из анкеты (FR-44) — группа для сравнения ошибок (E-1, бывшая H2.1; ADR-0051)."""

    RU = "ru"
    KK = "kk"
    TT = "tt"
    OTHER = "other"


class ArabicReading(StrEnum):
    """Опыт чтения по-арабски до бота (FR-44): от «с нуля» до «читаю уверенно» (FR-65)."""

    NONE = "none"
    SOME_LETTERS = "some_letters"
    SLOW_SYLLABLES = "slow_syllables"
    FLUENT = "fluent"


class AgeGroup(StrEnum):
    """Возрастная группа (FR-65): точный возраст не храним — для публикаций хватает групп."""

    U18 = "u18"
    A18_24 = "18_24"
    A25_34 = "25_34"
    A35_44 = "35_44"
    A45_54 = "45_54"
    A55_PLUS = "55_plus"


class Gender(StrEnum):
    MALE = "m"
    FEMALE = "f"


class Prayer(StrEnum):
    """Совершает ли намаз (FR-65): объясняет, насколько ученик знаком со звуками арабского."""

    NO = "no"
    SOMETIMES = "sometimes"
    REGULAR = "regular"


class Question(StrEnum):
    """Вопросы анкеты в порядке показа (FR-65). Значение — поле кнопки и событий."""

    NAME = "name"
    AGE = "age"
    GENDER = "gender"
    NATIVE = "native"
    READING = "reading"
    PRAYER = "prayer"


QUESTIONS: tuple[Question, ...] = tuple(Question)
NAME_MAX_LENGTH = 40


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    """Анкета ученика (FR-44, FR-65): заполняется по одному ответу, пропуск запоминается.

    ``display_name`` — единственное прямое ПДн анкеты: хранится в отдельной таблице и в отчёты,
    представления и выгрузки не попадает. Остальные поля — ковариаты исследования.
    """

    learner_id: UUID
    questionnaire_version: str
    answered_at: datetime
    display_name: str | None = None
    age_group: AgeGroup | None = None
    gender: Gender | None = None
    native_language: NativeLanguage | None = None
    arabic_reading: ArabicReading | None = None
    prayer: Prayer | None = None
    skipped: frozenset[Question] = frozenset()

    def has_answer(self, question: Question) -> bool:
        return self.value_of(question) is not None

    def value_of(self, question: Question) -> object | None:
        return {
            Question.NAME: self.display_name,
            Question.AGE: self.age_group,
            Question.GENDER: self.gender,
            Question.NATIVE: self.native_language,
            Question.READING: self.arabic_reading,
            Question.PRAYER: self.prayer,
        }[question]

    def next_question(self) -> Question | None:
        """Первый вопрос без ответа и не пропущенный; None — анкета закончена."""
        return next(
            (q for q in QUESTIONS if not self.has_answer(q) and q not in self.skipped), None
        )
