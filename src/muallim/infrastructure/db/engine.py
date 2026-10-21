"""Создание движка БД."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, echo: bool = False) -> AsyncEngine:
    # hide_parameters: значения запроса (Telegram ID и т. п.) не попадают в тексты ошибок и
    # журнал SQLAlchemy (NFR-SEC-07).
    engine = create_async_engine(url, echo=echo, pool_pre_ping=True, hide_parameters=True)
    if engine.dialect.name == "sqlite":
        # В SQLite внешние ключи (и каскадное удаление данных ученика) выключены по умолчанию.
        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
