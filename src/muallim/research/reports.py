"""Отчёт по данным исследования: выполняет analytics/sql/*.sql и собирает Markdown."""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def to_markdown_table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "_нет данных_"

    def cell(value: Any) -> str:
        return "" if value is None else str(value).replace("|", "\\|").replace("\n", " ")

    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _title(sql: str, fallback: str) -> str:
    first = sql.lstrip().splitlines()[0] if sql.strip() else ""
    return first.removeprefix("--").strip() if first.startswith("--") else fallback


def _read_queries(sql_dir: Path) -> list[tuple[Path, str]]:
    """Файлы читаются в отдельном потоке: в async-функции диск не блокирует цикл событий."""
    return [(path, path.read_text(encoding="utf-8")) for path in sorted(sql_dir.glob("*.sql"))]


async def build_report(engine: AsyncEngine, sql_dir: Path, generated_at: datetime) -> str:
    parts = [
        "# Отчёт по данным исследования",
        "",
        f"Сформирован: {generated_at.isoformat(timespec='seconds')}  ",
        f"БД: `{engine.dialect.name}`, запросы: `{sql_dir.name}/`",
        "",
    ]
    queries = await asyncio.to_thread(_read_queries, sql_dir)
    async with engine.connect() as conn:
        for path, sql in queries:
            result = await conn.execute(text(sql))
            parts += [
                f"## {_title(sql, path.stem)}",
                "",
                f"Запрос: `{path.name}`",
                "",
                to_markdown_table(list(result.keys()), [tuple(r) for r in result.all()]),
                "",
            ]
    return "\n".join(parts)
