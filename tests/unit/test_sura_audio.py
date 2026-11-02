"""Длинная запись суры (FR-57, ADR-0076): куски 6–10 с в самой тихой точке и эталон по аятам.

Одним проходом 40 с звука не уложились в 8 ГБ памяти (замер 2026-10-30) — поэтому куски.
numpy и фонетизатор ставятся с моделью (extra ``ml``); без них тесты пропускаются.
"""

from itertools import pairwise
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from muallim.infrastructure.asr.chunks import quiet_cuts  # noqa: E402

SR = 16_000


def _noise(seconds: float, seed: int = 0) -> Any:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * SR)) * 0.3).astype(np.float32)


def _silence(seconds: float) -> Any:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_short_recording_is_one_piece() -> None:
    wave = _noise(5)
    assert quiet_cuts(wave, SR) == [(0, len(wave))]


def test_cut_goes_into_the_silence() -> None:
    wave = np.concatenate([_noise(8), _silence(0.3), _noise(12, seed=1)])
    cuts = quiet_cuts(wave, SR)
    first_end = cuts[0][1] / SR
    assert 8.0 <= first_end <= 8.3


def test_pieces_cover_everything_in_order_and_are_not_too_long() -> None:
    wave = _noise(47)  # без единой паузы — ученик читает без остановки
    cuts = quiet_cuts(wave, SR)
    assert cuts[0][0] == 0 and cuts[-1][1] == len(wave)
    assert all(a[1] == b[0] for a, b in pairwise(cuts))
    assert all(end - start <= 10 * SR for start, end in cuts)
    assert all(end - start >= 6 * SR for start, end in cuts[:-1])


def test_empty_recording_has_no_pieces() -> None:
    assert quiet_cuts(np.zeros(0, dtype=np.float32), SR) == []


# ---------- эталон суры по аятам ----------


def test_sura_reference_splits_ayahs_into_words() -> None:
    pytest.importorskip("quran_transcript")
    from muallim.infrastructure.asr.muaalem import _references, sura_reference  # noqa: PLC0415

    ayahs = [
        ("L099-02", 1, "وَٱلضُّحَىٰ"),
        ("L099-03", 2, "وَٱلَّيْلِ إِذَا سَجَىٰ"),
    ]
    refs = sura_reference(ayahs)
    assert [(r.item_id, r.number) for r in refs] == [("L099-02", 1), ("L099-03", 2)]
    assert len(refs[1].words) == 3  # три слова аята
    for (_, _, text), ref in zip(ayahs, refs, strict=True):
        waqf = dict(_references(text)[1])["waqf"]
        assert "".join(ref.words) == waqf  # каждый аят — с остановкой в конце


def test_wasl_ending_differs_only_when_stopping_changes_the_word() -> None:
    pytest.importorskip("quran_transcript")
    from muallim.infrastructure.asr.muaalem import sura_reference  # noqa: PLC0415

    (ref,) = sura_reference([("L123-03", 2, "ٱللَّهُ ٱلصَّمَدُ")])
    assert ref.wasl_last and ref.wasl_last != ref.words[-1]  # «ас-самад» / «ас-самаду»


def test_last_piece_is_not_a_crumb() -> None:
    """Ревью кода 2026-10-31: тишина у отметки 10 с давала последний кусок в 20 мс."""
    wave = np.concatenate([_noise(9.99), _silence(0.02), _noise(0.01, seed=1)])
    cuts = quiet_cuts(wave, SR)
    assert all(end - start >= SR // 2 for start, end in cuts)
    assert cuts[-1][1] == len(wave)
