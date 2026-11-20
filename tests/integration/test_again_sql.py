"""Вердикт «ещё раз» в БД и отчётах (FR-70 п. 6, 8; ADR-0088 п. 6, 7, «Последствия»).

«Ещё раз» не засчитано: не освоение, не исход «засчитано» для повторения (интервал не сдвигается),
для FAR/FRR и κ бот «не засчитал» (FRR растёт, если учитель засчитал бы). Освоение — по вердикту.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain import review
from muallim.domain.assessment import Assessment, assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations
from muallim.research import metrics

pytestmark = pytest.mark.integration


def _at(day: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, 12, minute, tzinfo=UTC)


async def _learner(session: AsyncSession) -> Learner:
    learner = Learner(UUID(int=1), 4242, "L-00000001", "ru", _at(1))
    await SqlLearnerRepository(session).add(learner)
    return learner


def _attempt(
    learner: Learner, n: int, verdict: Verdict, *, item_id: str = "L01-14", score: int = 100
) -> Attempt:
    return Attempt(
        UUID(int=100 + n), learner.id, item_id, "v1", "maroof",
        Assessment("صَ", "صَ", score, ()), verdict, None, 900, 10, _at(17, n),
    )  # fmt: skip


async def test_again_is_stored_and_is_the_last_verdict(session: AsyncSession) -> None:
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    assert await repo.last_verdict(learner.id, "L01-14") is None
    await repo.add(_attempt(learner, 1, Verdict.FAILED), ())
    await repo.add(_attempt(learner, 2, Verdict.AGAIN), ())
    await repo.add(_attempt(learner, 3, Verdict.EXCELLENT, item_id="L01-15"), ())
    await session.commit()
    assert await repo.last_verdict(learner.id, "L01-14") is Verdict.AGAIN
    assert await repo.last_verdict(learner.id, "L01-15") is Verdict.EXCELLENT


async def test_mastered_cards_are_by_verdict_not_by_score(session: AsyncSession) -> None:
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, Verdict.FAILED, item_id="L01-01", score=85), ())
    await repo.add(_attempt(learner, 2, Verdict.AGAIN, item_id="L01-02", score=100), ())
    await repo.add(_attempt(learner, 3, Verdict.PASSED, item_id="L01-03", score=85), ())
    await repo.add(_attempt(learner, 4, Verdict.FAILED, item_id="L01-04", score=40), ())
    await repo.add(_attempt(learner, 5, Verdict.EXCELLENT, item_id="L01-04", score=100), ())
    await session.commit()
    assert await repo.mastered(learner.id) == frozenset({"L01-03", "L01-04"})


async def test_pilot_first_success_does_not_count_again(session: AsyncSession) -> None:
    """Метрики пилота (FR-55): «ещё раз» — не первый зачёт ученика."""
    from muallim.research import pilot  # noqa: PLC0415

    learner = await _learner(session)
    await SqlAttemptRepository(session).add(_attempt(learner, 1, Verdict.AGAIN), ())
    await session.commit()
    first = (await pilot.collect(session, date(2026, 10, 18))).first_success
    assert (first.learners, first.passed_ever) == (1, 0)


async def _consenting_attempt_with_audio(session: AsyncSession) -> Attempt:
    learner = Learner(UUID(int=1), 111, "L-aaaa", "ru", _at(1), research_consent=True)
    await SqlLearnerRepository(session).add(learner)
    attempt = replace(_attempt(learner, 1, Verdict.AGAIN), audio_sha256="a" * 64)
    await SqlAttemptRepository(session).add(attempt, ())
    await session.commit()
    return attempt


async def test_annotation_queue_shows_again_as_not_passed(session: AsyncSession) -> None:
    from muallim.infrastructure.db.repositories.annotation import (  # noqa: PLC0415
        SqlAnnotationTasks,
    )

    attempt = await _consenting_attempt_with_audio(session)
    task = await SqlAnnotationTasks(session).next_for("A1", frozenset())
    assert task is not None and task.attempt_id == attempt.id
    assert not task.bot_passed


async def test_annotation_package_shows_again_as_not_passed(
    session: AsyncSession, tmp_path: Path
) -> None:
    import csv  # noqa: PLC0415

    from muallim.infrastructure.audio.file_store import FileAudioStore  # noqa: PLC0415
    from muallim.research import annotation  # noqa: PLC0415

    await _consenting_attempt_with_audio(session)
    store = FileAudioStore(tmp_path / "audio")
    store.path_for("a" * 64).parent.mkdir(parents=True, exist_ok=True)
    store.path_for("a" * 64).write_bytes(b"ogg")
    out = tmp_path / "pkg"
    assert await annotation.export_package(session, store.root, out, "A1", 10) == 1
    with (out / "tasks.csv").open(encoding="utf-8-sig", newline="") as f:
        (row,) = list(csv.DictReader(f))
    assert row["bot_verdict"] == "не засчитано"


async def test_again_is_not_a_passed_outcome_for_review(session: AsyncSession) -> None:
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, Verdict.AGAIN), ())
    await repo.add(_attempt(learner, 2, Verdict.PASSED), ())
    await session.commit()
    day = date(2026, 10, 17)
    assert await repo.outcomes(learner.id) == [
        review.Outcome("L01-14", day, False),
        review.Outcome("L01-14", day, True),
    ]


async def test_again_counts_as_not_passed_in_far_and_frr(session: AsyncSession) -> None:
    """Бот сказал «ещё раз», учитель засчитал бы — это ложный отказ (FRR), а не «принято»."""
    learner = await _learner(session)
    a = assess("صَ", "صَ")
    attempt = Attempt(
        UUID(int=200), learner.id, "L01-14", "v1", "maroof", a, Verdict.AGAIN, None, 900, 10,
        _at(10),
    )  # fmt: skip
    await SqlAttemptRepository(session).add(attempt, ())
    await session.execute(
        insert(annotations),
        [
            {
                "attempt_id": attempt.id, "annotator": "T1", "label": "agree",
                "corrected_phonemes": "صَ", "guide_version": "2.0", "comment": "",
                "created_at": _at(17),
            }
        ],
    )  # fmt: skip
    await session.commit()
    v = (await metrics.collect(session, date(2026, 10, 17))).verdicts
    assert (v.accepted, v.rejected, v.false_rejects) == (0, 1, 1)


# ---------- тишина — не попытка; «было → стало» — без «ещё раз» (автор 2026-11-20) ----------
async def test_last_verdict_skips_unheard_attempts(session: AsyncSession) -> None:
    """«Не расслышано» (``model_output["unheard"]``) — не попытка для «ещё раз подряд»."""
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    await repo.add(_attempt(learner, 1, Verdict.AGAIN), ())
    silent = replace(_attempt(learner, 2, Verdict.AGAIN), model_output={"unheard": True})
    await repo.add(silent, ())
    await session.commit()
    assert await repo.last_verdict(learner.id, "L01-14") is Verdict.AGAIN
    only_silence = replace(silent, id=UUID(int=300), item_id="L01-15")
    await repo.add(only_silence, ())
    await session.commit()
    assert await repo.last_verdict(learner.id, "L01-15") is None


async def test_last_assessment_skips_again_attempts(session: AsyncSession) -> None:
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    failed = _attempt(learner, 1, Verdict.FAILED, score=40)
    await repo.add(failed, ())
    await repo.add(_attempt(learner, 2, Verdict.AGAIN, score=0), ())
    await repo.add(_attempt(learner, 3, Verdict.AGAIN, item_id="L01-15", score=0), ())
    await session.commit()
    assert await repo.last_assessment(learner.id, "L01-14") == failed.assessment
    assert await repo.last_assessment(learner.id, "L01-15") is None


# ---------- SQL-отчёты: «засчитано» — по вердикту, не по баллу ≥ 80 (блокер ревью) ----------
REPORTS = Path(__file__).resolve().parents[2] / "analytics" / "sql"


@pytest.mark.parametrize("report", ["02_item_difficulty.sql", "08_book_lines.sql"])
async def test_report_pass_rate_counts_passing_verdicts_not_scores(
    session: AsyncSession, report: str
) -> None:
    """Одна карточка, четыре попытки: «ещё раз» с баллом 100 и «ошибка» с 85 — не засчитаны,
    «засчитано» с 85 и «отлично» со 100 — засчитаны: доля 50 %, а не 100 % по ``score >= 80``."""
    learner = await _learner(session)
    repo = SqlAttemptRepository(session)
    plan = [
        (Verdict.AGAIN, 100),
        (Verdict.FAILED, 85),
        (Verdict.PASSED, 85),
        (Verdict.EXCELLENT, 100),
    ]
    for n, (verdict, score) in enumerate(plan):
        await repo.add(_attempt(learner, n, verdict, score=score), ())
    await session.commit()
    rows = (await session.execute(text((REPORTS / report).read_text(encoding="utf-8")))).mappings()
    (row,) = [r for r in rows if r["item_id"] == "L01-14"]
    assert row["attempts"] == 4
    assert float(row["pass_rate_pct"]) == 50.0
