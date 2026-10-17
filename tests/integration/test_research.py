"""Отчёты, разметка и выгрузка датасета на SQLite с тестовыми данными."""

import csv
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations
from muallim.research import annotation, dataset, reports
from tests.fakes import FixedClock

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


async def _seed(session: AsyncSession) -> None:
    """Два ученика: A с согласием (2 попытки + 1 заглушка), B без согласия (1 попытка)."""
    clock, policy = FixedClock(), GradingPolicy()
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    a = Learner(UUID(int=1), 111, "L-aaaa", "ru", clock.now(), research_consent=True)
    b = Learner(UUID(int=2), 222, "L-bbbb", "ru", clock.now())
    await learners.add(a)
    await learners.add(b)
    plan = [
        (a, 10, "سَ", "a" * 64, "muaalem"),
        (a, 11, "صَ", "b" * 64, "muaalem"),
        (a, 12, "صَ", "c" * 64, "stub"),
        (b, 13, "سَ", None, "muaalem"),
    ]
    for learner, n, heard, sha, model in plan:
        result = assess("صَ", heard)
        await attempts.add(
            Attempt(
                UUID(int=n),
                learner.id,
                "L01-14",
                "v1",
                model,
                result,
                policy.verdict(result),
                sha,
                900,
                10,
                clock.now(),
            ),
            tuple("msg" for _ in result.errors),
        )
    await session.commit()


async def test_report_runs_every_sql_file(session: AsyncSession) -> None:
    await _seed(session)
    md = await reports.build_report(
        session.bind,
        ROOT / "analytics" / "sql",
        FixedClock().now(),  # type: ignore[arg-type]
    )
    sql_files = sorted((ROOT / "analytics" / "sql").glob("*.sql"))
    assert md.count("\n## ") == len(sql_files)
    assert "L-aaaa" in md and "111" not in md.split("## Активность")[1]  # без Telegram ID
    assert "| ص | س | 2 | 2 |" in md  # путаница ص→س у двух учеников, заглушка не в счёт


def test_markdown_table_escapes_pipes() -> None:
    assert "a\\|b" in reports.to_markdown_table(["x"], [("a|b",)])
    assert reports.to_markdown_table(["x"], []) == "_нет данных_"


async def test_annotation_roundtrip(session: AsyncSession, tmp_path: Path) -> None:
    await _seed(session)
    queue = await annotation.export_queue(session, tmp_path, limit=10)
    # Только A (с согласием), без заглушки и без попытки B.
    assert sorted(r["attempt_id"][-1] for r in queue) == ["a", "b"]
    queue[0]["label"], queue[0]["corrected_phonemes"] = "false_alarm", "صَ"
    path = tmp_path / "q.csv"
    annotation.write_csv(queue, path)

    result = await annotation.import_labels(session, path, "A1", FixedClock())
    assert (result.imported, result.skipped_empty) == (1, 1)
    row = (await session.execute(select(annotations))).mappings().one()
    assert (row["label"], row["annotator"], row["guide_version"]) == (
        "false_alarm", "A1", annotation.GUIDE_VERSION,
    )  # fmt: skip
    # Размеченная попытка больше не попадает в очередь.
    assert len(await annotation.export_queue(session, tmp_path, limit=10)) == 1


async def test_annotation_rejects_unknown_label(session: AsyncSession, tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=annotation.EXPORT_COLUMNS)
        w.writeheader()
        w.writerow({"attempt_id": str(UUID(int=1)), "label": "maybe"})
    with pytest.raises(annotation.AnnotationError, match="Строка 2"):
        await annotation.import_labels(session, path, "A1", FixedClock())


async def test_annotation_requires_annotator(session: AsyncSession, tmp_path: Path) -> None:
    with pytest.raises(annotation.AnnotationError):
        await annotation.import_labels(session, tmp_path / "x.csv", "", FixedClock())


async def test_dataset_only_consenting_real_attempts(session: AsyncSession) -> None:
    await _seed(session)
    rows = await dataset.dataset_rows(session)
    assert [r["pseudonym"] for r in rows] == ["L-aaaa", "L-aaaa"]
    assert all("telegram" not in key for r in rows for key in r)
    assert {r["model_version"] for r in rows} == {"muaalem"}


def test_guide_version_matches_document() -> None:
    guide = (ROOT / "docs" / "data" / "annotation-guide.md").read_text(encoding="utf-8")
    assert f"Версия: {annotation.GUIDE_VERSION}" in guide
    for label in annotation.AttemptLabel:
        assert f"`{label}`" in guide, f"метка {label} не описана в руководстве"


async def test_disputed_attempts_come_first_in_queue(session: AsyncSession, tmp_path: Path) -> None:
    from muallim.domain.report import LearnerReport, ReportReason  # noqa: PLC0415

    await _seed(session)
    clock = FixedClock()
    # оспорим более старую попытку A (n=10) — она должна встать первой
    await SqlAttemptRepository(session).add_report(
        LearnerReport(UUID(int=10), UUID(int=1), ReportReason.READ_CORRECTLY, clock.now())
    )
    await session.commit()
    queue = await annotation.export_queue(session, tmp_path, limit=10)
    assert queue[0]["attempt_id"] == str(UUID(int=10))
    assert queue[0]["learner_report"] == "read_correctly"
    assert queue[1]["learner_report"] == ""
