"""То же на настоящем PostgreSQL: миграции, запись попытки, все SQL-отчёты, удаление.

Запускается, только если задан TEST_POSTGRES_URL (в CI — сервис postgres), например:
TEST_POSTGRES_URL=postgresql+asyncpg://test:test@127.0.0.1:55432/test uv run pytest -m postgres
"""

import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.engine import create_engine, create_session_factory
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import metadata
from muallim.research import dataset, reports
from tests.fakes import FixedClock

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL не задан"),
]


def _alembic(revision: str, up: bool) -> None:
    cfg = Config(ROOT / "alembic.ini")
    cfg.attributes.update(url=URL, configure_logger=False)
    (command.upgrade if up else command.downgrade)(cfg, revision)


@pytest.fixture
def migrated() -> object:
    _alembic("head", up=True)
    yield
    _alembic("base", up=False)


def test_full_cycle_on_postgres(migrated: object) -> None:
    import asyncio  # noqa: PLC0415 — alembic уже использует свой event loop, свой запускаем сами

    async def scenario() -> tuple[str, list[dict[str, object]]]:
        engine = create_engine(URL)
        clock, policy = FixedClock(), GradingPolicy()
        async with create_session_factory(engine)() as session:
            learners = SqlLearnerRepository(session)
            learner = Learner(
                UUID(int=1), 5, "L-00000001", "ru", clock.now(), research_consent=True
            )
            await learners.add(learner)
            result = assess("صَ", "سَ")
            await SqlAttemptRepository(session).add(
                Attempt(
                    UUID(int=2), learner.id, "L01-14", "v1", "muaalem", result,
                    policy.verdict(result), "a" * 64, 900, 10, clock.now(),
                ),
                ("msg",),
            )  # fmt: skip
            await session.commit()
            md = await reports.build_report(engine, ROOT / "analytics" / "sql", clock.now())
            rows = await dataset.dataset_rows(session)
            await learners.delete(learner.id)
            await session.commit()
            assert await SqlAttemptRepository(session).count(learner.id) == 0
        await engine.dispose()
        return md, rows

    async def schema_diff() -> list[object]:
        engine = create_engine(URL)
        async with engine.connect() as conn:
            diff = await conn.run_sync(
                lambda c: compare_metadata(MigrationContext.configure(c), metadata)
            )
        await engine.dispose()
        return list(diff)

    # схема в коде и миграции совпадают и на PostgreSQL, а не только на SQLite
    assert asyncio.run(schema_diff()) == []
    md, rows = asyncio.run(scenario())
    assert "| ص | س | 1 | 1 |" in md
    assert len(rows) == 1 and rows[0]["pseudonym"] == "L-00000001"
