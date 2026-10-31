"""Длинная запись — куски 6–10 с в самой тихой точке (FR-57, ADR-0076).

Модель на 40 с звука одним проходом не уложилась в 8 ГБ памяти (замер 2026-10-30). Ученик читает
без остановки, поэтому режем не по паузам, а в самом тихом месте окна: на вдохе, между словами.
"""

from typing import Any, Final

FRAME_S: Final = 0.02  # шаг поиска тихого места — 20 мс
MIN_S: Final = 6.0
MAX_S: Final = 10.0
MIN_TAIL_S: Final = 0.5  # последний кусок не короче: модели нужен звук, а не крошка


def quiet_cuts(
    wave: Any, sample_rate: int, *, min_s: float = MIN_S, max_s: float = MAX_S
) -> list[tuple[int, int]]:
    """Границы кусков (начало, конец) в отсчётах: подряд, без пропусков, каждый ≤ ``max_s``,
    каждый, кроме последнего, ≥ ``min_s``."""
    total = len(wave)
    if total == 0:
        return []
    frame = max(int(FRAME_S * sample_rate), 1)
    lo, hi = int(min_s * sample_rate), int(max_s * sample_rate)
    tail = int(MIN_TAIL_S * sample_rate)
    cuts: list[tuple[int, int]] = []
    start = 0
    while total - start > hi:
        window = wave[start + lo : min(start + hi, total - tail)]
        frames = len(window) // frame
        energy = (window[: frames * frame].reshape(frames, frame) ** 2).mean(axis=1)
        cut = start + lo + int(energy.argmin()) * frame + frame // 2
        cuts.append((start, cut))
        start = cut
    cuts.append((start, total))
    return cuts
