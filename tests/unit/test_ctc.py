"""Балл варианта по выходу модели: прямой алгоритм CTC и подготовка выхода (FR-70 п. 2–4, ADR-0088).

Сверено с прототипом `docs/research/phase3/words_check.py::ctc_logprob` и
`docs/research/phase3/to_maroof.py::prepare`. Матрицы маленькие, ответ считается вручную.
numpy ставится с моделью (extra ``ml``); без него тесты пропускаются.
"""

import math
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from muallim.infrastructure.asr.ctc import ctc_logprob, prepare  # noqa: E402

BLANK = 0


def _lp(probs: list[list[float]]) -> Any:
    return np.log(np.array(probs, dtype=np.float64))


# три символа: 0 — пустой, 1 и 2 — звуки
P = [[0.2, 0.5, 0.3], [0.1, 0.6, 0.3], [0.4, 0.4, 0.2]]


def test_one_frame_one_symbol_is_its_probability() -> None:
    assert ctc_logprob(_lp(P[:1]), [1], BLANK) == pytest.approx(math.log(0.5))


def test_two_frames_sum_every_path_of_the_symbol() -> None:
    # пути: 1 1, 0 1, 1 0
    expected = 0.5 * 0.6 + 0.2 * 0.6 + 0.5 * 0.1
    assert ctc_logprob(_lp(P[:2]), [1], BLANK) == pytest.approx(math.log(expected))


def test_two_different_symbols_in_two_frames_have_one_path() -> None:
    assert ctc_logprob(_lp(P[:2]), [1, 2], BLANK) == pytest.approx(math.log(0.5 * 0.3))


def test_repeated_symbol_needs_a_blank_between() -> None:
    assert ctc_logprob(_lp(P[:2]), [1, 1], BLANK) == -math.inf
    # три кадра: единственный путь 1 0 1
    assert ctc_logprob(_lp(P), [1, 1], BLANK) == pytest.approx(math.log(0.5 * 0.1 * 0.4))


def test_target_longer_than_frames_is_impossible() -> None:
    assert ctc_logprob(_lp(P[:1]), [1, 2], BLANK) == -math.inf


def test_three_frames_match_brute_force_over_all_paths() -> None:
    target = [1, 2]
    total = 0.0
    for a in range(3):
        for b in range(3):
            for c in range(3):
                collapsed = [
                    s for i, s in enumerate((a, b, c)) if s and (i == 0 or s != (a, b, c)[i - 1])
                ]
                if collapsed == target:
                    total += P[0][a] * P[1][b] * P[2][c]
    assert ctc_logprob(_lp(P), target, BLANK) == pytest.approx(math.log(total))


VOCAB = {
    "[PAD]": 0, "|": 1, "sil": 2, "b": 3,
    "a": 4, "A": 5, "aa": 6, "AA": 7,
    "i": 8, "I": 9, "ii": 10, "II": 11,
    "u": 12, "U": 13, "uu": 14, "UU": 15,
}  # fmt: skip


def _frame() -> Any:
    rng = np.random.default_rng(0)
    p = rng.random((2, len(VOCAB)))
    return np.log(p / p.sum(axis=1, keepdims=True))


def _sum(lp: Any, *names: str) -> Any:
    return np.logaddexp.reduce(lp[:, [VOCAB[n] for n in names]], axis=1)


def test_pause_and_silence_count_as_blank() -> None:
    lp = _frame()
    out = prepare(lp, VOCAB, long_is_short=False)
    assert out[:, VOCAB["[PAD]"]] == pytest.approx(_sum(lp, "[PAD]", "|", "sil"))


def test_heavy_vowel_counts_as_plain() -> None:
    lp = _frame()
    out = prepare(lp, VOCAB, long_is_short=False)
    for plain in ("a", "i", "u", "aa", "ii", "uu"):
        assert out[:, VOCAB[plain]] == pytest.approx(_sum(lp, plain, plain.upper()))
    assert out[:, VOCAB["b"]] == pytest.approx(lp[:, VOCAB["b"]])


def test_long_is_short_folds_long_vowel_into_short_and_removes_long() -> None:
    lp = _frame()
    out = prepare(lp, VOCAB, long_is_short=True)
    for short in ("a", "i", "u"):
        long_ = short * 2
        expected = _sum(lp, short, short.upper(), long_, long_.upper())
        assert out[:, VOCAB[short]] == pytest.approx(expected)
        assert np.all(out[:, VOCAB[long_]] == -np.inf)


def test_prepare_does_not_change_model_output() -> None:
    lp = _frame()
    before = lp.copy()
    prepare(lp, VOCAB, long_is_short=True)
    assert np.array_equal(lp, before)


def test_no_frames_is_impossible_not_an_error() -> None:
    """Пустая запись (0 кадров): ничего не прочитано — −inf, а не IndexError (ревью части 1)."""
    empty = np.zeros((0, 3), dtype=np.float64)
    assert ctc_logprob(empty, [1], BLANK) == -math.inf
