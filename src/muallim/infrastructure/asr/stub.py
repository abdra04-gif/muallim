"""Заглушка распознавания: «слышит» ровно эталон. Чтобы запускать и проверять бота без модели.

Включается ASR_BACKEND=stub. В БД попытки помечаются model_version="stub" и в отчёты не идут.
"""

import math
from collections.abc import Sequence

from muallim.application.ports.recognition import (
    CardListener,
    Listening,
    PronunciationRecognizer,
    Recognition,
    RecognitionError,
    SuraRecognition,
    SuraRecognizer,
)
from muallim.domain.sura import AyahReference


class StubRecognizer(PronunciationRecognizer, SuraRecognizer):
    async def recognize(self, audio: bytes, text: str) -> Recognition:
        return Recognition(
            heard=text, references=(("waqf", text),), model_version="stub", audio_duration_ms=0
        )

    async def recognize_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str = "",
        preamble: str = "",
    ) -> SuraRecognition:
        """Сура «прочитана» идеально: слова эталона — слова текста."""
        refs = tuple(AyahReference(i, n, tuple(text.split())) for i, n, text in ayahs)
        heard = "".join(r.text for r in refs)
        return SuraRecognition(
            heard=heard,
            ayahs=refs,
            opening=tuple(opening.split()),
            preamble=tuple(preamble.split()),
            pauses=(),
            chunks=((0, 0, 0, len(heard)),),
            model_version="stub",
            audio_duration_ms=0,
        )


class StubCardListener(CardListener):
    """«Варианты карточки» без модели (``make run-stub``): верное чтение — сам текст карточки,
    его балл 0, у любого другого варианта −inf — каждая карточка засчитана."""

    async def listen(self, audio: bytes, text: str, *, long_is_short: bool) -> Listening:
        return Listening(
            references=(("waqf", text),),
            model_version="stub",
            audio_duration_ms=0,
            raw="",
            score=lambda variant: 0.0 if variant == text else -math.inf,
            sounds=tuple,
        )


class DisabledRecognizer(PronunciationRecognizer, SuraRecognizer):
    """Muaalem выключена (``CHECKER=maroof``, ADR-0088): модель не грузится. Карточки проверяет
    MostafaMaroof; суры на ней — следующий шаг (FR-70 ч. 7), до него голосовое суры —
    ``RecognitionError``: ученик видит «не получилось обработать», в журнале — этап
    ``disabled``."""

    async def recognize(self, audio: bytes, text: str) -> Recognition:
        raise RecognitionError("Muaalem выключена (CHECKER=maroof)", stage="disabled")

    async def recognize_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str = "",
        preamble: str = "",
    ) -> SuraRecognition:
        raise RecognitionError("Сура на MostafaMaroof ещё не сделана", stage="disabled")
