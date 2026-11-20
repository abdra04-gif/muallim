"""Границы аятов в записи суры: CTC Viterbi по склейке верных чтений (FR-70 ч. 7, ADR-0088 «Суры»).

Прототип — `docs/research/phase3/sura_align_check.py::viterbi_starts`, замер PHASE_3 §11.8k.
В отличие от прототипа любая цель может не прозвучать: из «пустого» перед целью есть переход сразу
в «пустой» после неё (необязательное начало, пропущенный аят, аяты после конца чтения).
numpy ставится с моделью (extra ``ml``).
"""

from collections.abc import Sequence
from typing import Any

import numpy as np


def ayah_starts(
    lp: Any, targets: Sequence[Sequence[int]], blank: int, *, optional: int = 0
) -> list[int | None]:
    """Кадр первого звука каждой цели; ``None`` — цель не прозвучала.

    ``targets`` — звуки модели (номера) подряд: [истиаза] [басмала] аят 1 … аят N. Пропустить
    можно любую цель; ``optional`` — сколько первых целей — необязательные начала: на граф не
    влияет, им пользуется вызывающий (отличить «начало не прочитано» от «пропущен аят»).
    """
    del optional  # граф для всех целей один: пропустить можно любую
    frames = lp.shape[0]
    if frames == 0 or not targets:
        return [None] * len(targets)
    ext = [blank]
    gaps = [0]  # «пустой» перед целью k — gaps[k], после неё — gaps[k + 1]
    owner = [-1]  # чья это буква (номер цели); -1 — «пустой»
    firsts: list[int] = []
    lasts: list[int] = []
    for k, target in enumerate(targets):
        firsts.append(len(ext))
        for token in target:
            ext += [token, blank]
            owner += [k, -1]
        lasts.append(len(ext) - 2 if target else -1)
        gaps.append(len(ext) - 1)
    states = np.array(ext)
    n = len(ext)
    tokens = np.array(owner) >= 0
    skip = np.zeros(n, dtype=bool)
    skip[2:] = tokens[2:] & (states[2:] != states[:-2])
    jump = np.full(n, -1)  # обход цели: «пустой» перед ней → «пустой» после
    for k in range(len(targets)):
        if gaps[k + 1] != gaps[k]:  # у пустой цели «до» и «после» — одно состояние
            jump[gaps[k + 1]] = gaps[k]
    has_jump = jump >= 0

    emit = np.asarray(lp)[:, states]  # кадры × состояния
    delta = np.full(n, -np.inf)
    start = [*gaps, *(f for f, t in zip(firsts, targets, strict=True) if t)]
    delta[start] = emit[0, start]
    back = np.zeros((frames, n), dtype=np.int32)
    idx = np.arange(n)
    for f in range(1, frames):
        cand = np.full((4, n), -np.inf)
        cand[0] = delta
        cand[1, 1:] = delta[:-1]
        cand[2, 2:] = np.where(skip[2:], delta[:-2], -np.inf)
        cand[3] = np.where(has_jump, delta[jump], -np.inf)
        best = cand.argmax(axis=0)
        source = np.choose(best, [idx, idx - 1, idx - 2, jump])
        back[f] = source
        delta = cand[best, idx] + emit[f]
    ends = [*gaps, *(e for e in lasts if e >= 0)]
    state = max(ends, key=lambda s: delta[s])
    found: list[int | None] = [None] * len(targets)
    for f in range(frames - 1, -1, -1):
        if owner[state] >= 0:
            found[owner[state]] = f
        state = int(back[f, state]) if f else state
    return found
