"""Хранилище настроек и состояния экрана ученика на SQL (FR-51, TD-FN-90, ADR-0061).

Одна строка `learner_settings` на ученика. Строки нет — ученик ничего не менял: действуют
умолчания (как бот работает сейчас). Идёт на SQLite и — при TEST_POSTGRES_URL — на PostgreSQL.
"""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.learner import Learner
from muallim.domain.settings import HowToRead, LearnerSettings
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.settings import SqlLearnerSettingsRepository
from muallim.infrastructure.db.tables import learner_settings
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration
LEARNER = UUID(int=1)

CHANGED = LearnerSettings(
    how_to_read=HowToRead.HIDDEN,
    auto_reference=True,
    daily_opening=False,
    large_font=True,
    research_block=True,
    reminder_minute=19 * 60 + 30,
    utc_offset_min=300,
    screen_item_id="L006-02",
    screen_opening=True,
    opening_resume_item="L006-01",
    opening_day=date(2026, 10, 21),
    opening_skipped_on=date(2026, 10, 20),
    reminder_sent_on=date(2026, 10, 19),
)


async def _repo(session: AsyncSession) -> tuple[SqlLearnerSettingsRepository, FixedClock]:
    clock = FixedClock()
    await SqlLearnerRepository(session).add(Learner(LEARNER, 77, "L-set", "ru", clock.now()))
    await session.commit()
    return SqlLearnerSettingsRepository(session, clock), clock


async def test_learner_without_row_gets_defaults(session: AsyncSession) -> None:
    repo, _ = await _repo(session)
    assert await repo.get(LEARNER) == LearnerSettings()


async def test_every_field_survives_save_and_get(session: AsyncSession) -> None:
    repo, _ = await _repo(session)
    await repo.save(LEARNER, CHANGED)
    await session.commit()
    session.expunge_all()
    assert await repo.get(LEARNER) == CHANGED


async def test_save_twice_keeps_one_row_with_last_values(session: AsyncSession) -> None:
    repo, clock = await _repo(session)
    await repo.save(LEARNER, CHANGED)
    await session.commit()
    await repo.save(LEARNER, LearnerSettings(large_font=True))
    await session.commit()
    assert await repo.get(LEARNER) == LearnerSettings(large_font=True)
    assert await session.scalar(select(func.count()).select_from(learner_settings)) == 1
    updated = await session.scalar(select(learner_settings.c.updated_at))
    assert updated == clock.current, "updated_at — время последнего сохранения (Clock)"


async def test_screen_can_be_reset_to_menu(session: AsyncSession) -> None:
    """NULL в screen_item_id — на экране меню; сохранение None не путается с «не менять»."""
    repo, _ = await _repo(session)
    await repo.save(LEARNER, CHANGED)
    await session.commit()
    menu = LearnerSettings(screen_item_id=None, opening_resume_item=None, opening_day=None)
    await repo.save(LEARNER, menu)
    await session.commit()
    assert await repo.get(LEARNER) == menu


async def test_save_rejects_impossible_offset_for_learner_without_row(
    session: AsyncSession,
) -> None:
    """Нарушение CHECK при первой записи не теряется молча (ревью круга 2)."""
    repo, _ = await _repo(session)
    with pytest.raises(IntegrityError):
        await repo.save(LEARNER, LearnerSettings(utc_offset_min=900))


async def test_change_writes_only_given_fields(session: AsyncSession) -> None:
    """Два перехода экрана подряд не затирают чужие поля (потерянное обновление, ревью круга 2)."""
    repo, _ = await _repo(session)
    await repo.change(LEARNER, {"opening_resume_item": "L006-01", "screen_opening": True})
    await repo.change(LEARNER, {"screen_item_id": None, "screen_opening": False})
    await session.commit()
    session.expunge_all()
    got = await repo.get(LEARNER)
    assert got.opening_resume_item == "L006-01"
    assert got.screen_item_id is None
    assert got.screen_opening is False
    assert got.how_to_read is HowToRead.SPOILER
