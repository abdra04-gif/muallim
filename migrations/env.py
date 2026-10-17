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
    url = config.attributes.get("url") or os.environ.get("DATABASE_URL")
    if not url:
        from muallim.bootstrap.config import Settings  # noqa: PLC0415

        url = Settings().database_url.get_secret_value()  # type: ignore[call-arg]
    return str(url)


def _render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | bool:
    # Свой тип UtcDateTime в миграции пишем как обычный DateTime(timezone=True).
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        render_item=_render_item,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


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
