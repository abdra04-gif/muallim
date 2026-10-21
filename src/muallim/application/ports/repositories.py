"""Хранилища данных исследования."""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from muallim.domain.assessment import Assessment
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import ConsentRecord, Learner, LearnerProfile
from muallim.domain.report import LearnerReport
from muallim.domain.settings import LearnerSettings


class LearnerRepository(Protocol):
    async def get_by_telegram_id(self, telegram_user_id: int) -> Learner | None: ...

    async def add(self, learner: Learner) -> None: ...

    async def save(self, learner: Learner) -> None: ...

    async def add_consent(self, record: ConsentRecord) -> None: ...

    async def delete(self, learner_id: UUID) -> None:
        """Удаляет ученика и все его данные (право на удаление, FR-10)."""


class LearnerProfileRepository(Protocol):
    """Анкета ученика (FR-44). Удаляется вместе с учеником (FR-10)."""

    async def get(self, learner_id: UUID) -> LearnerProfile | None: ...

    async def add(self, profile: LearnerProfile) -> None: ...


class AttemptRepository(Protocol):
    async def add(self, attempt: Attempt, feedback: tuple[str, ...]) -> None: ...

    async def best_scores(self, learner_id: UUID) -> Mapping[str, int]:
        """Лучший балл по каждой карточке: item_id -> score."""

    async def count(self, learner_id: UUID) -> int: ...

    async def last_assessment(self, learner_id: UUID, item_id: str) -> Assessment | None:
        """Оценка последней попытки этой строки — для «было → стало»; None — первая."""

    async def audio_hashes(self, learner_id: UUID) -> list[str]: ...

    async def forget_audio(self, learner_id: UUID, until: datetime | None = None) -> list[str]:
        """Отзыв согласия: убирает ссылки на записи и разметку по ним; возвращает их SHA-256.

        Попытки (фонемы, баллы) остаются — по ним считается прогресс ученика. ``until`` — только
        попытки не позже этого момента (повтор журнала удалений после восстановления копии).
        """

    async def audio_in_use(self, sha256: str) -> bool:
        """Есть ли ещё попытка с этой записью (ту же запись мог переслать другой ученик)."""

    async def owner(self, attempt_id: UUID) -> UUID | None:
        """Чья попытка (learner_id) или None, если такой нет."""

    async def add_report(self, report: LearnerReport) -> bool:
        """False — жалоба этого ученика на эту попытку уже есть (повторное нажатие)."""

    async def activity(self, learner_id: UUID) -> Mapping[date, int]:
        """Сколько попыток в каждый местный день ученика — для серии дней и начала занятия.

        День — по смещению ученика (``learner_settings.utc_offset_min``, ADR-0061).
        """


class LearnerSettingsRepository(Protocol):
    """Настройки ученика и состояние его экрана (ADR-0061). Удаляются вместе с учеником."""

    async def get(self, learner_id: UUID) -> LearnerSettings:
        """Нет записи — умолчания (``LearnerSettings()``)."""

    async def save(self, learner_id: UUID, settings: LearnerSettings) -> None:
        """Записать все поля целиком (None — это значение, а не «не менять»)."""

    async def change(self, learner_id: UUID, fields: Mapping[str, Any]) -> None:
        """Записать только эти поля: параллельный переход экрана не затрёт чужие."""

    async def claim_reminder(self, learner_id: UUID, today: date) -> bool:
        """Атомарно отметить «сегодня напомнили» (``reminder_sent_on = today``), если ещё не
        отмечено этой датой; False — уже отмечено (другой тик или процесс успел)."""


class ReminderRecipients(Protocol):
    """Кому может прийти напоминание о занятии (ADR-0061 п. 4)."""

    async def candidates(self) -> list[UUID]:
        """Ученики с включённым напоминанием, не заблокировавшие бота."""

    async def learner(self, learner_id: UUID) -> Learner | None: ...


class CurriculumVersionError(Exception):
    """Контент программы изменился, а версия — нет: попытки нельзя будет связать с текстом."""


class CurriculumSnapshots(Protocol):
    async def publish(self, curriculum: Curriculum) -> int:
        """Сохраняет снимок версии программы; возвращает число новых карточек (0 — уже есть).

        Бросает CurriculumVersionError, если такая версия уже сохранена с другим содержимым.
        """


class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
