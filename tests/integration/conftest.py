from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.infrastructure.db.engine import create_engine, create_session_factory
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(create_views)
    async with create_session_factory(engine)() as s:
        yield s
    await engine.dispose()
