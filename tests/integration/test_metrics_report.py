"""Сбор метрик GQM из БД (SQLite; те же запросы — на PostgreSQL)."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations, interaction_events
from muallim.research import metrics

pytestmark = pytest.mark.integration
TODAY = date(2026, 10, 17)


def _at(day: int) -> datetime:
    return datetime(2026, 10, day, 12, 0, tzinfo=UTC)


async def _seed(session: AsyncSession) -> None:
    """Попытки 1–3 и 5 — настоящая модель, 4 — заглушка; разметка двумя учителями T1, T2."""
    policy = GradingPolicy()
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    a = Learner(UUID(int=1), 987654321, "L-aaaa", "ru", _at(1))
    b = Learner(UUID(int=2), 876543219, "L-bbbb", "ru", _at(15))
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

    def label(
        n: int,
        annotator: str,
        actual: str | None,
        *,
        status: str,
        day: int = 17,
        guide: str = "2.0",
    ) -> dict[str, object]:
        return {
            "attempt_id": UUID(int=n), "detected_error_id": None, "annotator": annotator,
            "label": status, "corrected_phonemes": actual, "guide_version": guide,
            "comment": "", "created_at": _at(day),
        }  # fmt: skip

    # Эталон «صَ». Разметчик пишет, что прозвучало на самом деле (docs/data/annotation-guide.md).
    await session.execute(
        insert(annotations),
        [
            label(1, "T1", "سَ", status="fix"),  # модель: верно; учитель: ص→س — пропуск (FA)
            label(1, "T2", None, status="audio_unusable"),  # не входит в метрики
            label(2, "T1", "سَ", status="agree"),  # модель и учитель: ص→س (TR, диагноз верный)
            label(2, "T2", "سَ", status="agree"),
            label(3, "T1", "صَ", status="agree"),  # оба: верно
            label(3, "T2", "صَ", status="agree"),
            label(5, "T1", "صِ", day=16, status="agree"),  # сначала согласился с моделью…
            label(
                5, "T1", "صَ", status="fix"
            ),  # …потом исправил: берётся последняя метка — ложная тревога
            label(
                5, "T2", None, status="correct", guide="1.0"
            ),  # старая метка без фонем — не в счёт
            label(4, "T1", "سَ", status="fix"),  # заглушка — не входит
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


async def test_phoneme_level_detection_from_annotations(session: AsyncSession) -> None:
    """Счёт по каждой фонеме эталона (L2-ARCTIC, Iqra'Eval); каждый разметчик — отдельно."""
    await _seed(session)
    m = await metrics.collect(session, TODAY)
    # 1/T1: TA1 FA1 · 2/T1, 2/T2: TA1 TR1 CD1 · 3/T1, 3/T2: TA2 · 5/T1 (последняя): TA1 FR1
    assert m.phonemes == metrics.PhonemeCounts(ta=8, fr=1, fa=1, tr=2, correct_diagnosis=2)
    assert m.quality.precision == pytest.approx(2 / 3)
    assert m.quality.recall == pytest.approx(2 / 3)
    assert m.quality.far == pytest.approx(1 / 3)
    assert m.quality.frr == pytest.approx(1 / 9)
    assert m.quality.diagnosis == pytest.approx(1.0)


async def test_detection_by_error_kind(session: AsyncSession) -> None:
    """Precision — по типу ошибки модели, recall — по типу ошибки в разметке."""
    await _seed(session)
    by_kind = (await metrics.collect(session, TODAY)).by_kind
    assert by_kind["letter_substitution"] == metrics.KindQuality(
        flagged=2, confirmed=2, errors=3, caught=2
    )
    assert by_kind["letter_substitution"].recall == pytest.approx(2 / 3)
    assert by_kind["vowel_substitution"].precision == pytest.approx(0.0)


async def test_false_accept_and_reject_rates(session: AsyncSession) -> None:
    """Вердикт учителя = та же политика оценки, применённая к его транскрипции."""
    await _seed(session)
    v = (await metrics.collect(session, TODAY)).verdicts
    assert (v.accepted, v.false_accepts, v.rejected, v.false_rejects) == (3, 1, 3, 1)
    assert v.far == pytest.approx(1 / 3) and v.frr == pytest.approx(1 / 3)


async def test_agreement_bot_teacher_and_between_teachers(session: AsyncSession) -> None:
    await _seed(session)
    m = await metrics.collect(session, TODAY)
    assert m.kappa_bot_teacher == pytest.approx(1 / 3) and m.pairs_bot_teacher == 6
    assert m.kappa_teachers == pytest.approx(1.0) and m.pairs_teachers == 2
    # α по фонемам: попытки 2 и 3 размечены двумя, по 2 фонемы — 4 единицы, полное согласие
    assert m.alpha_phonemes == pytest.approx(1.0) and m.alpha_units == 4


async def test_agreement_with_bot_per_annotator(session: AsyncSession) -> None:
    """Учёт: сколько раз разметчик согласился с ботом и сколько исправил — по вердикту бота."""
    await _seed(session)
    review = (await metrics.collect(session, TODAY)).review
    # T1 (последние метки): 1 fix — бот засчитал, 2 agree — не засчитал, 3 agree — засчитал,
    # 5 fix — не засчитал
    assert review["T1"] == metrics.ReviewCounts(
        agree_passed=1, fix_passed=1, agree_failed=1, fix_failed=1, unusable=0
    )
    assert review["T1"].agreement == pytest.approx(0.5)
    assert review["T2"].agreement == pytest.approx(1.0) and review["T2"].unusable == 1


async def test_annotation_coverage(session: AsyncSession) -> None:
    await _seed(session)
    m = await metrics.collect(session, TODAY)
    assert (m.annotated_attempts, m.double_annotated) == (4, 3)


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
    assert "κ" in md and "α" in md and "FAR" in md and "диагноз" in md
    assert "Согласие разметчиков с ботом" in md
    assert "987654321" not in md and "876543219" not in md


async def test_empty_database_renders_without_errors(session: AsyncSession) -> None:
    md = metrics.render(await metrics.collect(session, TODAY))
    assert "нет данных" in md
