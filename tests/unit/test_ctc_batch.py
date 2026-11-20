"""Батч-CTC: баллы многих вариантов за один проход по записи (FR-70 п. 2–4, ADR-0088 п. 2;
блокер ревью «подсчёт вариантов в потоке бота до ~15 с»).

Предложенный интерфейс: ``ctc.ctc_logprob_many(lp, targets, blank) -> list[float]`` — то же, что
``[ctc_logprob(lp, t, blank) for t in targets]``, но векторно по вариантам. Матрицы — случайные
логарифмы вероятностей с закреплённым seed; эталон — поштучный ``ctc_logprob`` (уже сверен с
прототипом и перебором путей в `test_ctc.py`).
numpy ставится с моделью (extra ``ml``); без него тесты пропускаются.
"""

import math
import time
from collections.abc import Sequence
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from muallim.infrastructure.asr import ctc  # noqa: E402
from muallim.infrastructure.asr.ctc import ctc_logprob  # noqa: E402

BLANK = 0
# Бюджет с большим запасом: поштучный подсчёт тех же 2000 вариантов идёт порядка 10 с, батч —
# доли секунды. Тест ловит возврат к поштучному циклу, а не колебания машины CI.
BUDGET_S = 2.0


def _lp(rng: Any, frames: int, symbols: int) -> Any:
    p = rng.random((frames, symbols)) + 1e-3
    return np.log(p / p.sum(axis=1, keepdims=True))


def _same(got: Sequence[float], expected: Sequence[float]) -> None:
    assert len(got) == len(expected)
    for g, e in zip(got, expected, strict=True):
        if e == -math.inf:
            assert g == -math.inf
        else:
            assert g == pytest.approx(e, rel=0, abs=1e-9)


def _many(lp: Any, targets: Sequence[Sequence[int]]) -> list[float]:
    return list(ctc.ctc_logprob_many(lp, targets, BLANK))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_batch_matches_one_by_one_on_targets_of_different_length(seed: int) -> None:
    rng = np.random.default_rng(seed)
    lp = _lp(rng, 20, 8)
    targets = [list(rng.integers(1, 8, size=int(n))) for n in rng.integers(1, 10, size=30)]
    targets += [[3, 3], [3, 3, 3], [1, 2, 1, 2]]  # повтор подряд — нужен «пустой» между
    _same(_many(lp, targets), [ctc_logprob(lp, t, BLANK) for t in targets])


def test_empty_target_is_the_path_of_blanks() -> None:
    lp = _lp(np.random.default_rng(3), 6, 5)
    _same(_many(lp, [[], [1], []]), [ctc_logprob(lp, t, BLANK) for t in ([], [1], [])])


def test_target_longer_than_frames_is_impossible() -> None:
    lp = _lp(np.random.default_rng(4), 3, 5)
    got = _many(lp, [[1, 2, 3, 4], [1, 2], [1, 1, 1]])
    assert got[0] == -math.inf
    assert got[2] == -math.inf  # три одинаковых подряд — нужно 5 кадров
    _same(got, [ctc_logprob(lp, t, BLANK) for t in ([1, 2, 3, 4], [1, 2], [1, 1, 1])])


def test_no_frames_gives_minus_inf_for_every_target() -> None:
    empty = np.zeros((0, 5), dtype=np.float64)
    assert _many(empty, [[1], [], [1, 2]]) == [-math.inf] * 3


def test_no_targets_gives_an_empty_list() -> None:
    assert _many(_lp(np.random.default_rng(5), 4, 5), []) == []


def test_batch_of_2000_variants_fits_the_budget() -> None:
    """2000 вариантов длины около 40 на записи 600 × 80 (≈ 12 с звука) — быстрее бюджета.
    Лучшее из двух запусков: первый может прогревать numpy."""
    rng = np.random.default_rng(6)
    lp = _lp(rng, 600, 80)
    targets = [list(rng.integers(1, 80, size=int(n))) for n in rng.integers(36, 45, size=2000)]
    best = math.inf
    for _ in range(2):
        started = time.perf_counter()
        got = _many(lp, targets)
        best = min(best, time.perf_counter() - started)
    assert len(got) == len(targets)
    assert best < BUDGET_S, f"{best:.2f} с на 2000 вариантов"
    for i in (0, 999, 1999):  # и балл тот же
        _same([got[i]], [ctc_logprob(lp, targets[i], BLANK)])
