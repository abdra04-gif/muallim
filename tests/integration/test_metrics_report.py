"""Сбор метрик GQM из БД (SQLite; те же запросы — на PostgreSQL)."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations, detected_errors, interaction_events
from muallim.research import metrics

pytestmark = pytest.mark.integration
TODAY = date(2026, 10, 17)


def _at(day: int) -> datetime:
    return datetime(2026, 10, day, 12, 0, tzinfo=UTC)


async def _seed(session: AsyncSession) -> dict[int, str]:
    """Попытки 1–3 и 5 — настоящая модель, 4 — заглушка; разметка двумя учителями T1, T2."""
    policy = GradingPolicy()
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    a = Learner(UUID(int=1), 111, "L-aaaa", "ru", _at(1))
    b = Learner(UUID(int=2), 222, "L-bbbb", "ru", _at(15))
    await learners.add(a)
    await learners.add(b)
    plan = [  # n, ученик, услышано, день, processing_ms, модель
        (1, a, "صَ", 1, 1000, "muaalem"),  # засчитано
        (2, a, "سَ", 9, 2000, "muaalem"),  # не засчитано, ошибка буквы
        (3, b, "صَ", 15, 3000, "muaalem"),  # засчитано
        (4, a, "صَ", 2, 99999, "stub"),  # заглушка — не в счёт
        (5, a, "صِ", 9, 1500, "muaalem"),  # не засчитано, ошибка огласовки
    ]
    for n, learner, heard, day, ms, model in plan:
        result = assess("صَ", heard)
        await attempts.add(
            Attempt(
                UUID(int=n), learner.id, "L01-14", "v1", model, result,
                policy.verdict(result), None, 900, ms, _at(day),
            ),
            tuple("msg" for _ in result.errors),
        )  # fmt: skip
    rows = await session.execute(select(detected_errors.c.attempt_id, detected_errors.c.id))
    error_of = {attempt.int: error_id for attempt, error_id in rows.all()}

    def label(n: int, annotator: str, value: str, *, on_error: bool = False) -> dict[str, object]:
        return {
            "attempt_id": UUID(int=n),
            "detected_error_id": error_of[n] if on_error else None,
            "annotator": annotator, "label": value, "guide_version": "1.0",
            "comment": "", "created_at": _at(17),
        }  # fmt: skip

    await session.execute(
        insert(annotations),
        [
            label(2, "T1", "correct", on_error=True),  # TP
            label(5, "T1", "false_alarm", on_error=True),  # FP
            label(1, "T1", "missed_error"),  # FN; бот засчитал, учитель — нет
            label(2, "T1", "correct"),
            label(5, "T1", "false_alarm"),  # бот не засчитал верное чтение
            label(3, "T1", "correct"),
            label(3, "T2", "correct"),
            label(2, "T2", "correct"),
            label(1, "T2", "audio_unusable"),  # не входит в метрики
            label(4, "T1", "correct"),  # заглушка — не входит
        ],
    )
    events: list[tuple[str, dict[str, object]]] = [("attempt_assessed", {})] * 3 + [
        ("recognition_failed", {"item_id": "L01-14", "stage": "model", "processing_ms": 40}),
        ("recognition_failed", {"item_id": "L01-14", "stage": "decode", "processing_ms": 5}),
    ]
    await session.execute(
        insert(interaction_events),
        [{"learner_id": a.id, "event": e, "payload": p, "created_at": _at(16)} for e, p in events],
    )
    await session.commit()
    kinds = await session.execute(select(detected_errors.c.attempt_id, detected_errors.c.kind))
    return {attempt.int: kind for attempt, kind in kinds.all()}


async def test_detection_quality_from_annotations(session: AsyncSession) -> None:
    kinds = await _seed(session)
    m = await metrics.collect(session, TODAY)
    assert (m.detection.tp, m.detection.fp, m.detection.fn) == (1, 1, 1)
    assert m.detection.precision == pytest.approx(0.5)
    assert m.detection.recall == pytest.approx(0.5)
    assert m.by_kind[kinds[2]].precision == pytest.approx(1.0)
    assert m.by_kind[kinds[5]].precision == pytest.approx(0.0)


async def test_false_accept_and_reject_rates(session: AsyncSession) -> None:
    await _seed(session)
    v = (await metrics.collect(session, TODAY)).verdicts
    assert (v.accepted, v.false_accepts, v.rejected, v.false_rejects) == (3, 1, 3, 1)
    assert v.far == pytest.approx(1 / 3) and v.frr == pytest.approx(1 / 3)


async def test_kappa_bot_vs_teacher_and_between_teachers(session: AsyncSession) -> None:
    await _seed(session)
    m = await metrics.collect(session, TODAY)
    assert m.kappa_bot_teacher == pytest.approx(1 / 3) and m.pairs_bot_teacher == 6
    assert m.kappa_teachers == pytest.approx(1.0) and m.pairs_teachers == 2


async def test_response_time_excludes_stub(session: AsyncSession) -> None:
    await _seed(session)
    t = (await metrics.collect(session, TODAY)).response
    assert (t.attempts, t.p50_ms, t.p90_ms, t.max_ms) == (4, 1500, 3000, 3000)


async def test_recognition_failure_share_by_stage(session: AsyncSession) -> None:
    await _seed(session)
    f = (await metrics.collect(session, TODAY)).failures
    assert (f.failed, f.assessed) == (2, 3) and f.share == pytest.approx(0.4)
    assert f.by_stage == {"model": 1, "decode": 1}


async def test_retention_from_real_attempts(session: AsyncSession) -> None:
    await _seed(session)
    r = (await metrics.collect(session, TODAY)).retention
    assert r == metrics.Retention(learners=2, returned=1, cohort_7d=1, returned_7d=1)


async def test_render_is_markdown_without_telegram_ids(session: AsyncSession) -> None:
    await _seed(session)
    md = metrics.render(await metrics.collect(session, TODAY))
    for heading in ("Точность проверки", "Время ответа", "Сбои распознавания", "Возврат учеников"):
        assert f"## {heading}" in md
    assert "κ" in md and "FAR" in md
    assert "111" not in md and "222" not in md


async def test_empty_database_renders_without_errors(session: AsyncSession) -> None:
    md = metrics.render(await metrics.collect(session, TODAY))
    assert "нет данных" in md
