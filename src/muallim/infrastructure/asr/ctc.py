"""Балл варианта по выходу модели CTC: log P(вариант | запись) (ADR-0088 п. 2).

Прототип — `docs/research/phase3/words_check.py::ctc_logprob` и `to_maroof.py::prepare`.
numpy ставится с моделью (extra ``ml``).
"""

import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

import numpy as np


def ctc_logprob(lp: Any, target: Sequence[int], blank: int) -> float:
    """log P(target | запись) по CTC — прямой алгоритм, векторно по состояниям.

    ``lp`` — логарифмы вероятностей, кадры × символы. Пустая цель — путь из одних «пустых».
    """
    if lp.shape[0] == 0:  # пустая запись: ничего не прочитано
        return -math.inf
    if not target:  # путь из одних «пустых»
        return float(np.sum(lp[:, blank]))
    ext = np.full(2 * len(target) + 1, blank)
    ext[1::2] = target
    n = len(ext)
    skip = np.zeros(n, dtype=bool)
    skip[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])
    alpha = np.full(n, -np.inf)
    alpha[0] = lp[0, ext[0]]
    alpha[1] = lp[0, ext[1]]
    for f in range(1, lp.shape[0]):
        a1 = np.concatenate(([-np.inf], alpha[:-1]))
        a2 = np.where(skip, np.concatenate(([-np.inf, -np.inf], alpha[:-2])), -np.inf)
        alpha = np.logaddexp(np.logaddexp(alpha, a1), a2) + lp[f, ext]
    return float(np.logaddexp(alpha[-1], alpha[-2]))


def ctc_logprob_many(lp: Any, targets: Sequence[Sequence[int]], blank: int) -> list[float]:
    """То же, что ``[ctc_logprob(lp, t, blank) for t in targets]``, но все варианты разом.

    Прямой алгоритм в вероятностях с нормировкой каждого кадра (логарифм нормировок копится
    отдельно) — без медленного ``logaddexp``. Цели дополняются «пустыми» справа: переходы идут
    только вправо, поэтому хвост не влияет на ответ. Вариант, который вышел невозможным, хотя по
    длине помещается (нормировка могла обнулить слишком малую долю), пересчитывается поштучно.
    """
    if not targets:
        return []
    frames = lp.shape[0]
    if frames == 0:
        return [-math.inf] * len(targets)
    lengths = np.array([2 * len(t) + 1 for t in targets])
    ext = np.full((len(targets), int(lengths.max())), blank)
    for i, t in enumerate(targets):
        ext[i, 1 : 2 * len(t) : 2] = t
    skip = np.zeros(ext.shape, dtype=bool)
    skip[:, 2:] = (ext[:, 2:] != blank) & (ext[:, 2:] != ext[:, :-2])
    p = np.exp(np.asarray(lp, dtype=np.float64))
    alpha = np.zeros(ext.shape)
    alpha[:, :2] = p[0][ext[:, :2]]
    log_scale = np.zeros(len(targets))

    def normalize(alpha: Any) -> Any:
        top = alpha.max(axis=1)
        top = np.where(top > 0, top, 1.0)
        log_scale[:] += np.log(top)
        return alpha / top[:, None]

    alpha = normalize(alpha)
    for f in range(1, frames):
        moved = alpha.copy()
        moved[:, 1:] += alpha[:, :-1]
        moved[:, 2:] += np.where(skip[:, 2:], alpha[:, :-2], 0.0)
        alpha = normalize(moved * p[f][ext])
    rows = np.arange(len(targets))
    end = alpha[rows, lengths - 1] + np.where(lengths > 1, alpha[rows, lengths - 2], 0.0)
    with np.errstate(divide="ignore"):
        out = (np.log(end) + log_scale).tolist()
    for i, t in enumerate(targets):
        needed = len(t) + sum(a == b for a, b in pairwise(t))
        if out[i] == -math.inf and needed <= frames:
            out[i] = ctc_logprob(lp, t, blank)
    return [float(x) for x in out]


def prepare(lp: Any, vocab: Mapping[str, int], *, long_is_short: bool) -> Any:
    """Выход модели для подсчёта баллов (копия, исходный не меняется).

    Пауза между словами и тишина — тоже «пустой» символ; твёрдая гласная (A — после ص ض ط ظ ق и
    خ غ в данных обучения) и простая (a) — один звук. ``long_is_short`` (уроки 3–30, ADR-0086 п. 4):
    протянутая гласная на слоге — не ошибка, долгая складывается с короткой и убирается.
    """
    out = np.array(lp, dtype=np.float64)
    blank = vocab["[PAD]"]
    out[:, blank] = np.logaddexp.reduce(out[:, [blank, vocab["|"], vocab["sil"]]], axis=1)
    for plain in ("a", "i", "u", "aa", "ii", "uu"):
        out[:, vocab[plain]] = np.logaddexp(out[:, vocab[plain]], out[:, vocab[plain.upper()]])
    if long_is_short:
        for short in ("a", "i", "u"):
            out[:, vocab[short]] = np.logaddexp(out[:, vocab[short]], out[:, vocab[short * 2]])
            out[:, vocab[short * 2]] = -np.inf
    return out
