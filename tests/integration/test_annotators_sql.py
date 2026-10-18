"""Разметчики и очередь разметки на настоящем SQL (FR-17): приглашения, отзыв, порядок, метки."""

import csv
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.annotation import AnnotationSource, AnnotationStatus, Label, invite_digest
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.domain.report import LearnerReport, ReportReason
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.annotation import (
    SqlAnnotationTasks,
    SqlAnnotatorDirectory,
)
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations, annotator_invites
from muallim.research import annotation, annotators
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration


async def _seed(session: AsyncSession) -> None:
    """Ученик A с согласием: 10 — бот нашёл ошибку, 11 — засчитано, 12 — заглушка;
    ученик B без согласия: 13."""
    clock, policy = FixedClock(), GradingPolicy()
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    a = Learner(UUID(int=1), 111, "L-aaaa", "ru", clock.now(), research_consent=True)
    b = Learner(UUID(int=2), 222, "L-bbbb", "ru", clock.now())
    await learners.add(a)
    await learners.add(b)
    for learner, n, heard, sha, model in [
        (a, 11, "صَ", "b" * 64, "muaalem"),
        (a, 10, "سَ", "a" * 64, "muaalem"),
        (a, 12, "صَ", "c" * 64, "stub"),
        (b, 13, "سَ", "d" * 64, "muaalem"),
    ]:
        result = assess("صَ", heard)
        await attempts.add(
            Attempt(UUID(int=n), learner.id, "L01-14", "v1", model, result,
                    policy.verdict(result), sha, 900, 10, clock.now()),
            tuple("msg" for _ in result.errors),
        )  # fmt: skip
    await session.commit()


def _label(n: int, annotator: str = "A1") -> Label:
    return Label(
        attempt_id=UUID(int=n), annotator=annotator, status=AnnotationStatus.AGREE,
        actual="سَ", comment="", source=AnnotationSource.TELEGRAM, seconds_spent=4,
        created_at=FixedClock().now(),
    )  # fmt: skip


# ---------- приглашения и отзыв ----------
async def test_invite_is_stored_as_digest_and_works_once(session: AsyncSession) -> None:
    clock = FixedClock()
    code = await annotators.create_invite(session, "A2", clock)
    stored = (await session.execute(select(annotator_invites))).mappings().one()
    assert code not in str(dict(stored))  # сам код в БД не хранится
    assert stored["code_digest"] == invite_digest(code) and stored["annotator"] == "A2"

    directory = SqlAnnotatorDirectory(session)
    assert await directory.redeem(invite_digest(code), 900, clock.now()) == "A2"
    assert await directory.bound_code(900) == "A2"
    assert await directory.redeem(invite_digest(code), 901, clock.now()) is None  # второй раз


async def test_expired_invite_does_not_work(session: AsyncSession) -> None:
    clock = FixedClock()
    code = await annotators.create_invite(session, "A2", clock)
    later = clock.now() + timedelta(hours=25)
    assert await SqlAnnotatorDirectory(session).redeem(invite_digest(code), 900, later) is None


async def test_revoke_closes_access_and_new_invite_reopens(session: AsyncSession) -> None:
    clock, directory = FixedClock(), SqlAnnotatorDirectory(session)
    code = await annotators.create_invite(session, "A2", clock)
    await directory.redeem(invite_digest(code), 900, clock.now())
    await session.commit()

    await annotators.revoke(session, "A2", clock)
    assert await directory.is_revoked("A2")
    await annotators.revoke(session, "A1", clock)  # разметчик из настроек — тоже закрывается
    assert await directory.is_revoked("A1")
    listed = {row.code: row for row in await annotators.list_annotators(session)}
    assert listed["A2"].revoked and listed["A2"].telegram_bound

    await annotators.create_invite(session, "A2", clock)
    assert not await directory.is_revoked("A2")


async def test_bad_annotator_code_is_refused(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="Код разметчика"):
        await annotators.create_invite(session, "А1", FixedClock())  # кириллица


async def test_failed_redeems_are_counted_per_learner(session: AsyncSession) -> None:
    await _seed(session)
    clock, directory = FixedClock(), SqlAnnotatorDirectory(session)
    start = clock.now()
    await directory.add_failed_redeem(UUID(int=1), clock.now())
    await directory.add_failed_redeem(UUID(int=1), clock.now())
    await directory.add_failed_redeem(UUID(int=2), clock.now())
    assert await directory.failed_redeems(UUID(int=1), start) == 2
    assert await directory.failed_redeems(UUID(int=1), clock.now()) == 0


# ---------- очередь ----------
async def test_queue_order_and_contents_match_excel_package(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _seed(session)
    tasks = SqlAnnotationTasks(session)
    first = await tasks.next_for("A1", frozenset())
    assert first is not None and first.attempt_id == UUID(int=10)  # где бот нашёл ошибки
    assert first.bot_errors == (("ص", "س"),) and not first.bot_passed
    assert (first.bot_heard, first.reference_phonemes) == ("سَ", "صَ")
    assert first.audio_sha256 == "a" * 64
    second = await tasks.next_for("A1", frozenset({UUID(int=10)}))
    assert second is not None and second.attempt_id == UUID(int=11) and second.bot_passed
    assert await tasks.next_for("A1", frozenset({UUID(int=10), UUID(int=11)})) is None
    assert await tasks.remaining("A1") == 2  # без заглушки и без ученика без согласия

    store = FileAudioStore(tmp_path / "audio")
    for sha in ("a" * 64, "b" * 64):
        store.path_for(sha).parent.mkdir(parents=True, exist_ok=True)
        store.path_for(sha).write_bytes(b"ogg")
    await annotation.export_package(session, store.root, tmp_path / "pkg", "A1", 10)
    excel = (tmp_path / "pkg" / "tasks.csv").read_text(encoding="utf-8-sig").splitlines()[1:]
    assert [line.split(",")[1] for line in excel] == [str(UUID(int=10)), str(UUID(int=11))]


async def test_disputed_attempt_comes_first_with_learner_reason(session: AsyncSession) -> None:
    await _seed(session)
    report = LearnerReport(
        UUID(int=11), UUID(int=1), ReportReason.READ_CORRECTLY, FixedClock().now()
    )
    await SqlAttemptRepository(session).add_report(report)
    first = await SqlAnnotationTasks(session).next_for("A1", frozenset())
    assert first is not None and first.attempt_id == UUID(int=11)
    assert first.learner_says == ReportReason.READ_CORRECTLY


async def test_labelled_attempt_leaves_only_that_annotators_queue(session: AsyncSession) -> None:
    await _seed(session)
    tasks = SqlAnnotationTasks(session)
    await tasks.add(_label(10))
    await session.commit()
    assert await tasks.remaining("A1") == 1 and await tasks.remaining("A2") == 2
    row = (await session.execute(select(annotations))).mappings().one()
    assert (row["source"], row["seconds_spent"], row["guide_version"]) == (
        "telegram", 4, annotation.GUIDE_VERSION,
    )  # fmt: skip


async def test_get_hides_attempts_without_consent(session: AsyncSession) -> None:
    await _seed(session)
    tasks = SqlAnnotationTasks(session)
    assert await tasks.get(UUID(int=10)) is not None
    assert await tasks.get(UUID(int=13)) is None  # ученик B без согласия
    assert await tasks.get(UUID(int=99)) is None


async def test_excel_import_marks_source(session: AsyncSession, tmp_path: Path) -> None:
    await _seed(session)
    store = FileAudioStore(tmp_path / "audio")
    for sha in ("a" * 64, "b" * 64):
        store.path_for(sha).parent.mkdir(parents=True, exist_ok=True)
        store.path_for(sha).write_bytes(b"ogg")
    out = tmp_path / "pkg"
    await annotation.export_package(session, store.root, out, "A1", 10)
    with (out / "tasks.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0]["status"] = "agree"
    with (out / "tasks.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    await annotation.import_package(session, out / "tasks.csv", "A1", FixedClock())
    row = (await session.execute(select(annotations))).mappings().one()
    assert row["source"] == "excel" and row["seconds_spent"] is None
