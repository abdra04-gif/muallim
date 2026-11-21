"""Соль деления на учёбу и тест (TD-FN-174, ADR-0090): файл в закрытой части рядом с записями.

Создаётся один раз (32 случайных байта, права 0600, папка 0700) и никогда не перезаписывается:
иначе попытки молча переехали бы между учёбой и тестом. Файл появляется только целым (запись во
временный файл, fsync, ``os.link`` без перезаписи). Пропала соль, а тестовые голоса уже есть, или
файл повреждён — ошибка, а не новая соль (ревью 2026-11-21). Хук закрывает эту папку от агента.
"""

import contextlib
import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from muallim.application.ports.storage import SplitSalt

SALT_BYTES = 32


class SaltLostError(RuntimeError):
    """Соли нет или она повреждена, а деление уже шло: восстановите её из копии (make restore)."""


@dataclass(frozen=True, slots=True)
class FileSplitSalt(SplitSalt):
    path: Path

    def get(self) -> bytes:
        if not self.path.is_file():
            if self._test_voices_exist():
                raise SaltLostError(
                    f"Нет соли деления {self.path}, а тестовые записи есть — восстановите из копии"
                )
            self._create()
        salt = self.path.read_bytes()
        if len(salt) != SALT_BYTES:
            raise SaltLostError(
                f"Соль деления повреждена ({len(salt)} байт): восстановите из копии"
            )
        return salt

    def fingerprint(self) -> str:
        return hashlib.sha256(self.get()).hexdigest()

    def _test_voices_exist(self) -> bool:
        audio = self.path.parent / "audio"
        return audio.is_dir() and any(audio.glob("*/*.ogg"))

    def _create(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(secrets.token_bytes(SALT_BYTES))
                file.flush()
                os.fsync(file.fileno())
            with contextlib.suppress(FileExistsError):  # другой процесс успел — его соль и берём
                os.link(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
