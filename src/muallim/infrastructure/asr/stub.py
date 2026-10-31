"""Заглушка распознавания: «слышит» ровно эталон. Чтобы запускать и проверять бота без модели.

Включается ASR_BACKEND=stub. В БД попытки помечаются model_version="stub" и в отчёты не идут.
"""

from collections.abc import Sequence

from muallim.application.ports.recognition import (
    PronunciationRecognizer,
    Recognition,
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
