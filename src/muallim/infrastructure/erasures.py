"""Журнал удалений — файл JSON Lines вне БД (ADR-0054).

Строка: время (UTC), действие и UUID ученика — без Telegram ID. Файл только дописывается;
права 0600, папка 0700, как у записей голоса. Резервная копия сохраняет его рядом с дампом, а
восстановление объединяет журналы и не теряет строк новее копии.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from muallim.application.ports.erasures import ErasureAction, ErasureLog
from muallim.application.ports.system import Clock


@dataclass(frozen=True, slots=True)
class Erasure:
    at: datetime
    action: ErasureAction
    learner_id: UUID


@dataclass(frozen=True, slots=True)
class FileErasureLog(ErasureLog):
    path: Path
    clock: Clock

    async def record(self, action: ErasureAction, learner_id: UUID) -> None:
        line = json.dumps(
            {
                "at": self.clock.now().isoformat(),
                "action": str(action),
                "learner_id": str(learner_id),
            }
        )
        await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)  # строка на диске до commit в БД
        finally:
            os.close(fd)


def read_erasures(path: Path) -> list[Erasure]:
    """Записи по порядку; нет файла — пусто. Испорченная строка — ошибка, а не пропуск."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines and not text.endswith("\n"):
        lines = lines[:-1]  # оборванная последняя строка: сбой посреди записи, до commit в БД
    entries = []
    for n, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            entries.append(
                Erasure(
                    datetime.fromisoformat(item["at"]),
                    ErasureAction(item["action"]),
                    UUID(item["learner_id"]),
                )
            )
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{path}: строка {n} испорчена ({error})") from error
    return entries
