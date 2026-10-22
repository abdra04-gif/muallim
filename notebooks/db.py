"""Запросы к базе Muallim из Jupyter-ноутбука: SQL → таблица pandas.

Вход только для чтения `muallim_reader` (ADR-0054): изменить данные отсюда нельзя.
Пароль — строка READER_DB_PASSWORD в .env в корне проекта (создаёт `make db-roles`).

    from db import sql
    df = await sql("SELECT expected, heard, COUNT(*) AS n FROM v_errors GROUP BY 1, 2")
"""

from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HOST, PORT, DATABASE, USER = "localhost", 5432, "muallim", "muallim_reader"


def _reader_password(env_file: Path = ROOT / ".env") -> str:
    """Пароль из переменной окружения или из строки READER_DB_PASSWORD файла .env."""
    if password := os.environ.get("READER_DB_PASSWORD"):
        return password
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "READER_DB_PASSWORD":
                return value.strip().strip("'\"")
    msg = "Нет READER_DB_PASSWORD в .env — выполните `make db-roles`"
    raise RuntimeError(msg)


async def sql(query: str, *args: object) -> pd.DataFrame:
    """Выполнить SELECT и вернуть результат таблицей. Параметры — $1, $2, …"""
    conn = await asyncpg.connect(
        host=HOST, port=PORT, database=DATABASE, user=USER, password=_reader_password()
    )
    try:
        stmt = await conn.prepare(query)
        columns = [attr.name for attr in stmt.get_attributes()]
        rows = await stmt.fetch(*args)
    finally:
        await conn.close()
    return pd.DataFrame([tuple(r) for r in rows], columns=columns)
