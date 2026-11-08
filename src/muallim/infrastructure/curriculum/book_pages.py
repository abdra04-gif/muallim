"""Картинки страниц книги (SRC-040): ``curriculum/book_pages/NNN.jpg`` — вне git, как скан.

Собирает скрипт pages.py (scripts) из PDF; сам скан бот не читает (ADR-0022); нет файла —
кнопки страницы нет."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from muallim.application.ports.storage import BookPages


@dataclass(frozen=True, slots=True)
class DirBookPages(BookPages):
    root: Path

    def _path(self, page: int) -> Path:
        return self.root / f"{page:03d}.jpg"

    def has(self, page: int) -> bool:
        return self._path(page).is_file()

    async def get(self, page: int) -> bytes | None:
        path = self._path(page)
        return await asyncio.to_thread(path.read_bytes) if path.is_file() else None
