"""Чтения сур в БД (FR-60, ADR-0076): четыре новые таблицы, старые не меняются."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.domain.sura import (
    AyahReference,
    EventKind,
    ReadingChunk,
    SuraMode,
    SuraReading,
    assess_sura,
)
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.suras import SqlSuraReadingRepository
from muallim.infrastructure.db.tables import (
    sura_reading_ayahs,
    sura_reading_chunks,
    sura_reading_events,
    sura_readings,
)
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration

A1 = AyahReference("L123-02", 1, ("قُلْ", "هُوَ"))
A2 = AyahReference("L123-03", 2, ("سَمَدْ", "كَرِيمْ"))


def _learner(clock: FixedClock) -> Learner:
    return Learner(UUID(int=1), 4242, "L-00000001", "ru", clock.now())


def _reading(
    learner: Learner,
    clock: FixedClock,
    *,
    n: int,
    heard: str,
    mode: SuraMode,
    credited: tuple[str, ...] = (),
) -> SuraReading:
    assessment = assess_sura((A1, A2), heard, GradingPolicy(), pauses=((2, 3100),))
    half = len(heard) // 2
    return SuraReading(
        id=UUID(int=500 + n),
        learner_id=learner.id,
        sura=112,
        mode=mode,
        attempt_number=n,
        days_since_last=None if n == 1 else 2,
        studied_by_text=False,
        assessment=assessment,
        chunks=(
            ReadingChunk(0, 6000, heard[:half], 1, 1),
            ReadingChunk(6000, 9000, heard[half:], 1, 2),
        ),
        credited=credited,
        model_version="m",
        curriculum_version="v1",
        app_version="a",
        audio_sha256="b" * 64,
        audio_duration_ms=9000,
        processing_ms=700,
        created_at=clock.now(),
    )


async def _count(session: AsyncSession, table: object) -> int:
    return int((await session.execute(select(func.count()).select_from(table))).scalar_one())  # type: ignore[arg-type]


async def test_reading_is_saved_with_ayahs_chunks_and_events(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlSuraReadingRepository(session)
    # аят 2 ниже порога (три неверных звука; порог зачёта в суре — TD-FN-116) и пауза в аяте 1
    heard = "قُلْهُوَ" + "صُمَطْكَرِيمْ"
    reading = _reading(learner, clock, n=1, heard=heard, mode=SuraMode.MEMORY)
    await repo.add(reading)
    await session.commit()

    assert await _count(session, sura_readings) == 1
    assert await _count(session, sura_reading_ayahs) == 2
    assert await _count(session, sura_reading_chunks) == 2
    kinds = (await session.execute(select(sura_reading_events.c.kind))).scalars().all()
    assert EventKind.PAUSE in kinds and EventKind.PRONUNCIATION in kinds
    row = (await session.execute(select(sura_readings))).mappings().one()
    assert row["mode"] == "memory" and row["sura"] == 112
    assert row["passed"] is False and row["clean_ayahs"] == 1 and row["total_ayahs"] == 2


async def test_counts_last_read_and_memorized(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlSuraReadingRepository(session)
    clean = "قُلْهُوَ" + "سَمَدْكَرِيمْ"
    await repo.add(_reading(learner, clock, n=1, heard="قُلْ", mode=SuraMode.MEMORY))
    second = _reading(learner, clock, n=2, heard=clean, mode=SuraMode.MEMORY)
    await repo.add(second)
    await session.commit()

    assert await repo.count(learner.id, 112, SuraMode.MEMORY) == 2
    assert await repo.count(learner.id, 112, SuraMode.TEXT) == 0
    assert await repo.last_read(learner.id, 112) == second.created_at
    assert await repo.last_read(learner.id, 1) is None
    assert await repo.memorized(learner.id) == {112}
    assert await repo.audio_hashes(learner.id) == ["b" * 64, "b" * 64]


async def test_sura_passed_by_text_counts_in_best_scores(session: AsyncSession) -> None:
    """Зачёт «всё или ничего» виден прогрессу через лучшие баллы строк (FR-58)."""
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    clean = "قُلْهُوَ" + "سَمَدْكَرِيمْ"
    credited = ("L123-01", "L123-02", "L123-03")
    await SqlSuraReadingRepository(session).add(
        _reading(learner, clock, n=1, heard=clean, mode=SuraMode.TEXT, credited=credited)
    )
    await session.commit()

    best = await SqlAttemptRepository(session).best_scores(learner.id)
    assert {item: best[item] for item in credited} == dict.fromkeys(credited, 100)
    assert await SqlSuraReadingRepository(session).credited(learner.id) == set(credited)


async def test_deleting_learner_deletes_sura_readings(session: AsyncSession) -> None:
    """Удаление данных ученика стирает и чтения сур (FR-60, docs/security/privacy.md)."""
    clock = FixedClock()
    learner = _learner(clock)
    learners = SqlLearnerRepository(session)
    await learners.add(learner)
    await SqlSuraReadingRepository(session).add(
        _reading(learner, clock, n=1, heard="قُلْهُوَ", mode=SuraMode.TEXT)
    )
    await session.commit()
    await learners.delete(learner.id)
    await session.commit()
    for table in (sura_readings, sura_reading_ayahs, sura_reading_chunks, sura_reading_events):
        assert await _count(session, table) == 0


async def test_policy_is_saved(session: AsyncSession) -> None:
    from dataclasses import replace  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    reading = replace(
        _reading(learner, clock, n=1, heard="قُلْ", mode=SuraMode.TEXT),
        policy=GradingPolicy(pass_threshold=70, excellent_threshold=95),
    )
    await SqlSuraReadingRepository(session).add(reading)
    await session.commit()
    row = (await session.execute(select(sura_readings.c.policy))).scalar_one()
    assert row == {"pass_threshold": 70, "excellent_threshold": 95}


async def test_sura_reading_counts_in_daily_activity(session: AsyncSession) -> None:
    """Решение автора 2026-10-31: чтение суры — в серию дней и в «сегодня попыток»."""
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    reading = _reading(learner, clock, n=1, heard="قُلْ", mode=SuraMode.MEMORY)
    await SqlSuraReadingRepository(session).add(reading)
    await session.commit()
    days = await SqlAttemptRepository(session).activity(learner.id)
    assert sum(days.values()) == 1
