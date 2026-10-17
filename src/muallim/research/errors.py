"""Каталог ошибок с фильтрами (ADR-0023): поиск по представлению v_errors и выгрузка в CSV.

Попытки-заглушки (model_version = 'stub') по умолчанию исключены. Telegram ID не выводится.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.tables import UtcDateTime

COLUMNS = (
    "created_at", "pseudonym", "item_id", "lesson_id", "page", "line", "item_text", "kind",
    "expected", "heard", "position", "syllable", "score", "label", "disputed", "model_version",
    "attempt_id", "error_id", "audio_sha256", "message",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class ErrorFilter:
    expected: str | None = None  # какая буква должна была прозвучать
    heard: str | None = None  # что услышала модель
    kind: str | None = None  # тип ошибки (ErrorKind)
    lesson: str | None = None  # L18
    item: str | None = None  # L18-03
    page: int | None = None
    line: int | None = None
    learner: str | None = None  # псевдоним L-xxxx
    since: datetime | None = None
    until: datetime | None = None
    minimal_pairs: bool = False  # только строки «Обратите внимание»
    unannotated: bool = False  # ещё не размечены
    disputed: bool = False  # ученик нажал «Бот ошибся»
    with_audio: bool = False  # есть запись (ученик дал согласие)
    include_stub: bool = False
    limit: int = 500


async def find_errors(session: AsyncSession, f: ErrorFilter) -> list[dict[str, Any]]:
    where: list[str] = ["1 = 1"]
    params: dict[str, Any] = {"limit": f.limit}
    equal = {
        "expected": f.expected, "heard": f.heard, "kind": f.kind, "lesson_id": f.lesson,
        "item_id": f.item, "page": f.page, "line": f.line, "pseudonym": f.learner,
    }  # fmt: skip
    for column, value in equal.items():
        if value is not None:
            where.append(f"{column} = :{column}")
            params[column] = value
    if f.since is not None:
        where.append("created_at >= :since")
        params["since"] = f.since
    if f.until is not None:
        where.append("created_at < :until")
        params["until"] = f.until
    if f.minimal_pairs:
        where.append("item_note LIKE 'Обратите внимание%'")
    if f.unannotated:
        where.append("label IS NULL")
    if f.disputed:
        where.append("disputed > 0")
    if f.with_audio:
        where.append("audio_sha256 IS NOT NULL")
    if not f.include_stub:
        where.append("model_version <> 'stub'")
    sql = (
        f"SELECT {', '.join(COLUMNS)} FROM v_errors WHERE {' AND '.join(where)} "  # noqa: S608 — только имена колонок из кода
        "ORDER BY created_at, attempt_id, position LIMIT :limit"
    )
    stmt = text(sql).bindparams(
        *(bindparam(k, type_=UtcDateTime()) for k in ("since", "until") if k in params)
    )
    result = await session.execute(stmt, params)
    return [dict(row) for row in result.mappings().all()]


def write_csv(rows: list[dict[str, Any]], path: Path, audio_dir: Path) -> None:
    """CSV для Excel/LibreOffice: каждая ошибка — строка, с путём к записи для прослушивания."""
    store = FileAudioStore(audio_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=[*COLUMNS, "audio_path"])
        writer.writeheader()
        for row in rows:
            sha = row.get("audio_sha256")
            writer.writerow({**row, "audio_path": str(store.path_for(sha)) if sha else ""})
