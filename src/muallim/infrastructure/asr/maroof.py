"""Слушатель «вариантов карточки» на модели MostafaMaroof (FR-70, ADR-0088 п. 2, 9).

ffmpeg → wav2vec2 (MostafaMaroof) → `ctc.prepare` → log P(вариант | запись) по `ctc.ctc_logprob`.
Эталоны — фонетизатор бота (`phonetizer._references`), перевод в звуки модели —
`maroof_script.to_maroof`. Ревизия модели закреплена (QAS-09: пересчёт попытки той же моделью).
torch и transformers (extra ``ml``) импортируются лениво — только при загрузке модели.
"""

import asyncio
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

import numpy as np

from muallim.application.ports.recognition import CardListener, Listening, RecognitionError
from muallim.infrastructure.asr import maroof_script
from muallim.infrastructure.asr.ctc import ctc_logprob, ctc_logprob_many, prepare
from muallim.infrastructure.asr.maroof_script import to_maroof
from muallim.infrastructure.asr.phonetizer import _references
from muallim.infrastructure.audio.ffmpeg import SAMPLE_RATE, decode_to_pcm

MODEL_ID: Final = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
# Коммит модели на Hugging Face (проверено 2026-11-20); другая модель — новая ревизия здесь.
MODEL_REVISION = "0a32c641aaaeec6957e41a794add52e024e46b50"
_BLANK: Final = "[PAD]"
_LONG: Final = {"aa": "a", "ii": "i", "uu": "u"}

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


@dataclass
class MaroofListener(CardListener):
    device: str = "auto"  # auto | cpu | mps | cuda
    _forward: Forward | None = field(default=None, init=False, repr=False)
    _vocab: Mapping[str, int] = field(default_factory=dict, init=False, repr=False)

    @property
    def model_version(self) -> str:
        """Пишется в каждую попытку (≤ 128 знаков): модель, ревизия (7 знаков), версия перевода."""
        name = MODEL_ID.split("/")[1]
        return f"{name}@{MODEL_REVISION[:7]};to_maroof={maroof_script.VERSION}"

    def load(self) -> None:
        """Загрузить и прогреть модель при старте бота, а не на первом голосовом."""
        self._forward, self._vocab = _load(self.device)
        self._forward(np.zeros(SAMPLE_RATE, dtype=np.float32))  # первый вызов долгий

    async def listen(self, audio: bytes, text: str, *, long_is_short: bool) -> Listening:
        pcm = await decode_to_pcm(audio)
        wave = np.frombuffer(pcm, dtype=np.float32).copy()
        try:
            _, references = _references(text)
            for _, reading in references:
                to_maroof(reading)  # незнакомый знак — сбой сразу, а не на подсчёте баллов
        except Exception as error:  # фонетизатор бросает разные исключения
            raise RecognitionError(str(error), stage="reference") from error
        try:
            if self._forward is None:
                self.load()
            lp = await asyncio.to_thread(cast("Forward", self._forward), wave)
        except Exception as error:  # модель бросает разные исключения на плохом звуке
            raise RecognitionError(str(error), stage="model") from error
        vocab = self._vocab
        prepared = prepare(lp, vocab, long_is_short=long_is_short)
        blank = vocab[_BLANK]
        cache: dict[tuple[str, ...], float] = {}

        def score(variant: str) -> float:
            try:
                sounds = to_maroof(variant)
                ids = [vocab[s] for s in sounds]
            except (ValueError, KeyError):  # таких звуков у модели нет — вариант невозможен
                return -math.inf
            if sounds not in cache:
                cache[sounds] = ctc_logprob(prepared, ids, blank)
            return cache[sounds]

        def score_many(variants: Sequence[str]) -> list[float]:
            ids: dict[tuple[str, ...], list[int]] = {}
            keys: list[tuple[str, ...] | None] = []
            for variant in variants:
                try:
                    key = to_maroof(variant)
                    ids.setdefault(key, [vocab[s] for s in key])
                except (ValueError, KeyError):  # таких звуков у модели нет — невозможен
                    keys.append(None)
                    continue
                keys.append(key)
            new = [k for k in ids if k not in cache]
            cache.update(
                zip(new, ctc_logprob_many(prepared, [ids[k] for k in new], blank), strict=True)
            )
            return [-math.inf if k is None else cache[k] for k in keys]

        def sounds(variant: str) -> tuple[str, ...]:
            try:
                out = to_maroof(variant)
            except ValueError:
                return tuple(variant)
            # на уроках «долгая = короткая» протянутая гласная для проверки — та же короткая
            return tuple(_LONG.get(s, s) for s in out) if long_is_short else out

        return Listening(
            references=tuple(references),
            model_version=self.model_version,
            audio_duration_ms=round(len(wave) / SAMPLE_RATE * 1000),
            raw=_greedy(lp, vocab),
            score=score,
            sounds=sounds,
            score_many=score_many,
        )
