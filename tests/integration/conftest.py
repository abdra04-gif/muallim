"""Сессия БД для интеграционных тестов.

По умолчанию — SQLite в памяти (быстро, без сервера). Если задан TEST_POSTGRES_URL (в CI — сервис
postgres), те же тесты идут на настоящем PostgreSQL: схема пересоздаётся перед каждым тестом.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.db.engine import create_engine, create_session_factory
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views, drop_views

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")


def _clean(conn: Connection) -> None:
    drop_views(conn)
    metadata.drop_all(conn)
    conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_engine(POSTGRES_URL or "sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        if POSTGRES_URL:
            await conn.run_sync(_clean)
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(create_views)
    async with create_session_factory(engine)() as s:
        yield s
    if POSTGRES_URL:
        async with engine.begin() as conn:
            await conn.run_sync(_clean)
    await engine.dispose()
