"""Доверительные интервалы бутстрэпом по ученикам (FR-55, preregistration.md H1.2–H1.4).

Попытки одного ученика зависимы, поэтому выборка повторяется целыми учениками (кластерный
бутстрэп), а не отдельными попытками; интервал — процентильный 95 %.
"""

from collections.abc import Sequence
from statistics import fmean

import pytest

from muallim.research.metrics import BOOTSTRAP_REPS, cluster_bootstrap


def _mean(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def test_resamples_whole_learners_not_single_attempts() -> None:
    """Два ученика: у одного всё верно, у другого всё неверно. По ученикам — выборка из одного,
    другого или обоих, поэтому 95 % ДИ доли — от 0 до 1; по попыткам он был бы узким."""
    assert cluster_bootstrap([[1.0] * 4, [0.0] * 4], _mean) == (0.0, 1.0)


def test_constant_statistic_gives_point_interval() -> None:
    assert cluster_bootstrap([[1.0], [1.0], [1.0]], _mean) == (1.0, 1.0)


def test_interval_contains_estimate_and_is_ordered() -> None:
    clusters = [[0.0, 1.0], [1.0, 1.0], [0.0], [1.0, 0.0, 1.0], [1.0]]
    low, high = cluster_bootstrap(clusters, _mean) or (None, None)
    assert low is not None and high is not None
    assert low <= fmean(v for c in clusters for v in c) <= high


def test_same_seed_same_interval() -> None:
    """Повторный запуск отчёта даёт те же цифры (воспроизводимость, NFR)."""
    clusters = [[0.2], [0.4], [0.9], [0.5]]
    assert cluster_bootstrap(clusters, _mean) == cluster_bootstrap(clusters, _mean)
    assert cluster_bootstrap(clusters, _mean, seed=1) is not None


def test_fewer_than_two_learners_has_no_interval() -> None:
    assert cluster_bootstrap([], _mean) is None
    assert cluster_bootstrap([[1.0, 0.0, 1.0]], _mean) is None


def test_undefined_resamples_are_skipped() -> None:
    """Статистика не определена (например, precision без отметок модели) — повтор пропускается."""

    def only_with_ones(values: Sequence[float]) -> float | None:
        return 1.0 if 1.0 in values else None

    assert cluster_bootstrap([[1.0], [0.0]], only_with_ones) == (1.0, 1.0)
    assert cluster_bootstrap([[0.0], [0.0]], only_with_ones) is None


def test_default_repetitions() -> None:
    assert BOOTSTRAP_REPS >= 1000  # [утвердить]: 2000 — обычный выбор для 95 % процентильного ДИ


@pytest.mark.parametrize("level", [0.0, 1.0, 1.5])
def test_level_must_be_a_proper_fraction(level: float) -> None:
    with pytest.raises(ValueError, match="level"):
        cluster_bootstrap([[1.0], [0.0]], _mean, level=level)
