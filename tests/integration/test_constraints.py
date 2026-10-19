"""База сама не принимает неверных значений (TD-DB-02, ADR-0055).

Защита на случай ошибки в коде или ручной правки: допустимые значения вердикта, метки разметки,
её источника и причины жалобы проверяет PostgreSQL (и SQLite в тестах), а не только код.
Идёт на SQLite и — при TEST_POSTGRES_URL — на PostgreSQL.
"""

from uuid import UUID

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from muallim.domain.report import LearnerReport, ReportReason
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations, attempts, detected_errors, learner_reports
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration
LEARNER, ATTEMPT = UUID(int=1), UUID(int=2)


async def _seed(session: AsyncSession) -> None:
    clock = FixedClock()
    await SqlLearnerRepository(session).add(Learner(LEARNER, 5, "L-1", "ru", clock.now()))
    result = assess("صَ", "سَ")
    repo = SqlAttemptRepository(session)
    await repo.add(
        Attempt(
            ATTEMPT, LEARNER, "L01-14", "v1", "m", result, Verdict.FAILED, None, 900, 10,
            clock.now(),
        ),
        ("msg",),
    )  # fmt: skip
    await repo.add_report(LearnerReport(ATTEMPT, LEARNER, ReportReason.OTHER, clock.now()))
    await session.execute(
        insert(annotations).values(
            attempt_id=ATTEMPT, annotator="A1", label="fix", corrected_phonemes="سَ",
            comment="", guide_version="2.1", created_at=clock.now(), source="excel",
        )
    )  # fmt: skip
    await session.commit()


@pytest.mark.parametrize(
    ("table", "values"),
    [
        (attempts, {"verdict": "maybe"}),
        (annotations, {"label": "maybe"}),
        (annotations, {"source": "fax"}),
        (learner_reports, {"reason": "boring"}),
    ],
    ids=["verdict", "label", "source", "reason"],
)
async def test_db_rejects_unknown_values(
    session: AsyncSession, table: object, values: dict[str, str]
) -> None:
    await _seed(session)
    with pytest.raises(IntegrityError):
        await session.execute(update(table).values(**values))  # type: ignore[arg-type]
    await session.rollback()


async def test_old_guide_labels_stay_valid(session: AsyncSession) -> None:
    """Метки руководства 1.0 могли остаться в БД — миграция не должна на них падать."""
    await _seed(session)
    await session.execute(update(annotations).values(label="correct"))
    await session.commit()


async def test_error_number_is_unique_within_attempt(session: AsyncSession) -> None:
    await _seed(session)
    with pytest.raises(IntegrityError):
        await session.execute(
            insert(detected_errors).values(
                attempt_id=ATTEMPT, ordinal=0, kind="letter_substitution", position=0,
                expected="ص", heard="س", message="m",
            )
        )  # fmt: skip
    await session.rollback()


async def test_one_report_per_learner_and_attempt(session: AsyncSession) -> None:
    await _seed(session)
    repo = SqlAttemptRepository(session)
    again = LearnerReport(ATTEMPT, LEARNER, ReportReason.READ_CORRECTLY, FixedClock().now())
    assert await repo.add_report(again) is False
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(learner_reports)) == 1
