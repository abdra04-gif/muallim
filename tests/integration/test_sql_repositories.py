"""Репозитории на настоящем SQL (SQLite в памяти)."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import ConsentKind, ConsentRecord, Learner
from muallim.domain.policy import Verdict
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.events import SqlEventLog
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import consents, detected_errors, interaction_events
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration


def _learner(clock: FixedClock) -> Learner:
    return Learner(UUID(int=1), 4242, "L-00000001", "ru", clock.now())


def _attempt(learner: Learner, n: int, heard: str, clock: FixedClock) -> Attempt:
    return Attempt(
        id=UUID(int=100 + n), learner_id=learner.id, item_id="L01-14", curriculum_version="v1",
        model_version="m", assessment=assess("صَ", heard), verdict=Verdict.FAILED,
        audio_sha256="a" * 64, audio_duration_ms=900, processing_ms=12, created_at=clock.now(),
    )  # fmt: skip


async def test_learner_roundtrip(session: AsyncSession) -> None:
    clock, repo = FixedClock(), SqlLearnerRepository(session)
    learner = _learner(clock)
    await repo.add(learner)
    learner.current_item_id, learner.research_consent = "L01-02", True
    await repo.save(learner)
    await session.commit()
    assert await repo.get_by_telegram_id(4242) == learner
    assert await repo.get_by_telegram_id(1) is None


async def test_attempt_with_errors_and_scores(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, "سَ", clock), ("сообщение",))
    await repo.add(_attempt(learner, 2, "صَ", clock), ())
    await session.commit()
    assert await repo.best_scores(learner.id) == {"L01-14": 100}
    assert await repo.count(learner.id) == 2
    assert await repo.audio_hashes(learner.id) == ["a" * 64] * 2
    row = (await session.execute(select(detected_errors))).mappings().one()
    assert (row["kind"], row["expected"], row["heard"], row["message"]) == (
        "letter_substitution", "ص", "س", "сообщение",
    )  # fmt: skip


async def test_last_assessment_of_a_line_with_its_errors(session: AsyncSession) -> None:
    """Прошлая попытка той же строки — для «было → стало» (FR-43)."""
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    assert await repo.last_assessment(learner.id, "L01-14") is None
    await repo.add(_attempt(learner, 1, "صَ", clock), ())
    second = _attempt(learner, 2, "سَ", clock)
    await repo.add(second, ("сообщение",))
    await session.commit()
    assert await repo.last_assessment(learner.id, "L01-14") == second.assessment
    assert await repo.last_assessment(learner.id, "L01-15") is None


async def test_delete_learner_cascades(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    learners = SqlLearnerRepository(session)
    await learners.add(learner)
    await learners.add_consent(
        ConsentRecord(learner.id, ConsentKind.RESEARCH_AUDIO, True, "v", clock.now())
    )
    await SqlAttemptRepository(session).add(_attempt(learner, 1, "سَ", clock), ("m",))
    await SqlEventLog(session, clock).record("x", learner.id, {"k": 1})
    await session.commit()

    await learners.delete(learner.id)
    await session.commit()

    for table in (consents, detected_errors):
        assert await session.scalar(select(func.count()).select_from(table)) == 0
    event = (await session.execute(select(interaction_events))).mappings().one()
    assert event["learner_id"] is None and event["payload"] == {"k": 1}


async def test_feedback_language_roundtrip(session: AsyncSession) -> None:
    clock, repo = FixedClock(), SqlLearnerRepository(session)
    learner = _learner(clock)
    learner.feedback_language = "kk"
    await repo.add(learner)
    await session.commit()
    stored = await repo.get_by_telegram_id(4242)
    assert stored is not None and stored.feedback_language == "kk"


async def test_decision_trace_is_stored(session: AsyncSession) -> None:
    from muallim.domain.assessment import Candidate  # noqa: PLC0415
    from muallim.domain.policy import GradingPolicy  # noqa: PLC0415
    from muallim.infrastructure.db.tables import attempts  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    base = _attempt(learner, 1, "سَ", clock)
    traced = Attempt(
        **{
            **{f: getattr(base, f) for f in base.__dataclass_fields__},
            "reference_variant": "waqf",
            "candidates": (Candidate("wasl", assess("صََ", "سَ")), Candidate("waqf", base.assessment)),
            "model_output": {"phonemes": "سَ", "sifat": [1, 2]},
            "policy": GradingPolicy(75, 95),
            "app_version": "0.2.0+abc123",
            "feedback_language": "ru",
        }
    )
    await SqlAttemptRepository(session).add(traced, ("m",))
    await session.commit()
    row = (await session.execute(select(attempts))).mappings().one()
    assert row["reference_variant"] == "waqf" and row["app_version"] == "0.2.0+abc123"
    assert [c["variant"] for c in row["candidates"]] == ["wasl", "waqf"]
    assert row["candidates"][1] == {"variant": "waqf", "reference": "صَ", "score": 50}
    assert row["model_output"] == {"phonemes": "سَ", "sifat": [1, 2]}
    assert row["policy"] == {"pass_threshold": 75, "excellent_threshold": 95}
    assert row["feedback_language"] == "ru"


async def test_reports_and_ownership(session: AsyncSession) -> None:
    from muallim.domain.report import LearnerReport, ReportReason  # noqa: PLC0415
    from muallim.infrastructure.db.tables import learner_reports  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    attempt = _attempt(learner, 1, "سَ", clock)
    await repo.add(attempt, ("m",))
    assert await repo.owner(attempt.id) == learner.id
    assert await repo.owner(UUID(int=999)) is None
    await repo.add_report(
        LearnerReport(attempt.id, learner.id, ReportReason.WRONG_ERROR, clock.now())
    )
    await session.commit()
    row = (await session.execute(select(learner_reports))).mappings().one()
    assert (row["attempt_id"], row["reason"]) == (attempt.id, "wrong_error")


async def test_activity_counts_attempts_per_day(session: AsyncSession) -> None:
    from datetime import timedelta  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, "صَ", clock), ())
    await repo.add(_attempt(learner, 2, "صَ", clock), ())
    clock.current += timedelta(days=1)
    await repo.add(_attempt(learner, 3, "صَ", clock), ())
    await session.commit()
    days = await repo.activity(learner.id)
    assert sorted(days.values()) == [1, 2] and len(days) == 2
