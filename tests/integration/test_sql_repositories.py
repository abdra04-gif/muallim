"""Репозитории на настоящем SQL (SQLite в памяти)."""

from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import (
    ArabicReading,
    ConsentKind,
    ConsentRecord,
    Learner,
    LearnerProfile,
    NativeLanguage,
)
from muallim.domain.policy import Verdict
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.events import SqlEventLog
from muallim.infrastructure.db.repositories.learners import (
    SqlLearnerProfileRepository,
    SqlLearnerRepository,
)
from muallim.infrastructure.db.tables import (
    annotations,
    consents,
    detected_errors,
    interaction_events,
)
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
    from muallim.domain.settings import LearnerSettings  # noqa: PLC0415
    from muallim.infrastructure.db.repositories.settings import (  # noqa: PLC0415
        SqlLearnerSettingsRepository,
    )
    from muallim.infrastructure.db.tables import learner_settings  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    learners = SqlLearnerRepository(session)
    await learners.add(learner)
    await learners.add_consent(
        ConsentRecord(learner.id, ConsentKind.RESEARCH_AUDIO, True, "v", clock.now())
    )
    await SqlAttemptRepository(session).add(_attempt(learner, 1, "سَ", clock), ("m",))
    await SqlEventLog(session, clock).record("x", learner.id, {"k": 1})
    settings = SqlLearnerSettingsRepository(session, clock)
    await settings.save(learner.id, LearnerSettings(reminder_minute=540))  # ADR-0061
    await session.commit()

    await learners.delete(learner.id)
    await session.commit()

    for table in (consents, detected_errors, learner_settings):
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


# ---------- анкета (FR-44) ----------
def _profile(learner: Learner, clock: FixedClock) -> LearnerProfile:
    return LearnerProfile(
        learner_id=learner.id, adult=True, native_language=NativeLanguage.TT,
        arabic_reading=ArabicReading.SLOW_SYLLABLES, questionnaire_version="q1",
        answered_at=clock.now(),
    )  # fmt: skip


async def test_profile_roundtrip(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlLearnerProfileRepository(session)
    assert await repo.get(learner.id) is None
    profile = _profile(learner, clock)
    await repo.add(profile)
    await session.commit()
    assert await repo.get(learner.id) == profile


async def test_minor_profile_has_no_answers(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlLearnerProfileRepository(session)
    minor = LearnerProfile(learner.id, False, None, None, "q1", clock.now())
    await repo.add(minor)
    await session.commit()
    assert await repo.get(learner.id) == minor


async def test_profile_deleted_with_learner(session: AsyncSession) -> None:
    clock = FixedClock()
    learner = _learner(clock)
    learners = SqlLearnerRepository(session)
    await learners.add(learner)
    await SqlLearnerProfileRepository(session).add(_profile(learner, clock))
    await session.commit()
    await learners.delete(learner.id)  # право на удаление (FR-10): анкета уходит каскадом
    await session.commit()
    assert await SqlLearnerProfileRepository(session).get(learner.id) is None


async def test_forget_audio_clears_hashes_and_labels_but_keeps_attempts(
    session: AsyncSession,
) -> None:
    """Отзыв согласия: записи и разметка по ним удаляются, баллы остаются (privacy.md)."""
    clock = FixedClock()
    await SqlLearnerRepository(session).add(learner := _learner(clock))
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, "سَ", clock), ("msg",))
    await session.execute(
        insert(annotations).values(
            attempt_id=UUID(int=101), annotator="A1", label="fix", corrected_phonemes="سَ",
            comment="", guide_version="2.0", created_at=clock.now(),
        )
    )  # fmt: skip
    await session.commit()

    assert await repo.forget_audio(learner.id) == ["a" * 64]
    await session.commit()
    assert await repo.count(learner.id) == 1
    assert await repo.audio_hashes(learner.id) == []
    assert await session.scalar(select(func.count()).select_from(annotations)) == 0
    assert not await repo.audio_in_use("a" * 64)


async def test_forget_audio_until_keeps_later_recordings(session: AsyncSession) -> None:
    """Повтор старого «отзыва» после восстановления не трогает записей после нового «да»."""
    clock = FixedClock()
    await SqlLearnerRepository(session).add(learner := _learner(clock))
    repo = SqlAttemptRepository(session)
    early = _attempt(learner, 1, "صَ", clock)
    withdrawn_at = clock.now()
    late = replace(_attempt(learner, 2, "صَ", clock), audio_sha256="b" * 64)
    await repo.add(early, ())
    await repo.add(late, ())
    await session.commit()
    assert await repo.forget_audio(learner.id, until=withdrawn_at) == ["a" * 64]
    await session.commit()
    assert await repo.audio_hashes(learner.id) == ["b" * 64]


async def test_audio_in_use_sees_other_learners(session: AsyncSession) -> None:
    clock = FixedClock()
    learners = SqlLearnerRepository(session)
    await learners.add(first := _learner(clock))
    await learners.add(second := Learner(UUID(int=2), 4343, "L-00000002", "ru", clock.now()))
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(first, 1, "صَ", clock), ())
    await repo.add(replace(_attempt(second, 2, "صَ", clock), learner_id=second.id), ())
    await session.commit()
    await repo.forget_audio(first.id)
    await session.commit()
    assert await repo.audio_in_use("a" * 64)  # та же запись у второго ученика


# ---------- история исходов для «🔁 Повторения» (FR-52 (б), ADR-0062 вариант A) ----------
async def test_outcomes_in_attempt_order_with_learners_local_day(session: AsyncSession) -> None:
    """Исходы по строкам: по времени попытки, день — местный по ``utc_offset_min``, засчитано —
    вердикт не ``failed``. Чужие попытки не попадают."""
    from datetime import UTC, date, datetime  # noqa: PLC0415

    from muallim.domain import review  # noqa: PLC0415
    from muallim.domain.settings import LearnerSettings  # noqa: PLC0415
    from muallim.infrastructure.db.repositories.settings import (  # noqa: PLC0415
        SqlLearnerSettingsRepository,
    )

    clock = FixedClock()
    learner = _learner(clock)
    other = Learner(UUID(int=2), 4343, "L-00000002", "ru", clock.now())
    learners = SqlLearnerRepository(session)
    await learners.add(learner)
    await learners.add(other)
    await SqlLearnerSettingsRepository(session, clock).save(
        learner.id, LearnerSettings(utc_offset_min=300)
    )
    repo = SqlAttemptRepository(session)
    clock.current = datetime(2026, 10, 17, 20, 0, tzinfo=UTC)  # 01:00 18.10 при UTC+5
    await repo.add(_attempt(learner, 3, "سَ", clock), ("сообщение",))  # вставлена первой
    clock.current = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)  # 15:00 17.10
    await repo.add(_attempt(learner, 1, "سَ", clock), ("сообщение",))
    await repo.add(replace(_attempt(learner, 2, "صَ", clock), verdict=Verdict.PASSED), ())
    await repo.add(replace(_attempt(learner, 4, "سَ", clock), learner_id=other.id), ("с",))
    await session.commit()
    assert await repo.outcomes(learner.id) == [
        review.Outcome("L01-14", date(2026, 10, 17), False),
        review.Outcome("L01-14", date(2026, 10, 17), True),
        review.Outcome("L01-14", date(2026, 10, 18), False),
    ]


async def test_outcomes_without_settings_use_utc_plus_3(session: AsyncSession) -> None:
    from datetime import UTC, date, datetime  # noqa: PLC0415

    from muallim.domain import review  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    clock.current = datetime(2026, 10, 17, 22, 0, tzinfo=UTC)  # 01:00 18.10 по Москве
    await repo.add(_attempt(learner, 1, "سَ", clock), ("сообщение",))
    await session.commit()
    assert await repo.outcomes(learner.id) == [review.Outcome("L01-14", date(2026, 10, 18), False)]


async def test_recent_errors_come_from_last_attempts_only(session: AsyncSession) -> None:
    """Ошибки последних N попыток ученика — из них считаются «буквы, где чаще ошибается»."""
    from muallim.domain.assessment import ErrorKind, PronunciationError  # noqa: PLC0415

    clock = FixedClock()
    learner = _learner(clock)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, "سَ", clock), ("сообщение",))
    await repo.add(_attempt(learner, 2, "صَ", clock), ())
    await repo.add(_attempt(learner, 3, "سَ", clock), ("сообщение",))
    await session.commit()
    substitution = PronunciationError(ErrorKind.LETTER_SUBSTITUTION, 0, None, "ص", "س")
    assert await repo.recent_errors(learner.id, 2) == [substitution]
    assert await repo.recent_errors(learner.id, 3) == [substitution, substitution]
    assert await repo.recent_errors(UUID(int=99), 3) == []
