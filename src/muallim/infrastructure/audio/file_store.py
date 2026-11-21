"""Хранение записей на диске, адресация по SHA-256: одинаковые файлы не дублируются,
а хеш в БД позволяет проверить, что запись не подменена (NFR-TR-03).

Тестовые записи (TD-FN-174, ADR-0090) лежат в закрытой части рядом: ``root.parent/holdout/audio``.
Хук закрывает её от агента; бот (разметка учителей, удаление данных ученика) читает и удаляет
записи в обеих частях.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from muallim.application.ports.storage import AudioStore
from muallim.domain.split import Part

HOLDOUT_DIR = "holdout"  # закрытая часть рядом с записями (её же закрывает хук)


@dataclass(frozen=True, slots=True)
class FileAudioStore(AudioStore):
    root: Path

    @property
    def holdout_root(self) -> Path:
        return self.root.parent / HOLDOUT_DIR / "audio"

    def path_for(self, sha256: str, part: Part = Part.TRAIN) -> Path:
        if len(sha256) != 64 or not all(c in "0123456789abcdef" for c in sha256):
            raise ValueError("Некорректный SHA-256")  # защита от path traversal
        root = self.holdout_root if part is Part.TEST else self.root
        return root / sha256[:2] / f"{sha256}.ogg"

    def part_on_disk(self, sha256: str) -> Part | None:
        """Где лежит запись: в учёбе, в тесте или нигде (выгрузки берут только учёбу)."""
        for part in (Part.TEST, Part.TRAIN):
            if self.path_for(sha256, part).is_file():
                return part
        return None

    def _existing(self, sha256: str) -> Path | None:
        part = self.part_on_disk(sha256)
        return self.path_for(sha256, part) if part is not None else None

    async def save(self, audio: bytes, part: Part = Part.TRAIN) -> str:
        """Одни и те же байты в учёбе и тесте — тест побеждает: учебная копия переезжает в
        закрытую часть, голос не утекает в учёбу (ревью 2026-11-21)."""
        sha = hashlib.sha256(audio).hexdigest()
        now = self.part_on_disk(sha)
        if now is Part.TEST:
            return sha
        if now is Part.TRAIN and part is Part.TEST:
            await asyncio.to_thread(self._move_to_test, sha)
            return sha
        if now is None:
            await asyncio.to_thread(self._write, self.path_for(sha, part), audio)
        return sha

    def _move_to_test(self, sha256: str) -> None:
        target = self.path_for(sha256, Part.TEST)
        self._make_dirs(target.parent)
        self.path_for(sha256, Part.TRAIN).replace(target)

    async def delete(self, sha256: str) -> None:
        for part in Part:
            self.path_for(sha256, part).unlink(missing_ok=True)

    async def read(self, sha256: str) -> bytes | None:
        path = self._existing(sha256)
        return await asyncio.to_thread(path.read_bytes) if path is not None else None

    def _make_dirs(self, folder: Path) -> None:
        """Каждая создаваемая папка — 0700, и промежуточные (holdout/, holdout/audio/) тоже."""
        missing = []
        while not folder.exists():
            missing.append(folder)
            folder = folder.parent
        for path in reversed(missing):
            path.mkdir(mode=0o700, exist_ok=True)
            path.chmod(0o700)

    def _write(self, path: Path, audio: bytes) -> None:
        self._make_dirs(path.parent)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(audio)
        tmp.chmod(0o600)
        tmp.replace(path)  # атомарно: недописанный файл не появится под настоящим именем
