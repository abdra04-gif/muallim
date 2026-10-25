"""Ролики «🎬 Как произносить» (FR-56, ADR-0074): curriculum/video/videos.yaml + mp4.

Устроено как ``SoundLibrary`` (ADR-0068): ролик ищется по тексту карточки, ролик-тройка — ещё и по
букве (``letter``); ``status: bad`` — человек посмотрел и отклонил, не отдаём; ``unchecked``
отдаём. Из имени файла берётся только имя — из папки роликов не выйти. Ключ ролика — имя файла
без расширения (хеш содержимого): он попадает в кнопку и в журнал ``video_played``.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from muallim.application.ports.storage import ArticulationVideoLibrary, Video


@dataclass(frozen=True, slots=True)
class _Entry:
    path: Path
    seconds: float
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class VideoLibrary(ArticulationVideoLibrary):
    entries: Mapping[str, _Entry] = field(default_factory=dict)  # ключ → файл
    texts: Mapping[str, str] = field(default_factory=dict)  # текст карточки → ключ
    letters: Mapping[str, str] = field(default_factory=dict)  # буква → ключ тройки

    @classmethod
    def load(cls, root: Path) -> "VideoLibrary":
        manifest = root / "videos.yaml"
        if not manifest.is_file():
            return cls()
        rows: list[dict[str, Any]] = yaml.safe_load(manifest.read_text(encoding="utf-8")) or []
        entries: dict[str, _Entry] = {}
        texts: dict[str, str] = {}
        letters: dict[str, str] = {}
        for row in rows:
            name = str(row.get("file") or "")
            if row.get("status") == "bad" or Path(name).name != name or not name:
                continue  # отклонён — или имя с папками: из root не выходим
            path = root / name
            if not path.is_file():
                continue
            key = path.stem
            entries[key] = _Entry(
                path, float(row["seconds"]), int(row["width"]), int(row["height"])
            )
            texts[str(row["text"])] = key
            if row.get("letter"):
                letters[str(row["letter"])] = key
        return cls(entries, texts, letters)

    def for_text(self, text: str) -> str | None:
        return self.texts.get(text)

    def for_letter(self, letter: str) -> str | None:
        return self.letters.get(letter)

    async def get(self, key: str) -> Video | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        data = await asyncio.to_thread(entry.path.read_bytes)
        return Video(key, data, entry.seconds, entry.width, entry.height)
