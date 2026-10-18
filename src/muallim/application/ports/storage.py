"""Хранилище аудиозаписей."""

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
