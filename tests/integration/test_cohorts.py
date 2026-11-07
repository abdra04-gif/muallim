"""Данные анкеты для исследования: когорты, датасет, поиск ученика по номеру (FR-65, ADR-0081).

Имя ученика — только в `learner_names`: в представлениях, отчётах и выгрузках его нет, найти его
по псевдониму может только исследователь командой `muallim-research learner`.
"""

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import (
    AgeGroup,
    ArabicReading,
    Gender,
    Learner,
    LearnerProfile,
    NativeLanguage,
    Prayer,
)
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import (
    SqlLearnerProfileRepository,
    SqlLearnerRepository,
)
from muallim.research import dataset, learners
from tests.fakes import FixedClock

ROOT = Path(__file__).resolve().parents[2]
COHORT_REPORT = ROOT / "analytics" / "sql" / "12_errors_by_cohort.sql"
pytestmark = pytest.mark.integration

COVARIATES = {"age_group", "gender", "native_language", "arabic_reading", "prayer"}
PERSONAL = {"display_name", "name", "telegram_user_id", "telegram_id"}
DIMENSIONS = {"gender", "age_group", "prayer", "arabic_reading", "native_language"}


async def _learner(
    session: AsyncSession, n: int, *, gender: Gender, model: str = "muaalem"
) -> Learner:
    """Ученик n с анкетой и одной попыткой с одной ошибкой (ص прочитана как س)."""
    clock = FixedClock()
    learner = Learner(UUID(int=n), 1000 + n, f"L-{n:08x}", "ru", clock.now(), research_consent=True)
    await SqlLearnerRepository(session).add(learner)
    await SqlLearnerProfileRepository(session).save(
        LearnerProfile(
            learner_id=learner.id,
            questionnaire_version="q1",
            answered_at=clock.now(),
            display_name=f"Имя{n}",
            age_group=AgeGroup.A25_34,
            gender=gender,
            native_language=NativeLanguage.RU,
            arabic_reading=ArabicReading.NONE,
            prayer=Prayer.REGULAR,
        )
    )
    result = assess("صَ", "سَ")
    await SqlAttemptRepository(session).add(
        Attempt(
            UUID(int=500 + n),
            learner.id,
            "L01-14",
            "v1",
            model,
            result,
            GradingPolicy().verdict(result),
            "a" * 64,
            900,
            10,
            clock.now(),
        ),
        tuple("msg" for _ in result.errors),
    )
    return learner


async def _rows(session: AsyncSession, sql: str) -> list[dict[str, object]]:
    return [dict(r) for r in (await session.execute(text(sql))).mappings().all()]


async def test_dataset_carries_covariates_but_not_the_name(session: AsyncSession) -> None:
    await _learner(session, 1, gender=Gender.FEMALE)
    await session.commit()
    (row,) = await dataset.dataset_rows(session)
    assert row["gender"] == "f" and row["age_group"] == "25_34" and row["prayer"] == "regular"
    assert row.keys() >= COVARIATES
    assert not PERSONAL & row.keys() and "Имя1" not in map(str, row.values())


async def test_dataset_covariates_are_empty_without_questionnaire(session: AsyncSession) -> None:
    learner = await _learner(session, 2, gender=Gender.MALE)
    await session.execute(text("DELETE FROM learner_profiles"))
    await session.commit()
    (row,) = await dataset.dataset_rows(session)
    assert row["pseudonym"] == learner.pseudonym
    assert all(row[key] is None for key in COVARIATES)  # анкеты нет — пустые, но столбцы есть


async def test_cohort_view_has_covariates_and_no_personal_data(session: AsyncSession) -> None:
    learner = await _learner(session, 3, gender=Gender.FEMALE)
    await session.commit()
    (row,) = await _rows(session, "SELECT * FROM v_learner_cohorts")
    assert row["pseudonym"] == learner.pseudonym
    assert row.keys() >= COVARIATES and {"attempts", "errors"} <= row.keys()
    assert (row["gender"], row["attempts"], row["errors"]) == ("f", 1, 1)
    assert not PERSONAL & row.keys() and "Имя3" not in map(str, row.values())


async def test_cohort_report_hides_groups_smaller_than_five(session: AsyncSession) -> None:
    for n in range(1, 6):
        await _learner(session, n, gender=Gender.FEMALE)
    await _learner(session, 6, gender=Gender.MALE)  # один ученик — по группе можно узнать человека
    await _learner(session, 7, gender=Gender.MALE, model="stub")  # заглушка в отчёты не идёт
    await session.commit()
    rows = await _rows(session, COHORT_REPORT.read_text(encoding="utf-8"))
    by_group = {(r["dimension"], r["value"]): r for r in rows}
    female = by_group[("gender", "f")]
    assert (female["learners"], female["attempts"], female["errors"]) == (5, 5, 5)
    assert female["errors_per_attempt"] == 1
    assert ("gender", "m") not in by_group  # группа меньше 5 скрыта
    assert {d for d, _ in by_group} <= DIMENSIONS
    assert all(r["learners"] >= 5 for r in rows)  # type: ignore[operator]
    assert "Имя1" not in str(rows)


async def test_researcher_finds_learner_by_pseudonym(session: AsyncSession) -> None:
    learner = await _learner(session, 8, gender=Gender.FEMALE)
    await session.commit()
    card = await learners.find(session, learner.pseudonym)
    assert card is not None
    assert (card.display_name, card.gender, card.prayer) == ("Имя8", "f", "regular")
    assert card.attempts == 1 and card.pseudonym == learner.pseudonym
    assert "telegram" not in repr(card).lower()  # даже исследователю Telegram ID не показываем


async def test_finding_unknown_pseudonym_gives_nothing(session: AsyncSession) -> None:
    assert await learners.find(session, "L-ffffffff") is None
    assert await learners.find(session, "  ") is None
