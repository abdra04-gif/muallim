"""Распознавание произношения (ASR)."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from muallim.domain.sura import AyahReference


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


@dataclass(frozen=True, slots=True)
class Listening:
    """Что модель услышала для «вариантов карточки» (FR-70, ADR-0088 п. 1).

    ``score(вариант)`` — log P(вариант | запись) для любой строки в записи фонетизатора бота
    (−inf — вариант невозможен); ``sounds(вариант)`` — его звуки для модели (одинаковые звуки —
    один и тот же балл); ``raw`` — жадная расшифровка без подсказки (учителю);
    ``score_many(варианты)`` — баллы многих вариантов одним проходом (батч-CTC), у заглушек нет.
    """

    references: tuple[tuple[str, str], ...]  # (вариант, запись бота): ("wasl", …), ("waqf", …)
    model_version: str
    audio_duration_ms: int
    raw: str
    score: Callable[[str], float]
    sounds: Callable[[str], Sequence[str]]
    score_many: Callable[[Sequence[str]], Sequence[float]] | None = None


class CardListener(Protocol):
    async def listen(self, audio: bytes, text: str, *, long_is_short: bool) -> Listening:
        """``audio`` — запись из Telegram, ``text`` — текст карточки; ``long_is_short`` — на уроке
        протянутая гласная не ошибка (`CardPolicy.long_is_short`)."""


@dataclass(frozen=True, slots=True)
class AyahListening:
    """Аят в записи суры (FR-70 ч. 7): баллы вариантов — на его отрезке. ``span_ms is None`` —
    аят не прозвучал (пропущен или не дочитан). ``rehear()`` — второй проход: аят вырезается из
    записи и слушается отдельно (модель зовётся только при вызове)."""

    item_id: str
    number: int
    references: tuple[tuple[str, str], ...]
    raw: str
    score: Callable[[str], float]
    sounds: Callable[[str], Sequence[str]]
    score_many: Callable[[Sequence[str]], Sequence[float]] | None
    span_ms: tuple[int, int] | None
    rehear: Callable[[], Awaitable[Listening]] | None


@dataclass(frozen=True, slots=True)
class SuraListening:
    """Сура целиком на «вариантах карточки». ``prefix`` — что прозвучало перед сурой:
    ``"preamble"`` (истиаза), ``"opening"`` (басмала)."""

    ayahs: tuple[AyahListening, ...]
    prefix: tuple[str, ...]
    raw: str
    model_version: str
    audio_duration_ms: int
    pauses: tuple[tuple[int, int], ...] = ()
    chunks: tuple[tuple[int, int, int, int], ...] = ()


@runtime_checkable
class SuraListener(Protocol):
    async def listen_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str,
        preamble: str,
        *,
        long_is_short: bool,
    ) -> SuraListening:
        """``ayahs`` — (id карточки, номер аята, текст); ``opening`` — басмала, ``preamble`` —
        истиаза (необязательные начала)."""


@dataclass(frozen=True, slots=True)
class SuraRecognition:
    """Сура целиком (FR-57, ADR-0076): запись режется на куски 6–10 с, фонемы склеиваются."""

    heard: str
    ayahs: tuple[AyahReference, ...]  # эталон по аятам и словам
    opening: tuple[str, ...]  # басмала перед сурой по словам; () — нет
    preamble: tuple[str, ...]  # истиаза перед басмалой по словам; () — нет
    pauses: tuple[tuple[int, int], ...]  # молчание: (позиция в heard, мс)
    chunks: tuple[tuple[int, int, int, int], ...]  # (начало мс, конец мс, начало и конец в heard)
    model_version: str
    audio_duration_ms: int


@runtime_checkable
class SuraRecognizer(Protocol):
    async def recognize_sura(
        self,
        audio: bytes,
        ayahs: Sequence[tuple[str, int, str]],
        opening: str = "",
        preamble: str = "",
    ) -> SuraRecognition:
        """``ayahs`` — (id карточки, номер аята, текст); ``opening`` — басмала перед сурой,
        ``preamble`` — истиаза перед ней (необязательные начала)."""


class RecognitionError(Exception):
    """Запись не удалось обработать (битый файл, тишина, ошибка модели).

    ``stage`` — где сломалось: ``decode`` (ffmpeg) или ``model``; пишется в журнал (QAS-04).
    """

    def __init__(self, message: str, stage: str = "model") -> None:
        super().__init__(message)
        self.stage = stage
