"""Слушатель «вариантов карточки» на модели MostafaMaroof (FR-70, ADR-0088 п. 2, 9).

ffmpeg → wav2vec2 (MostafaMaroof) → `ctc.prepare` → log P(вариант | запись) по `ctc.ctc_logprob`.
Эталоны — фонетизатор бота (`phonetizer._references`), перевод в звуки модели —
`maroof_script.to_maroof`. Ревизия модели закреплена (QAS-09: пересчёт попытки той же моделью).
torch и transformers (extra ``ml``) импортируются лениво — только при загрузке модели.
"""

import asyncio
import json
import math
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

from muallim.application.ports.recognition import (
    AyahListening,
    CardListener,
    Listening,
    RecognitionError,
    SuraListener,
    SuraListening,
)
from muallim.infrastructure.asr import align, maroof_script
from muallim.infrastructure.asr.ctc import ctc_logprob, ctc_logprob_many, prepare
from muallim.infrastructure.asr.maroof_script import to_maroof
from muallim.infrastructure.asr.phonetizer import _references
from muallim.infrastructure.audio.ffmpeg import SAMPLE_RATE, decode_to_pcm

MODEL_ID: Final = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
# Коммит модели на Hugging Face (проверено 2026-11-20); другая модель — новая ревизия здесь.
MODEL_REVISION = "0a32c641aaaeec6957e41a794add52e024e46b50"
_BLANK: Final = "[PAD]"
_LONG: Final = {"aa": "a", "ii": "i", "uu": "u"}
# Сура (ADR-0088 «Суры», PHASE_3 §11.8k): до 3 мин — одним вызовом модели, длиннее — окнами
WHOLE_MAX_S: Final = 180
WINDOW_S: Final = 30
OVERLAP_S: Final = 4
_HOP: Final = 320  # отсчётов на кадр модели (20 мс при 16 кГц)
_BEFORE_FRAMES: Final = 5  # кадров тишины перед первым звуком аята (прототип, ``--before``)
_REHEAR_BEFORE: Final = SAMPLE_RATE * 15 // 100  # второй проход: 0,15 с перед аятом

Forward = Callable[[Any], Any]  # волна float32 16 кГц → логарифмы вероятностей, кадры × символы


def _load(device: str) -> tuple[Forward, Mapping[str, int]]:
    """Модель и её словарь с Hugging Face — на закреплённой ревизии."""
    import torch  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415
    from transformers.utils.hub import cached_file  # noqa: PLC0415

    if device == "auto":
        device = (
            "mps"
            if torch.backends.mps.is_available()
            else "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )
    model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID, revision=MODEL_REVISION).eval().to(device)
    # словарь — vocab.json той же ревизии (токенизатор модели новая transformers не читает)
    vocab_path = cached_file(MODEL_ID, "vocab.json", revision=MODEL_REVISION)
    vocab: dict[str, int] = json.loads(Path(str(vocab_path)).read_text(encoding="utf-8"))

    def forward(wave: Any) -> Any:
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)  # как при обучении модели
        with torch.inference_mode():
            logits = model(torch.from_numpy(norm).unsqueeze(0).to(device)).logits[0]
        return torch.log_softmax(logits.float(), -1).cpu().numpy()

    return forward, vocab


def _greedy(lp: Any, vocab: Mapping[str, int]) -> str:
    """Что модель услышала без подсказки: лучший символ кадра, повторы и «пустые» схлопнуты."""
    names = {i: s for s, i in vocab.items()}
    out: list[str] = []
    previous = -1
    for i in lp.argmax(axis=1).tolist():
        if i != previous and names.get(i) != _BLANK:
            out.append(names.get(i, "?"))
        previous = i
    return " ".join(out)


@dataclass(frozen=True, slots=True)
class _Scorer:
    """Баллы вариантов по выходу модели (уже после ``prepare``): поштучно и батчем."""

    prepared: Any
    vocab: Mapping[str, int]
    long_is_short: bool
    cache: dict[tuple[str, ...], float] = field(default_factory=dict)

    def score(self, variant: str) -> float:
        try:
            sounds = to_maroof(variant)
            ids = [self.vocab[s] for s in sounds]
        except (ValueError, KeyError):  # таких звуков у модели нет — вариант невозможен
            return -math.inf
        if sounds not in self.cache:
            self.cache[sounds] = ctc_logprob(self.prepared, ids, self.vocab[_BLANK])
        return self.cache[sounds]

    def score_many(self, variants: Sequence[str]) -> list[float]:
        ids: dict[tuple[str, ...], list[int]] = {}
        keys: list[tuple[str, ...] | None] = []
        for variant in variants:
            try:
                key = to_maroof(variant)
                ids.setdefault(key, [self.vocab[s] for s in key])
            except (ValueError, KeyError):  # таких звуков у модели нет — невозможен
                keys.append(None)
                continue
            keys.append(key)
        new = [k for k in ids if k not in self.cache]
        scored = ctc_logprob_many(self.prepared, [ids[k] for k in new], self.vocab[_BLANK])
        self.cache.update(zip(new, scored, strict=True))
        return [-math.inf if k is None else self.cache[k] for k in keys]

    def sounds(self, variant: str) -> tuple[str, ...]:
        try:
            out = to_maroof(variant)
        except ValueError:
            return tuple(variant)
        # на уроках «долгая = короткая» протянутая гласная для проверки — та же короткая
        return tuple(_LONG.get(s, s) for s in out) if self.long_is_short else out


def _readings(text: str) -> tuple[tuple[str, str], ...]:
    """Эталоны карточки в записи бота; незнакомый знак — сбой сразу, а не на подсчёте баллов."""
    _, references = _references(text)
    for _, reading in references:
        to_maroof(reading)
    return tuple(references)


def _unheard(variant: str) -> float:
    return -math.inf


def _unheard_many(variants: Sequence[str]) -> list[float]:
    return [-math.inf] * len(variants)


@dataclass
class MaroofListener(CardListener, SuraListener):
    device: str = "auto"  # auto | cpu | mps | cuda
    _forward: Forward | None = field(default=None, init=False, repr=False)
    _vocab: Mapping[str, int] = field(default_factory=dict, init=False, repr=False)
    # одна модель в памяти не рассчитана на параллельные вызовы из двух потоков
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def model_version(self) -> str:
        """Пишется в каждую попытку (≤ 128 знаков): модель, ревизия (7 знаков), версия перевода."""
        name = MODEL_ID.split("/")[1]
        return f"{name}@{MODEL_REVISION[:7]};to_maroof={maroof_script.VERSION}"

    def load(self) -> None:
        """Загрузить и прогреть модель при старте бота, а не на первом голосовом."""
        forward = self._ensure()
        forward(np.zeros(SAMPLE_RATE, dtype=np.float32))  # первый вызов долгий

    def _ensure(self) -> Forward:
        if self._forward is None:
            self._forward, self._vocab = _load(self.device)
        return self._forward

    async def _hear(self, wave: Any) -> Any:
        """Логиты записи (кадры × символы) не в потоке бота; сбой модели — ``RecognitionError``."""
        try:
            forward = self._ensure()
            return await asyncio.to_thread(self._locked, forward, wave)
        except Exception as error:  # модель бросает разные исключения на плохом звуке
            raise RecognitionError(str(error), stage="model") from error

    def _locked(self, forward: Forward, wave: Any) -> Any:
        with self._lock:
            return _windows(forward, wave)

    def _listening(
        self, lp: Any, references: tuple[tuple[str, str], ...], samples: int, long_is_short: bool
    ) -> Listening:
        prepared = prepare(lp, self._vocab, long_is_short=long_is_short)
        scorer = _Scorer(prepared, self._vocab, long_is_short)
        return Listening(
            references=references,
            model_version=self.model_version,
            audio_duration_ms=round(samples / SAMPLE_RATE * 1000),
            raw=_greedy(lp, self._vocab),
            score=scorer.score,
            sounds=scorer.sounds,
            score_many=scorer.score_many,
        )

    async def listen(self, audio: bytes, text: str, *, long_is_short: bool) -> Listening:
        pcm = await decode_to_pcm(audio)
        wave = np.frombuffer(pcm, dtype=np.float32).copy()
        try:
            references = _readings(text)
        except Exception as error:  # фонетизатор бросает разные исключения
            raise RecognitionError(str(error), stage="reference") from error
        lp = await self._hear(wave)
        return self._listening(lp, references, len(wave), long_is_short)

    async def listen_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str,
        preamble: str,
        *,
        long_is_short: bool,
    ) -> SuraListening:
        """Сура целиком (FR-70 ч. 7): логиты всей записи (длинная — окнами), границы аятов —
        Viterbi по склейке чтений с остановкой (`align.ayah_starts`), баллы аята — на его
        отрезке; второй проход (``rehear``) — по запросу сценария."""
        pcm = await decode_to_pcm(audio, max_seconds=None)  # сура — без ограничения длины
        wave = np.frombuffer(pcm, dtype=np.float32).copy()
        heads = [
            (name, text) for name, text in (("preamble", preamble), ("opening", opening)) if text
        ]
        try:
            head_refs = [_readings(text) for _, text in heads]
            ayah_refs = [_readings(text) for _, _, text in ayahs]
        except Exception as error:  # фонетизатор бросает разные исключения
            raise RecognitionError(str(error), stage="reference") from error
        lp = await self._hear(wave)
        sura = _Sura(wave, lp, tuple(ayahs), tuple(heads), (*head_refs, *ayah_refs))
        try:
            return await asyncio.to_thread(self._sura, sura, long_is_short)
        except Exception as error:  # звука нет в словаре, сбой numpy — тоже сбой модели
            raise RecognitionError(str(error), stage="model") from error

    def _sura(self, sura: "_Sura", long_is_short: bool) -> SuraListening:
        vocab = self._vocab
        prepared = prepare(sura.lp, vocab, long_is_short=long_is_short)
        frames = len(prepared)
        targets = [[vocab[s] for s in to_maroof(dict(refs)["waqf"])] for refs in sura.references]
        found = align.ayah_starts(prepared, targets, vocab[_BLANK], optional=len(sura.heads))
        samples = len(sura.wave)
        frame_samples = samples / frames if frames else 0.0
        starts = found[len(sura.heads) :]
        refs_of = sura.references[len(sura.heads) :]
        out = []
        for k, ((item_id, number, _), refs) in enumerate(zip(sura.ayahs, refs_of, strict=True)):
            start = starts[k]
            if start is None:
                out.append(AyahListening(
                    item_id, number, refs, "", _unheard, tuple, _unheard_many, None, None,
                ))  # fmt: skip
                continue
            # отрезок кончается на начале следующего аята: его первый звук исказил бы последний
            end = next((s for s in starts[k + 1 :] if s is not None), frames)
            seg = slice(max(0, start - _BEFORE_FRAMES), end)
            scorer = _Scorer(prepared[seg], vocab, long_is_short)
            a = max(0, round(start * frame_samples) - _REHEAR_BEFORE)
            b = round(end * frame_samples)
            span = (_ms(start * frame_samples), _ms(end * frame_samples))
            out.append(AyahListening(
                item_id, number, refs, _greedy(sura.lp[seg], vocab), scorer.score, scorer.sounds,
                scorer.score_many, span, self._rehear(sura.wave[a:b], refs, long_is_short),
            ))  # fmt: skip
        heard = zip(sura.heads, found, strict=False)
        return SuraListening(
            ayahs=tuple(out),
            prefix=tuple(name for (name, _), s in heard if s is not None),
            raw=_greedy(sura.lp, vocab),
            model_version=self.model_version,
            audio_duration_ms=_ms(samples),
        )

    def _rehear(
        self, piece: Any, references: tuple[tuple[str, str], ...], long_is_short: bool
    ) -> Callable[[], Awaitable[Listening]]:
        async def rehear() -> Listening:
            """Второй проход: аят, вырезанный из записи, модель слушает отдельно (§11.8k)."""
            lp = await self._hear(piece)
            return self._listening(lp, references, len(piece), long_is_short)

        return rehear


@dataclass(frozen=True, slots=True)
class _Sura:
    """Запись суры и её эталоны: начала (истиаза, басмала), затем аяты."""

    wave: Any
    lp: Any
    ayahs: tuple[tuple[str, int, str], ...]
    heads: tuple[tuple[str, str], ...]
    references: tuple[tuple[tuple[str, str], ...], ...]


def _ms(samples: float) -> int:
    return round(samples / SAMPLE_RATE * 1000)


def _windows(forward: Forward, wave: Any) -> Any:
    """Логиты всей записи: до ``WHOLE_MAX_S`` — одним вызовом; длиннее — окнами ``WINDOW_S`` с
    перекрытием ``OVERLAP_S``. Шов — середина перекрытия в отсчётах: кадр k записи — отсчёты от
    k·320, из каждого окна берутся кадры до шва, из следующего — от шва; кадров выходит столько
    же, сколько у одного вызова на всю запись (у wav2vec2 — ``(N − 400) // 320 + 1``)."""
    if len(wave) <= WHOLE_MAX_S * SAMPLE_RATE:
        return forward(wave)
    win, step = WINDOW_S * SAMPLE_RATE, (WINDOW_S - OVERLAP_S) * SAMPLE_RATE
    parts = []
    start, seam = 0, 0  # seam — кадр записи, с которого берём из этого окна
    while True:
        part = forward(wave[start : start + win])
        last = start + win >= len(wave)
        offset = start // _HOP  # первый кадр окна в кадрах записи (шаг окна кратен 320)
        end = len(part) if last else (start + step + OVERLAP_S * SAMPLE_RATE // 2) // _HOP - offset
        parts.append(part[seam - offset : end])
        if last:
            return np.concatenate(parts)
        seam = offset + end
        start += step
