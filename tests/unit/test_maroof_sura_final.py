"""Сура на MostafaMaroof — заключительные проверки FR-70 (ч. 7; FR-57; ADR-0088 «Суры»,
PHASE_3 §11.8k): стыки окон длинной записи, сбой внутри проверки, одна модель на два потока.

Модель не грузится: подставная модель и запись с номером кадра в каждом отсчёте — из
`test_maroof_sura.py` (там же эталоны из `tests/fixtures/maroof_cards.json`).
numpy ставится с моделью (extra ``ml``); без него тесты пропускаются.
"""

import asyncio
import threading
import time
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from muallim.application.ports.recognition import RecognitionError  # noqa: E402
from muallim.infrastructure.asr import align, maroof  # noqa: E402
from muallim.infrastructure.asr.maroof import MaroofListener  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402
from tests.unit.test_maroof_sura import (  # noqa: E402
    AYAHS,
    BY_TEXT,
    FRAME_MS,
    HOP,
    OPENING,
    PREAMBLE,
    VOCAB,
    Model,
    _listen,
    _near_ms,
    _speak,
    model,
)

__all__ = ["model"]  # фикстура из test_maroof_sura


def _wav2vec2_frames(samples: int) -> int:
    """Сколько кадров даёт wav2vec2 на ``samples`` отсчётов: окно 400, шаг 320."""
    return (samples - 400) // HOP + 1


# ---------- 1. стыки окон: ни одного потерянного кадра ----------
async def test_windows_glue_to_as_many_frames_as_one_call_on_the_whole_recording(
    model: Model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Модель считает кадры как wav2vec2 (``(N − 400) // 320 + 1``): склейка окон 30 с с
    перекрытием 4 с даёт ровно столько кадров, сколько один вызов на всю запись — на шве кадр не
    теряется, а аят в конце записи (192 с) найден там же, где прочитан."""

    def forward(wave: Any) -> Any:
        idx = np.asarray(wave[::HOP]).astype(int)[: _wav2vec2_frames(len(wave))]
        model.calls.append((int(idx[0]), len(idx)))
        return model.lp[np.clip(idx, 0, len(model.lp) - 1)]

    monkeypatch.setattr(model, "forward", forward)
    glued: list[int] = []
    original = align.ayah_starts

    def spy(lp: Any, *args: Any, **kwargs: Any) -> Any:
        glued.append(lp.shape[0])
        return original(lp, *args, **kwargs)

    monkeypatch.setattr(align, "ayah_starts", spy)
    frames = 200 * 1000 // FRAME_MS
    lp, starts = _speak([t for _, _, t in AYAHS], at=[10, 4000, 9600], total=frames)
    sura = await _listen(model, lp)
    assert len(model.calls) > 1  # запись длиннее 180 с — окнами
    assert glued == [_wav2vec2_frames(frames * HOP)]
    for ayah, start in zip(sura.ayahs, starts, strict=True):
        _near_ms(ayah.span_ms, start, slack=2)


# ---------- 2. сбой внутри проверки суры — RecognitionError(stage="model") ----------
async def test_sound_missing_from_the_model_vocabulary_is_a_model_error(
    model: Model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Звук эталона, которого нет в словаре модели (``KeyError`` внутри разбора суры), — не
    необработанное исключение, а ``RecognitionError`` с этапом ``model``."""
    sound = to_maroof(BY_TEXT[AYAHS[0][2]]["waqf"])[0]
    vocab = {s: i for s, i in VOCAB.items() if s != sound}
    monkeypatch.setattr(maroof, "_load", lambda *a, **k: (model.forward, vocab))
    lp, _ = _speak([t for _, _, t in AYAHS])
    model.lp = lp
    with pytest.raises(RecognitionError) as error:
        await MaroofListener().listen_sura(b"ogg", AYAHS, OPENING, PREAMBLE, long_is_short=False)
    assert error.value.stage == "model"


async def test_numeric_failure_while_aligning_is_a_model_error(
    model: Model, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("operands could not be broadcast together")

    monkeypatch.setattr(align, "ayah_starts", broken)
    lp, _ = _speak([t for _, _, t in AYAHS])
    with pytest.raises(RecognitionError) as error:
        await _listen(model, lp)
    assert error.value.stage == "model"


# ---------- 4. замок на модель: forward не идёт в двух потоках сразу ----------
async def test_two_recordings_do_not_run_the_model_at_the_same_time(
    model: Model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два голосовых одновременно (карточка и сура, по потоку на каждое): вызовы модели идут
    по очереди — одна модель в памяти не рассчитана на параллельные вызовы."""
    guard = threading.Lock()
    active = [0, 0]  # сейчас, максимум

    def forward(wave: Any) -> Any:
        with guard:
            active[0] += 1
            active[1] = max(active[1], active[0])
        time.sleep(0.05)
        with guard:
            active[0] -= 1
        idx = np.clip(np.asarray(wave[::HOP]).astype(int), 0, len(model.lp) - 1)
        return model.lp[idx]

    monkeypatch.setattr(model, "forward", forward)
    lp, _ = _speak([t for _, _, t in AYAHS])
    model.lp = lp
    listener = MaroofListener()
    await asyncio.gather(
        listener.listen_sura(b"ogg", AYAHS, OPENING, PREAMBLE, long_is_short=False),
        listener.listen(b"ogg", AYAHS[1][2], long_is_short=False),
        listener.listen(b"ogg", AYAHS[2][2], long_is_short=False),
    )
    assert active[1] == 1
