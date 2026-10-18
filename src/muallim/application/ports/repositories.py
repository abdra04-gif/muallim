"""Хранилища данных исследования."""

from collections.abc import Mapping
from datetime import date
from typing import Protocol
from uuid import UUID

from muallim.domain.assessment import Assessment
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import ConsentRecord, Learner, LearnerProfile
from muallim.domain.report import LearnerReport


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

    async def forget_audio(self, learner_id: UUID) -> list[str]:
        """Отзыв согласия: убирает ссылки на записи и разметку по ним; возвращает их SHA-256.

        Попытки (фонемы, баллы) остаются — по ним считается прогресс ученика.
        """

    async def audio_in_use(self, sha256: str) -> bool:
        """Есть ли ещё попытка с этой записью (ту же запись мог переслать другой ученик)."""

    async def owner(self, attempt_id: UUID) -> UUID | None:
        """Чья попытка (learner_id) или None, если такой нет."""

    async def add_report(self, report: LearnerReport) -> None: ...

    async def activity(self, learner_id: UUID) -> Mapping[date, int]:
        """Сколько попыток в каждый день (UTC) — для серии дней подряд."""


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
