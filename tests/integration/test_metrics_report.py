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
            "attempt_id": UUID(int=n), "annotator": annotator,
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


async def test_self_corrections_are_counted_separately(session: AsyncSession) -> None:
    """Решение автора 2026-10-18 (ADR-0044): ученик ошибся и тут же сам перечитал верно — в одном
    голосовом. Такая попытка не входит в главные цифры RQ-1, у неё — свой блок."""
    await _seed(session)
    before = await metrics.collect(session, TODAY)
    learner = Learner(UUID(int=3), 765432198, "L-cccc", "ru", _at(16))
    await SqlLearnerRepository(session).add(learner)
    heard = "سَصَ"  # «са…» — и сразу верно «ṣа»
    result = assess("صَ", heard)
    await SqlAttemptRepository(session).add(
        Attempt(UUID(int=6), learner.id, "L01-14", "v1", "muaalem", result,
                GradingPolicy().verdict(result), None, 900, 1200, _at(16)),
        tuple("msg" for _ in result.errors),
    )  # fmt: skip
    mark = {"comment": "", "guide_version": "2.1", "created_at": _at(17)}
    await session.execute(
        insert(annotations),
        [
            {"attempt_id": UUID(int=6), "annotator": "T1", "label": "agree",
             "corrected_phonemes": heard, "self_corrected": True, **mark},
            # второй разметчик не отметил — попытка всё равно отдельно: хватает одной отметки
            {"attempt_id": UUID(int=6), "annotator": "T2", "label": "agree",
             "corrected_phonemes": heard, "self_corrected": False, **mark},
        ],
    )  # fmt: skip
    await session.commit()

    m = await metrics.collect(session, TODAY)
    assert m.phonemes == before.phonemes and m.quality == before.quality
    assert m.verdicts == before.verdicts and m.pairs_bot_teacher == before.pairs_bot_teacher
    assert m.alpha_units == before.alpha_units
    own = metrics.phoneme_decisions("صَ", heard, heard)
    assert m.self_corrected.attempts == 1
    assert m.self_corrected.phonemes == own + own  # оба разметчика, как в главных цифрах
    assert m.self_corrected.quality == metrics.mdd_quality(own + own)
    assert before.self_corrected.attempts == 0
    assert "## Самоисправления" in metrics.render(m)


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


async def test_confidence_intervals_by_learner(session: AsyncSession) -> None:
    """95 % ДИ бутстрэпом по ученикам (preregistration.md H1.2–H1.4). Ученик B прочитал верно и
    модель ничего не отметила: выборки только из B не определяют precision и пропускаются, поэтому
    ДИ precision — от precision ученика A до неё же."""
    await _seed(session)
    ci = (await metrics.collect(session, TODAY)).ci
    assert set(ci) == {
        "precision", "recall", "F1", "FAR вердикта", "FRR вердикта",
        "κ бот — учитель", "κ учитель — учитель",
    }  # fmt: skip
    assert ci["precision"] == pytest.approx((2 / 3, 2 / 3))
    assert ci["recall"] == pytest.approx((2 / 3, 2 / 3))
    low, high = ci["κ бот — учитель"] or (2.0, -2.0)
    assert -1.0 <= low <= high <= 1.0


async def test_no_interval_with_one_learner(session: AsyncSession) -> None:
    """Один ученик — повторять выборку не из чего: ДИ нет, а не ложный нулевой разброс."""
    learner = Learner(UUID(int=1), 987654321, "L-aaaa", "ru", _at(1))
    await SqlLearnerRepository(session).add(learner)
    result = assess("صَ", "سَ")
    await SqlAttemptRepository(session).add(
        Attempt(UUID(int=1), learner.id, "L01-14", "v1", "muaalem", result,
                GradingPolicy().verdict(result), None, 900, 1000, _at(2)),
        ("msg",),
    )  # fmt: skip
    await session.execute(
        insert(annotations),
        [{"attempt_id": UUID(int=1), "annotator": "T1", "label": "agree",
          "corrected_phonemes": "سَ", "guide_version": "2.0", "comment": "",
          "created_at": _at(3)}],
    )  # fmt: skip
    await session.commit()
    ci = (await metrics.collect(session, TODAY)).ci
    assert all(value is None for value in ci.values())


async def test_detection_by_reference_sound(session: AsyncSession) -> None:
    """Q1.5: precision по звуку эталона, отмеченному моделью; recall — по разметке."""
    await _seed(session)
    by_sound = (await metrics.collect(session, TODAY)).by_sound
    assert by_sound["ص"] == metrics.KindQuality(flagged=2, confirmed=2, errors=3, caught=2)
    assert by_sound["َ"] == metrics.KindQuality(flagged=1, confirmed=0, errors=0, caught=0)


async def test_render_shows_intervals_and_sounds(session: AsyncSession) -> None:
    await _seed(session)
    md = metrics.render(await metrics.collect(session, TODAY))
    assert "95 % ДИ" in md and "бутстрэп" in md
    assert "По звуку эталона" in md
