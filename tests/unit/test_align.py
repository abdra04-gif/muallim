"""Границы аятов в записи суры — CTC Viterbi по склейке верных чтений (FR-70 ч. 7, FR-57;
ADR-0088 «Суры» п. 2; прототип `docs/research/phase3/sura_align_check.py::viterbi_starts`,
замер PHASE_3 §11.8k).

Предложенный интерфейс (принимает человек):
``align.ayah_starts(lp, targets, blank, *, optional=0) -> list[int | None]`` — кадр, где звучит
первый звук каждой цели. ``targets`` — звуки модели (номера) подряд: [истиаза] [басмала] аят 1 …
аят N. Любая цель может не прозвучать (ветви графа, обход её состояний): необязательное начало,
пропущенный аят в середине (главная ошибка «наизусть») или аяты после конца чтения — для неё
``None``. ``optional`` — сколько первых целей — необязательные начала (истиаза, басмала); по
ним адаптер отличает «начало не прочитано» от «пропущен аят».

Логиты — подставные: в каждом кадре один символ с вероятностью 0,98, остальное поровну.
numpy ставится с моделью (extra ``ml``); без него тесты пропускаются.
"""

from collections.abc import Sequence
from typing import Any

import pytest

np = pytest.importorskip("numpy")

BLANK = 0
SYMBOLS = 16
A1, A2, A3 = [1, 2, 3], [4, 5, 6, 4], [7, 2, 8]  # аяты: у A1 и A3 общий звук, у A2 повтор
ISTIADHA, BASMALA = [9, 10, 11], [12, 13, 1]  # необязательные начала
LEAD, PAUSE, TAIL = 5, 6, 8  # тишина в начале, между целями и в конце (кадры)


def _speak(spoken: Sequence[Sequence[int]], *, tail: int = TAIL) -> tuple[Any, list[int]]:
    """Логиты «прочитанного»: каждый звук — 2 кадра, между звуками 1 «пустой», между целями
    пауза. Ответ — (логиты, кадр первого звука каждой прочитанной цели)."""
    frames: list[int] = [BLANK] * LEAD
    starts: list[int] = []
    for target in spoken:
        starts.append(len(frames))
        for k, sym in enumerate(target):
            frames += [sym, sym]
            if k + 1 < len(target):
                frames.append(BLANK)
        frames += [BLANK] * PAUSE
    frames += [BLANK] * tail
    p = np.full((len(frames), SYMBOLS), 0.02 / (SYMBOLS - 1))
    p[np.arange(len(frames)), frames] = 0.98
    return np.log(p), starts


def ayah_starts(lp: Any, targets: Sequence[Sequence[int]], blank: int, **kw: int) -> Any:
    """``align.ayah_starts``; модуль импортируется здесь, чтобы его отсутствие (красная фаза)
    роняло эти тесты, а не сбор всего набора."""
    from muallim.infrastructure.asr import align  # noqa: PLC0415

    return align.ayah_starts(lp, targets, blank, **kw)


def _close(got: Sequence[int | None], expected: Sequence[int | None]) -> None:
    assert len(got) == len(expected)
    for g, e in zip(got, expected, strict=True):
        if e is None:
            assert g is None
        else:
            assert g is not None and abs(g - e) <= 1, (got, expected)


def test_known_ayah_starts_are_found_to_one_frame() -> None:
    lp, starts = _speak([A1, A2, A3])
    _close(ayah_starts(lp, [A1, A2, A3], BLANK), starts)


def test_long_pause_between_ayahs_does_not_shift_the_next_start() -> None:
    lp, _ = _speak([A1])
    lp2, starts2 = _speak([A2], tail=0)
    whole = np.concatenate([lp, lp2])
    expected = [LEAD, len(lp) + starts2[0]]
    _close(ayah_starts(whole, [A1, A2], BLANK), expected)


def test_istiadha_and_basmala_heard_are_found_before_the_sura() -> None:
    lp, starts = _speak([ISTIADHA, BASMALA, A1, A2, A3])
    got = ayah_starts(lp, [ISTIADHA, BASMALA, A1, A2, A3], BLANK, optional=2)
    _close(got, starts)


def test_openings_not_heard_are_none_and_ayahs_are_still_found() -> None:
    lp, starts = _speak([A1, A2, A3])
    got = ayah_starts(lp, [ISTIADHA, BASMALA, A1, A2, A3], BLANK, optional=2)
    _close(got, [None, None, *starts])


def test_basmala_without_istiadha_is_found() -> None:
    lp, starts = _speak([BASMALA, A1, A2, A3])
    got = ayah_starts(lp, [ISTIADHA, BASMALA, A1, A2, A3], BLANK, optional=2)
    _close(got, [None, *starts])


def test_istiadha_without_basmala_is_found() -> None:
    lp, starts = _speak([ISTIADHA, A1, A2, A3])
    got = ayah_starts(lp, [ISTIADHA, BASMALA, A1, A2, A3], BLANK, optional=2)
    _close(got, [starts[0], None, *starts[1:]])


def test_reading_cut_short_leaves_the_last_ayahs_none() -> None:
    """Дочитал до аята 2 и замолчал: аят 3 не прозвучал — ``None``, без исключения."""
    lp, starts = _speak([A1, A2], tail=20)
    _close(ayah_starts(lp, [A1, A2, A3], BLANK), [*starts, None])


def test_skipped_middle_ayah_is_none_and_neighbours_are_found() -> None:
    """Пропущен аят 2 (наизусть забыл): для него ``None``, границы аятов 1 и 3 верны."""
    lp, starts = _speak([A1, A3])
    _close(ayah_starts(lp, [A1, A2, A3], BLANK), [starts[0], None, starts[1]])


def test_skipped_ayah_after_openings_is_found() -> None:
    lp, starts = _speak([ISTIADHA, BASMALA, A1, A3])
    got = ayah_starts(lp, [ISTIADHA, BASMALA, A1, A2, A3], BLANK, optional=2)
    _close(got, [*starts[:3], None, starts[3]])


def test_empty_target_does_not_break_skipping_the_one_before() -> None:
    """Пустая цель (аят без звуков модели) среди аятов: пропуск цели перед ней по-прежнему
    возможен — цели [1], [2], [], [3] при непрочитанной [2] дают кадр первой, None, None и кадр
    четвёртой, а не «ничего не найдено»."""
    lp, starts = _speak([[1], [3]])
    _close(ayah_starts(lp, [[1], [2], [], [3]], BLANK), [starts[0], None, None, starts[1]])


def test_silence_alone_gives_no_ayah() -> None:
    lp, _ = _speak([], tail=30)
    assert ayah_starts(lp, [A1, A2, A3], BLANK) == [None, None, None]


def test_starts_go_in_order() -> None:
    lp, _ = _speak([ISTIADHA, BASMALA, A1, A2, A3])
    got = ayah_starts(lp, [ISTIADHA, BASMALA, A1, A2, A3], BLANK, optional=2)
    found = [g for g in got if g is not None]
    assert found == sorted(found) and len(set(found)) == len(found)
