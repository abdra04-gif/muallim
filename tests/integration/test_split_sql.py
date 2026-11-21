"""Часть попытки и чтения суры в БД (TD-FN-174, шаг 2а; предрегистрация 0.7).

У попытки и чтения суры — столбец ``split``: ``train`` или ``test``. По умолчанию ``train`` (все
старые строки — до разметки по соли, шаг 3). Других значений БД не принимает. Схема: миграция 0017,
docs/data/data-dictionary.md.
"""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import Assessment
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from muallim.domain.split import Part
from muallim.domain.sura import SuraMode
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.suras import SqlSuraReadingRepository
from muallim.infrastructure.db.tables import attempts, sura_readings
from tests.fakes import FixedClock
from tests.integration.test_sura_readings_sql import _reading

pytestmark = pytest.mark.integration
AT = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


async def _learner(session: AsyncSession) -> Learner:
    learner = Learner(UUID(int=1), 4242, "L-00000001", "ru", AT)
    await SqlLearnerRepository(session).add(learner)
    return learner


def _attempt(learner: Learner, n: int) -> Attempt:
    return Attempt(
        UUID(int=100 + n), learner.id, "L03-04", "v1", "maroof",
        Assessment("أَ", "أَ", 100, ()), Verdict.EXCELLENT, None, 900, 10, AT,
    )  # fmt: skip


async def test_attempt_part_is_stored(session: AsyncSession) -> None:
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1), ())
    await repo.add(replace(_attempt(learner, 2), part=Part.TEST), ())
    await session.commit()
    rows = dict((await session.execute(select(attempts.c.id, attempts.c.split))).all())
    assert rows == {UUID(int=101): "train", UUID(int=102): "test"}


async def test_sura_reading_part_is_stored(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = await _learner(session)
    repo = SqlSuraReadingRepository(session)
    await repo.add(
        replace(_reading(learner, clock, n=1, heard="قُلْ", mode=SuraMode.TEXT), part=Part.TEST)
    )
    await session.commit()
    assert (await session.execute(select(sura_readings.c.split))).scalar_one() == "test"


async def test_database_accepts_only_train_or_test(session: AsyncSession) -> None:
    learner = await _learner(session)
    await SqlAttemptRepository(session).add(_attempt(learner, 1), ())
    await session.commit()
    row = dict((await session.execute(select(attempts).limit(1))).mappings().one())
    row.update(id=UUID(int=999), split="holdout")
    with pytest.raises(IntegrityError):
        await session.execute(insert(attempts).values(**row))
        await session.commit()
