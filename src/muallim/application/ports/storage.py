"""Хранилище аудиозаписей и роликов."""

from dataclasses import dataclass
from typing import Protocol


class AudioStore(Protocol):
    async def save(self, audio: bytes) -> str:
        """Сохраняет запись и возвращает её SHA-256 (адресация по содержимому)."""

    async def delete(self, sha256: str) -> None: ...

    async def read(self, sha256: str) -> bytes | None:
        """Запись по SHA-256 (для разметчика); None — файла нет."""


class ReferenceAudioLibrary(Protocol):
    """Эталонные записи «как правильно» по id карточки (ADR-0018)."""

    def has(self, item_id: str) -> bool: ...

    async def get(self, item_id: str) -> bytes | None: ...

    async def save(self, item_id: str, audio: bytes) -> None:
        """Записать эталон (режим учителя). ValueError — недопустимый id."""


@dataclass(frozen=True, slots=True)
class Video:
    """Ролик «🎬 Как произносить» (FR-56, ADR-0074): mp4 и то, что Telegram просит указать."""

    key: str
    data: bytes
    seconds: float
    width: int
    height: int


class ArticulationVideoLibrary(Protocol):
    """Ролики артикуляции по тексту карточки и по букве (ролик-тройка), ADR-0074."""

    def for_text(self, text: str) -> str | None:
        """Ключ ролика для текста карточки; None — ролика нет."""

    def for_letter(self, letter: str) -> str | None:
        """Ключ ролика-тройки буквы; None — нет.

        В разборе и шпаргалке пока не используется (ADR-0074)."""

    async def get(self, key: str) -> Video | None:
        """Ролик по ключу; None — ключ неизвестен (ролик убран или отклонён)."""
