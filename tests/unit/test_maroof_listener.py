"""Слушатель MostafaMaroof: порт ``CardListener`` и адаптер без модели (FR-70 п. 1–4, 9;
ADR-0088 п. 1, 2, 9; ADR-0087 п. 4).

Модель не грузится: ``maroof._load`` подменён и отдаёт маленькую матрицу логарифмов вероятностей
(кадры × символы) и словарь; ffmpeg (``maroof.decode_to_pcm``) и фонетизатор бота
(``maroof._references``) — тоже подмены. Эталоны — из `tests/fixtures/maroof_cards.json`
(L010-04 «بُ»).
numpy ставится с моделью (extra ``ml``); без него тесты пропускаются.
"""

import math
import re
from collections.abc import Mapping
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from muallim.application.ports.recognition import (  # noqa: E402
    CardListener,
    Listening,
    RecognitionError,
)
from muallim.domain.card_check import decide  # noqa: E402
from muallim.domain.policy import CardPolicy  # noqa: E402
from muallim.infrastructure.asr import maroof, maroof_script  # noqa: E402
from muallim.infrastructure.asr.ctc import ctc_logprob, prepare  # noqa: E402
from muallim.infrastructure.asr.maroof import MODEL_REVISION, MaroofListener  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402

VOCAB: Mapping[str, int] = {
    "[PAD]": 0, "|": 1, "sil": 2, "b": 3,
    "a": 4, "A": 5, "aa": 6, "AA": 7,
    "i": 8, "I": 9, "ii": 10, "II": 11,
    "u": 12, "U": 13, "uu": 14, "UU": 15,
}  # fmt: skip
BU = ("بُ", "بڇ")  # «بُ» L010-04: слитно и с остановкой
SAMPLES = 16_000  # 1 с при 16 кГц


def _frames(*peaks: str) -> Any:
    """Кадр на каждый символ: у него вероятность 0,5, остальное поровну; у долгой «uu» — доля."""
    p = np.full((len(peaks), len(VOCAB)), 0.5 / (len(VOCAB) - 1))
    for f, sym in enumerate(peaks):
        p[f, VOCAB[sym]] = 0.5
    p[:, VOCAB["uu"]] += 0.05
    p = p / p.sum(axis=1, keepdims=True)
    return np.log(p)


LP = _frames("b", "b", "[PAD]", "u")


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    def load(*args: Any, **kwargs: Any) -> tuple[Any, Mapping[str, int]]:
        calls.append((*args, *kwargs.values()))
        return (lambda wave: LP), VOCAB

    async def decode(audio: bytes, *args: Any, **kwargs: Any) -> bytes:
        return bytes(np.zeros(SAMPLES, dtype=np.float32).tobytes())

    monkeypatch.setattr(maroof, "_load", load)
    monkeypatch.setattr(maroof, "decode_to_pcm", decode)
    monkeypatch.setattr(
        maroof, "_references", lambda text: (None, (("wasl", BU[0]), ("waqf", BU[1])))
    )
    return calls


def _expected(variant: str, *, long_is_short: bool) -> float:
    lp = prepare(LP, VOCAB, long_is_short=long_is_short)
    return ctc_logprob(lp, [VOCAB[s] for s in to_maroof(variant)], VOCAB["[PAD]"])


async def test_listening_gives_bot_references_duration_and_version(loads: list[Any]) -> None:
    listener = MaroofListener()
    listening = await listener.listen(b"ogg", "بُ", long_is_short=False)
    assert isinstance(listening, Listening)
    assert dict(listening.references) == {"wasl": BU[0], "waqf": BU[1]}
    assert listening.audio_duration_ms == 1000
    assert listening.model_version == listener.model_version


@pytest.mark.parametrize("long_is_short", [False, True])
async def test_score_is_ctc_logprob_of_prepared_output(
    loads: list[Any], long_is_short: bool
) -> None:
    """score(вариант) = log P(звуки варианта | запись) после ``prepare`` с флагом урока."""
    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=long_is_short)
    for variant in ("بُ", "بَ", "ب", "بُۥۥ"):
        assert listening.score(variant) == pytest.approx(
            _expected(variant, long_is_short=long_is_short)
        )


async def test_long_is_short_flag_reaches_prepare(loads: list[Any]) -> None:
    """Уроки 3–30: долгая = короткая. С флагом и без — разные баллы одного варианта."""
    listener = MaroofListener()
    plain = await listener.listen(b"ogg", "بُ", long_is_short=False)
    folded = await listener.listen(b"ogg", "بُ", long_is_short=True)
    assert plain.score("بُ") != pytest.approx(folded.score("بُ"))


async def test_raw_is_greedy_decoding_without_hint(loads: list[Any]) -> None:
    """Что модель услышала без подсказки (учителю, FR-70 п. 9): повторы и «пустые» схлопнуты."""
    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    assert listening.raw.split() == ["b", "u"]


async def test_sounds_of_a_variant_are_model_sounds(loads: list[Any]) -> None:
    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    assert tuple(listening.sounds("بڇ")) == tuple(listening.sounds("ب")) == ("b",)


async def test_decision_on_listening_is_json_safe(loads: list[Any]) -> None:
    import dataclasses  # noqa: PLC0415
    import json  # noqa: PLC0415

    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    d = decide(
        [BU[0]], listening.score, CardPolicy(), separate_syllables=True, sounds=listening.sounds
    )
    json.dumps(dataclasses.asdict(d), allow_nan=False)


async def test_model_is_loaded_once(loads: list[Any]) -> None:
    listener = MaroofListener()
    await listener.listen(b"ogg", "بُ", long_is_short=False)
    await listener.listen(b"ogg", "بُ", long_is_short=False)
    assert len(loads) == 1


def test_revision_is_pinned_to_a_commit() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", MODEL_REVISION)


def test_model_version_has_pinned_revision_and_script_version() -> None:
    from sqlalchemy import String  # noqa: PLC0415

    from muallim.infrastructure.db.tables import attempts  # noqa: PLC0415

    version = MaroofListener().model_version
    assert version.startswith(f"wav2vec2-arabic-phoneme-asr@{MODEL_REVISION[:7]}")
    assert f"to_maroof={maroof_script.VERSION}" in version
    column = attempts.c.model_version.type
    assert isinstance(column, String) and column.length is not None
    assert len(version) <= column.length


def test_maroof_listener_is_a_card_listener() -> None:
    listener: CardListener = MaroofListener()
    assert callable(listener.listen)


# ---------- сбои (ADR-0088 п. 9, QAS-04): RecognitionError, на Muaalem молча не переходим ----
async def test_decode_failure_keeps_its_stage(
    loads: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(audio: bytes, *args: Any, **kwargs: Any) -> bytes:
        raise RecognitionError("ffmpeg", stage="decode")

    monkeypatch.setattr(maroof, "decode_to_pcm", broken)
    with pytest.raises(RecognitionError) as error:
        await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    assert error.value.stage == "decode"


async def test_model_failure_is_a_recognition_error(
    loads: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(wave: Any) -> Any:
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(maroof, "_load", lambda *a, **k: (crash, VOCAB))
    with pytest.raises(RecognitionError) as error:
        await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    assert error.value.stage == "model"


async def test_phonetizer_failure_is_a_recognition_error(
    loads: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(text: str) -> Any:
        raise KeyError("x")

    monkeypatch.setattr(maroof, "_references", broken)
    with pytest.raises(RecognitionError):
        await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)


async def test_reference_without_model_sounds_is_a_recognition_error(
    loads: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Перевод эталона в звуки модели не удался (незнакомый знак) — сбой сразу, а не на score."""
    monkeypatch.setattr(maroof, "_references", lambda text: (None, (("wasl", "بx"), ("waqf", "ب"))))
    with pytest.raises(RecognitionError):
        await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)


# ---------- заглушка для make run-stub ----------
async def test_stub_listener_passes_every_card() -> None:
    from muallim.infrastructure.asr.stub import StubCardListener  # noqa: PLC0415

    for text in ("بُ", "رَ رِ رُ", "رَبَّ"):
        listening = await StubCardListener().listen(b"", text, long_is_short=False)
        assert listening.model_version == "stub"
        accepted = [reading for _, reading in listening.references]
        d = decide(accepted, listening.score, CardPolicy(), separate_syllables=False)
        assert d.outcome == "passed", text
        assert not math.isnan(d.margin or 0.0)


# ---------- баллы многих вариантов одним проходом (батч-CTC, блокер ревью) ----------
# Предложено: ``Listening.score_many(варианты) -> Sequence[float]`` (необязательное поле порта,
# у заглушек может не быть); у MostafaMaroof — через ``ctc.ctc_logprob_many``.
MANY = ("بُ", "بَ", "ب", "بُۥۥ", "بِ", "زُ", "بڇ", "بُ", "بx")  # повтор и вариант без звуков


@pytest.mark.parametrize("long_is_short", [False, True])
async def test_score_many_equals_score_of_each_variant(
    loads: list[Any], long_is_short: bool
) -> None:
    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=long_is_short)
    assert listening.score_many is not None
    got = list(listening.score_many(MANY))
    expected = [listening.score(v) for v in MANY]
    assert len(got) == len(expected)
    for g, e in zip(got, expected, strict=True):
        assert g == e or g == pytest.approx(e, rel=0, abs=1e-9), (g, e)
    assert got[-1] == -math.inf  # таких звуков у модели нет — вариант невозможен


async def test_score_many_runs_one_batch_ctc_pass(
    loads: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from muallim.infrastructure.asr import ctc  # noqa: PLC0415

    calls: list[int] = []
    many = ctc.ctc_logprob_many

    def spy(lp: Any, targets: Any, blank: int) -> Any:
        calls.append(len(targets))
        return many(lp, targets, blank)

    monkeypatch.setattr(maroof, "ctc_logprob_many", spy)
    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    assert listening.score_many is not None
    listening.score_many(MANY)
    assert len(calls) == 1


async def test_decision_with_score_many_is_the_same(loads: list[Any]) -> None:
    listening = await MaroofListener().listen(b"ogg", "بُ", long_is_short=False)
    kwargs: dict[str, Any] = {"separate_syllables": True, "sounds": listening.sounds}
    one = decide([BU[0]], listening.score, CardPolicy(), **kwargs)
    many = decide([BU[0]], listening.score, CardPolicy(), score_many=listening.score_many, **kwargs)
    assert many.outcome == one.outcome and many.winner == one.winner
    assert many.margin == pytest.approx(one.margin, abs=1e-9)
    assert many.margin_other == pytest.approx(one.margin_other, abs=1e-9)
