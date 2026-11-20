"""Аят суры на MostafaMaroof в БД (FR-70 ч. 7, FR-57, FR-60; ADR-0088 «Суры — решения автора»):
исход «ещё раз» (``again``) и маржи аята в JSON-столбце ``sura_reading_ayahs.model_output``.

Предложенный интерфейс: ``AyahOutcome.AGAIN``; ``AyahResult.model_output: Mapping[str, Any]``
(по умолчанию пусто — у чтений Muaalem столбец пуст, ``NULL``).
"""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.learner import Learner
from muallim.domain.sura import AyahOutcome, AyahResult, SuraAssessment, SuraMode, SuraReading
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.suras import SqlSuraReadingRepository
from muallim.infrastructure.db.tables import sura_reading_ayahs
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration

OUTPUT = {
    "margin": -0.3,
    "margin_other": 2.5,
    "winner": "best-variant",
    "kind": None,
    "unheard": False,
    "second_pass": True,
}


def _reading(learner: Learner, clock: FixedClock) -> SuraReading:
    ayahs = (
        AyahResult("L123-02", 1, AyahOutcome.CLEAN, 100, "a", "a"),
        AyahResult(
            "L123-03",
            2,
            AyahOutcome.AGAIN,
            0,
            "a",
            "",
            model_output=OUTPUT,
        ),
    )
    return SuraReading(
        id=UUID(int=900),
        learner_id=learner.id,
        sura=112,
        mode=SuraMode.TEXT,
        attempt_number=1,
        days_since_last=None,
        studied_by_text=False,
        assessment=SuraAssessment(ayahs, (), 50, "aa", "a"),
        chunks=(),
        credited=(),
        model_version="maroof",
        curriculum_version="v1",
        app_version="a",
        audio_sha256=None,
        audio_duration_ms=9000,
        processing_ms=700,
        created_at=clock.now(),
    )


async def test_ayah_again_and_its_model_output_are_saved(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = Learner(UUID(int=1), 4242, "L-00000001", "ru", clock.now())
    await SqlLearnerRepository(session).add(learner)
    await SqlSuraReadingRepository(session).add(_reading(learner, clock))
    await session.commit()
    rows = (
        (await session.execute(select(sura_reading_ayahs).order_by(sura_reading_ayahs.c.ayah)))
        .mappings()
        .all()
    )
    assert [r["outcome"] for r in rows] == ["clean", "again"]
    assert rows[1]["model_output"] == OUTPUT
    assert not rows[0]["model_output"]  # у аята без маржей столбец пуст
