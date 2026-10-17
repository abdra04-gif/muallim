"""Заглушка распознавания: «слышит» ровно эталон. Чтобы запускать и проверять бота без модели.

Включается ASR_BACKEND=stub. В БД попытки помечаются model_version="stub" и в отчёты не идут.
"""

from muallim.application.ports.recognition import PronunciationRecognizer, Recognition


class StubRecognizer(PronunciationRecognizer):
    async def recognize(self, audio: bytes, text: str) -> Recognition:
        return Recognition(
            heard=text, references=(("waqf", text),), model_version="stub", audio_duration_ms=0
        )
