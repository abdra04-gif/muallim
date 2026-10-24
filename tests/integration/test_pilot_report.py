"""Сбор метрик пилота из БД (FR-55; SQLite в тестах, те же запросы — на PostgreSQL)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy, Verdict
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import curriculum_items, interaction_events
from muallim.research import pilot

pytestmark = pytest.mark.integration
MON = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
TODAY = date(2026, 11, 4)  # B занимался 27.10 — 8 дней назад, A — 19.10


def _item(item_id: str, lesson: int) -> dict[str, object]:
    return {
        "curriculum_version": "v1", "item_id": item_id, "lesson_id": f"L{lesson:02d}",
        "lesson_number": lesson, "lesson_title": "—", "position": 1, "kind": "practice",
        "text": "صَ", "note": "", "verified": False, "published_at": MON,
    }  # fmt: skip


async def _seed(session: AsyncSession) -> None:
    """A: «سَ» (ошибка) → эталон 🔊 → «صَ» (зачёт); B: зачёт сразу; заглушка — не в счёт."""
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    a = Learner(UUID(int=1), 987654321, "L-aaaa", "ru", MON)
    b = Learner(UUID(int=2), 876543219, "L-bbbb", "ru", MON)
    await learners.add(a)
    await learners.add(b)
    await session.execute(insert(curriculum_items), [_item("L01-1", 1), _item("L02-1", 2)])
    policy = GradingPolicy()
    plan = [  # n, ученик, строка, услышано, минут от MON, processing_ms, модель
        (1, a, "L01-1", "سَ", 10, 1000, "muaalem"),
        (2, a, "L01-1", "صَ", 20, 3000, "muaalem"),
        (3, b, "L01-1", "صَ", 60 * 24 * 8, 2000, "muaalem"),  # 27.10 — следующая неделя
        (4, a, "L02-1", "صَ", 30, 99999, "stub"),  # заглушка — не в счёт
    ]
    for n, learner, item, heard, minutes, ms, model in plan:
        result = assess("صَ", heard)
        await attempts.add(
            Attempt(
                UUID(int=n), learner.id, item, "v1", model, result, policy.verdict(result),
                None, 900, ms, MON + timedelta(minutes=minutes),
            ),
            tuple("msg" for _ in result.errors),
        )  # fmt: skip
    await session.execute(
        insert(interaction_events),
        [
            {"learner_id": a.id, "event": "reference_played", "payload": {"item_id": "L01-1"},
             "created_at": MON + timedelta(minutes=15)},
        ],
    )  # fmt: skip
    await session.commit()


async def test_weekly_new_lines_from_real_attempts(session: AsyncSession) -> None:
    await _seed(session)
    r = await pilot.collect(session, TODAY)
    assert [(w.week, w.lines, w.learners) for w in r.weekly] == [
        (date(2026, 10, 19), 1, 1),
        (date(2026, 10, 26), 1, 1),
    ]


async def test_first_success_and_effort(session: AsyncSession) -> None:
    await _seed(session)
    r = await pilot.collect(session, TODAY)
    assert r.first_success == pilot.FirstSuccess(
        learners=2, passed_ever=2, passed_same_day=1, median_minutes=(20 + 60 * 24 * 8) / 2
    )
    assert r.effort == {1: pilot.LessonEffort(passed=2, median_attempts=1.5, not_passed=0)}


async def test_drop_off_uses_lesson_from_curriculum_snapshot(session: AsyncSession) -> None:
    await _seed(session)
    r = await pilot.collect(session, TODAY)
    assert r.drop_off == {1: 2}  # оба не занимались 7+ дней; заглушка на уроке 2 не в счёт


async def test_retry_with_reference_and_fixed_named_error(session: AsyncSession) -> None:
    """Названная ботом ошибка берётся из detected_errors попытки n (позиция и нужный звук)."""
    await _seed(session)
    retries = (await pilot.collect(session, TODAY)).retries
    assert retries[pilot.ALL] == pilot.RetryEffect(
        pairs=1,
        mean_delta=50.0,
        improved=1,
        named=1,
        fixed=1,  # «سَ» = 50 → «صَ» = 100
    )
    assert retries[pilot.WITH_REFERENCE].pairs == 1
    assert retries[pilot.WITHOUT_REFERENCE].pairs == 0


async def test_response_time_by_day_excludes_stub(session: AsyncSession) -> None:
    await _seed(session)
    days = (await pilot.collect(session, TODAY)).response
    assert [(d.day, d.attempts, d.max_ms) for d in days] == [
        (date(2026, 10, 19), 2, 3000),
        (date(2026, 10, 27), 1, 2000),
    ]


async def test_verdict_is_taken_as_stored(session: AsyncSession) -> None:
    """Попытка засчитана ботом с тогдашними порогами — так и считается, даже если балл < 80."""
    await _seed(session)
    learner = Learner(UUID(int=3), 765432198, "L-cccc", "ru", MON)
    await SqlLearnerRepository(session).add(learner)
    result = assess("صَ", "سَ")
    await SqlAttemptRepository(session).add(
        Attempt(UUID(int=9), learner.id, "L02-1", "v1", "muaalem", result, Verdict.PASSED,
                None, 900, 500, MON),
        tuple("msg" for _ in result.errors),
    )  # fmt: skip
    await session.commit()
    r = await pilot.collect(session, TODAY)
    assert r.weekly[0].lines == 2 and r.weekly[0].learners == 2


async def test_render_is_markdown_without_telegram_ids(session: AsyncSession) -> None:
    await _seed(session)
    md = pilot.render(await pilot.collect(session, TODAY))
    for heading in ("Главная метрика", "Путь новичка", "Повтор после объяснения", "по дням"):
        assert heading in md
    assert "987654321" not in md and "876543219" not in md
    assert "L-aaaa" not in md  # в отчёте пилота — только агрегаты


async def test_empty_database_renders_without_errors(session: AsyncSession) -> None:
    md = pilot.render(await pilot.collect(session, TODAY))
    assert "нет данных" in md
