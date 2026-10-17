"""Хранение записей на диске, адресация по SHA-256: одинаковые файлы не дублируются,
а хеш в БД позволяет проверить, что запись не подменена (NFR-TR-03)."""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from muallim.application.ports.storage import AudioStore


@dataclass(frozen=True, slots=True)
class FileAudioStore(AudioStore):
    root: Path

    def path_for(self, sha256: str) -> Path:
        if len(sha256) != 64 or not all(c in "0123456789abcdef" for c in sha256):
            raise ValueError("Некорректный SHA-256")  # защита от path traversal
        return self.root / sha256[:2] / f"{sha256}.ogg"

    async def save(self, audio: bytes) -> str:
        sha = hashlib.sha256(audio).hexdigest()
        path = self.path_for(sha)
        if not path.exists():
            await asyncio.to_thread(self._write, path, audio)
        return sha

    async def delete(self, sha256: str) -> None:
        self.path_for(sha256).unlink(missing_ok=True)

    @staticmethod
    def _write(path: Path, audio: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(audio)
        tmp.chmod(0o600)
        tmp.replace(path)  # атомарно: недописанный файл не появится под настоящим именем
