"""Распознавание произношения (ASR)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Recognition:
    heard: str  # распознанные фонемы
    references: tuple[tuple[str, str], ...]  # (вариант, фонемы): ("wasl", …), ("waqf", …)
    model_version: str
    audio_duration_ms: int
    raw: Mapping[str, Any] = field(default_factory=dict)  # всё, что модель отдала сверх фонем


class PronunciationRecognizer(Protocol):
    async def recognize(self, audio: bytes, text: str) -> Recognition:
        """``audio`` — запись из Telegram (OGG/Opus), ``text`` — арабский текст карточки."""


class RecognitionError(Exception):
    """Запись не удалось обработать (битый файл, тишина, ошибка модели).

    ``stage`` — где сломалось: ``decode`` (ffmpeg) или ``model``; пишется в журнал (QAS-04).
    """

    def __init__(self, message: str, stage: str = "model") -> None:
        super().__init__(message)
        self.stage = stage
