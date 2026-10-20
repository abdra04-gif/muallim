"""База сама не принимает неверных значений (TD-DB-02, ADR-0055).

Защита на случай ошибки в коде или ручной правки: допустимые значения вердикта, метки разметки,
её источника, причины жалобы и настроек ученика (ADR-0061) проверяет PostgreSQL (и SQLite
в тестах), а не только код.
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


# ---------- настройки ученика (ADR-0061, миграция 0008) ----------
async def _seed_settings(session: AsyncSession) -> None:
    from muallim.infrastructure.db.tables import learner_settings  # noqa: PLC0415

    await _seed(session)
    await session.execute(
        insert(learner_settings).values(learner_id=LEARNER, updated_at=FixedClock().now())
    )
    await session.commit()


async def test_learner_settings_row_gets_current_bot_defaults(session: AsyncSession) -> None:
    """Строка без значений — как бот работает сейчас (ADR-0029, ADR-0050, ADR-0057; В3, В5)."""
    from muallim.infrastructure.db.tables import learner_settings  # noqa: PLC0415

    await _seed_settings(session)
    row = (await session.execute(select(learner_settings))).mappings().one()
    assert row["how_to_read"] == "spoiler"
    assert (row["auto_reference"], row["daily_opening"]) == (False, True)
    assert (row["large_font"], row["research_block"], row["screen_opening"]) == (False,) * 3
    assert (row["reminder_minute"], row["utc_offset_min"]) == (None, 180)


@pytest.mark.parametrize(
    "values",
    [
        {"how_to_read": "audio"},
        {"reminder_minute": -1},
        {"reminder_minute": 1440},
        {"utc_offset_min": -721},
        {"utc_offset_min": 841},
    ],
    ids=["how_to_read", "minute_low", "minute_high", "offset_low", "offset_high"],
)
async def test_db_rejects_impossible_settings(
    session: AsyncSession, values: dict[str, object]
) -> None:
    from muallim.infrastructure.db.tables import learner_settings  # noqa: PLC0415

    await _seed_settings(session)
    with pytest.raises(IntegrityError):
        await session.execute(update(learner_settings).values(**values))
    await session.rollback()


@pytest.mark.parametrize(
    "values",
    [{"reminder_minute": 0}, {"reminder_minute": 1439}, {"utc_offset_min": -720},
     {"utc_offset_min": 840}, {"how_to_read": "shown"}, {"how_to_read": "hidden"}],
)  # fmt: skip
async def test_db_accepts_boundary_settings(
    session: AsyncSession, values: dict[str, object]
) -> None:
    from muallim.infrastructure.db.tables import learner_settings  # noqa: PLC0415

    await _seed_settings(session)
    await session.execute(update(learner_settings).values(**values))
    await session.commit()


async def test_one_settings_row_per_learner(session: AsyncSession) -> None:
    from muallim.infrastructure.db.tables import learner_settings  # noqa: PLC0415

    await _seed_settings(session)
    with pytest.raises(IntegrityError):
        await session.execute(
            insert(learner_settings).values(learner_id=LEARNER, updated_at=FixedClock().now())
        )
    await session.rollback()
