"""Окружение Alembic. Схема — muallim/infrastructure/db/tables.py."""

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy.engine import Connection

from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import UtcDateTime, metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _url() -> str:
    """Миграции — входом владельца схемы (muallim_owner, ADR-0054), если он задан."""
    url = (
        config.attributes.get("url")
        or os.environ.get("MIGRATION_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        from muallim.bootstrap.config import Settings  # noqa: PLC0415

        url = Settings().migration_url()  # type: ignore[call-arg]
    return str(url)


def _render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | bool:
    # Свой тип UtcDateTime в миграции пишем как обычный DateTime(timezone=True).
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(connection: Connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Batch-режим пересоздаёт таблицу (DROP старой): при включённых внешних ключах каскад стёр
        # бы строки, которые на неё ссылаются (жалобы, ошибки, разметку). PRAGMA действует только вне
        # транзакции — поэтому до begin_transaction; после миграций — проверка ссылок.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 0:
            raise RuntimeError("SQLite не выключил внешние ключи — миграция стёрла бы данные")
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=metadata,
        render_item=_render_item,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    try:
        with context.begin_transaction():
            context.run_migrations()
            if sqlite:  # внутри транзакции: при битых ссылках миграция откатится
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
                if broken:
                    raise RuntimeError(f"После миграции нарушены внешние ключи: {broken[:5]}")
    finally:
        if sqlite:
            connection.rollback()  # PRAGMA действует только вне транзакции
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


async def _run_online() -> None:
    engine = create_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_configure)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())
