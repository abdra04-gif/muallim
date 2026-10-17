"""Эталон «как правильно» (ADR-0018, ADR-0025).

1. Запись учителя: curriculum/audio/<id карточки>.ogg — главнее всего.
2. Для строк из Корана — учебное чтение (муаллим) Махмуда Халиля аль-Хусари по аятам с EveryAyah
   (SRC-042), кэш на диске data/recitations/. Синтез речи не используется (ADR-0018).
3. Для букв, слогов и строк книги — нарезка из того же чтения Хусари (ADR-0032):
   curriculum/audio/husary/, список и проверка — cuts.yaml (scripts/audio/husary_cuts.py).
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import yaml

from muallim.application.ports.storage import ReferenceAudioLibrary

logger: Final = logging.getLogger(__name__)
_AYA: Final = re.compile(r"^(\d{1,3}):(\d{1,3})$")
EVERYAYAH: Final = "https://everyayah.com/data/{reciter}/{sura:03d}{aya:03d}.mp3"

_ITEM_ID: Final = re.compile(r"^L\d{2,3}-\d{2,3}$")  # защита от path traversal


@dataclass(frozen=True, slots=True)
class FileReferenceAudio(ReferenceAudioLibrary):
    root: Path

    def _path(self, item_id: str) -> Path | None:
        if not _ITEM_ID.fullmatch(item_id):
            return None
        path = self.root / f"{item_id}.ogg"
        return path if path.is_file() else None

    def has(self, item_id: str) -> bool:
        return self._path(item_id) is not None

    async def get(self, item_id: str) -> bytes | None:
        path = self._path(item_id)
        return None if path is None else await asyncio.to_thread(path.read_bytes)

    async def save(self, item_id: str, audio: bytes) -> None:
        """Запись учителя (ADR-0024): через временный файл, чтобы не оставить битый эталон."""
        if not _ITEM_ID.fullmatch(item_id):
            raise ValueError(f"Недопустимый id карточки: {item_id!r}")

        def write() -> None:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = self.root / f".{item_id}.ogg.tmp"
            tmp.write_bytes(audio)
            tmp.replace(self.root / f"{item_id}.ogg")

        await asyncio.to_thread(write)


Fetch = Callable[[str], Awaitable[bytes]]


@dataclass
class RecitationCache:
    """Аяты чтеца с EveryAyah: скачиваются один раз и хранятся на диске."""

    root: Path
    fetch: Fetch
    reciter: str = "Husary_Muallim_128kbps"

    async def get(self, ref: str) -> bytes | None:
        m = _AYA.fullmatch(ref)
        if m is None:
            return None
        sura, aya = int(m[1]), int(m[2])
        path = self.root / self.reciter / f"{sura:03d}{aya:03d}.mp3"
        if path.is_file():
            return await asyncio.to_thread(path.read_bytes)
        url = EVERYAYAH.format(reciter=self.reciter, sura=sura, aya=aya)
        try:
            data = await self.fetch(url)
        except Exception:  # сеть недоступна — эталона просто нет
            logger.warning("Не удалось скачать %s", url, exc_info=True)
            return None
        await asyncio.to_thread(_write, path, data)
        return data


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


@dataclass(frozen=True, slots=True)
class HusaryCuts:
    """Нарезки из чтения Хусари по тексту карточки (ADR-0032).

    cuts.yaml: ``- {text, file, status, parts: [...]}``; status ``bad`` — человек прослушал и
    отклонил, такую нарезку не даём. Ключ — текст, а не id: id карточек меняются при пересборке.
    """

    files: Mapping[str, Path]

    @classmethod
    def load(cls, root: Path) -> "HusaryCuts":
        manifest = root / "cuts.yaml"
        if not manifest.is_file():
            return cls({})
        rows = yaml.safe_load(manifest.read_text(encoding="utf-8")) or []
        files = {
            row["text"]: root / Path(row["file"]).name  # только имя: не выйти за пределы root
            for row in rows
            if row.get("status") != "bad" and (root / Path(row["file"]).name).is_file()
        }
        return cls(files)

    def has(self, text: str) -> bool:
        return text in self.files

    async def get(self, text: str) -> bytes | None:
        path = self.files.get(text)
        return None if path is None else await asyncio.to_thread(path.read_bytes)


@dataclass
class CombinedReferenceAudio(ReferenceAudioLibrary):
    """Запись учителя → аят Хусари целиком (id → «сура:аят») → нарезка Хусари (id → текст)."""

    teacher: FileReferenceAudio
    recitations: RecitationCache
    ayat: Mapping[str, str] = field(default_factory=dict)
    cuts: HusaryCuts = field(default_factory=lambda: HusaryCuts({}))
    texts: Mapping[str, str] = field(default_factory=dict)  # id карточки -> её арабский текст

    def has(self, item_id: str) -> bool:
        return (
            self.teacher.has(item_id)
            or item_id in self.ayat
            or self.cuts.has(self.texts.get(item_id, ""))
        )

    async def get(self, item_id: str) -> bytes | None:
        audio = await self.teacher.get(item_id)
        if audio is None and item_id in self.ayat:
            audio = await self.recitations.get(self.ayat[item_id])
        if audio is None and item_id in self.texts:
            audio = await self.cuts.get(self.texts[item_id])
        return audio

    async def save(self, item_id: str, audio: bytes) -> None:
        await self.teacher.save(item_id, audio)
