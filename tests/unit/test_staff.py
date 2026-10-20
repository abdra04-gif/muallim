"""Кто видит блок «Для исследования»: учитель и разметчик — одним методом (FR-50).

Признак считается в application (StaffAccess.is_staff), обработчик только спрашивает. Сбой базы
при проверке не должен лишать ученика результата: тогда он просто «не staff».
"""

from datetime import UTC, datetime
from uuid import UUID

from muallim.application.use_cases.annotation import AnnotatorAccess
from muallim.domain.learner import Learner
from tests.fakes import InMemoryAnnotators

TEACHER, ANNOTATOR, PUPIL = 7001, 7002, 7003
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _learner(tg: int) -> Learner:
    return Learner(UUID(int=tg), tg, f"L-{tg}", "ru", NOW)


class BrokenAnnotators(InMemoryAnnotators):
    """База недоступна: любая проверка разметчика падает."""

    async def bound_code(self, telegram_user_id: int) -> str | None:
        raise ConnectionError("база недоступна")


def _staff(directory: InMemoryAnnotators, configured: dict[int, str] | None = None):  # type: ignore[no-untyped-def]
    from muallim.application.use_cases.staff import StaffAccess  # noqa: PLC0415 — новый сценарий

    return StaffAccess(frozenset({TEACHER}), AnnotatorAccess(directory, configured or {}))


async def test_teacher_is_staff() -> None:
    assert await _staff(InMemoryAnnotators()).is_staff(_learner(TEACHER))


async def test_annotator_by_invite_is_staff() -> None:
    directory = InMemoryAnnotators(bound={ANNOTATOR: "A2"})
    assert await _staff(directory).is_staff(_learner(ANNOTATOR))


async def test_annotator_from_settings_is_staff() -> None:
    assert await _staff(InMemoryAnnotators(), {ANNOTATOR: "A1"}).is_staff(_learner(ANNOTATOR))


async def test_revoked_annotator_is_not_staff() -> None:
    directory = InMemoryAnnotators(bound={ANNOTATOR: "A2"}, revoked={"A2"})
    assert not await _staff(directory).is_staff(_learner(ANNOTATOR))


async def test_pupil_is_not_staff() -> None:
    assert not await _staff(InMemoryAnnotators()).is_staff(_learner(PUPIL))


async def test_broken_database_means_not_staff() -> None:
    """Проверка разметчика упала — ученик получает обычный результат, без блока."""
    assert not await _staff(BrokenAnnotators()).is_staff(_learner(PUPIL))
