"""Формулы метрик GQM (docs/research/metrics-gqm.md): G1 — точность, G4 — возврат, G5 — система."""

from datetime import date

import pytest

from muallim.research.metrics import (
    Retention,
    cohen_kappa,
    detection_quality,
    nearest_rank,
    retention,
    teacher_passes,
)


def test_detection_quality_precision_recall_f1() -> None:
    q = detection_quality(tp=8, fp=2, fn=2)
    assert q.precision == pytest.approx(0.8)
    assert q.recall == pytest.approx(0.8)
    assert q.f1 == pytest.approx(0.8)


def test_detection_quality_without_data_is_undefined() -> None:
    q = detection_quality(tp=0, fp=0, fn=0)
    assert q.precision is None and q.recall is None and q.f1 is None


def test_detection_quality_without_missed_errors_known_has_no_recall() -> None:
    """По типу ошибки пропуски неизвестны: `missed_error` ставится на всю попытку."""
    q = detection_quality(tp=3, fp=1, fn=None)
    assert q.precision == pytest.approx(0.75) and q.recall is None and q.f1 is None


@pytest.mark.parametrize(
    ("label", "bot_passed", "expected"),
    [
        ("correct", True, True),  # бот прав — учитель согласен с его вердиктом
        ("correct", False, False),
        ("false_alarm", False, True),  # бот нашёл несуществующую ошибку — прочитано верно
        ("missed_error", True, False),  # бот пропустил ошибку — читать заново
        ("wrong_error", True, False),  # ошибка была, хоть и описана не так
        ("audio_unusable", True, None),  # оценить нельзя — не входит в метрики
        ("off_task", False, None),
    ],
)
def test_teacher_verdict_from_label(label: str, bot_passed: bool, expected: bool | None) -> None:
    assert teacher_passes(label, bot_passed) is expected


def test_cohen_kappa_known_value() -> None:
    # 4 оба «да», 1 «да/нет», 2 «нет/да», 3 оба «нет»: po = 0,7, pe = 0,5 → κ = 0,4
    pairs = [(True, True)] * 4 + [(True, False)] + [(False, True)] * 2 + [(False, False)] * 3
    assert cohen_kappa(pairs) == pytest.approx(0.4)


def test_cohen_kappa_perfect_agreement() -> None:
    assert cohen_kappa([(True, True), (False, False)]) == pytest.approx(1.0)


def test_cohen_kappa_undefined_without_variation_or_data() -> None:
    assert cohen_kappa([]) is None
    assert cohen_kappa([(True, True), (True, True)]) is None  # pe = 1


def test_nearest_rank_percentiles() -> None:
    values = [100 * i for i in range(10, 0, -1)]  # порядок не важен
    assert nearest_rank(values, 50) == 500
    assert nearest_rank(values, 90) == 900
    assert nearest_rank(values, 100) == 1000
    assert nearest_rank([], 90) is None


def test_retention_counts_returns_and_seven_day_cohort() -> None:
    today = date(2026, 10, 17)
    days = {
        "L-a": {date(2026, 10, 1), date(2026, 10, 9)},  # вернулся, и через ≥ 7 дней
        "L-b": {date(2026, 10, 2), date(2026, 10, 3)},  # вернулся, но не через 7 дней
        "L-c": {date(2026, 10, 15), date(2026, 10, 16)},  # слишком новый для 7-дневной когорты
        "L-d": {date(2026, 10, 5)},  # не вернулся
    }
    assert retention(days, today) == Retention(learners=4, returned=3, cohort_7d=3, returned_7d=1)
