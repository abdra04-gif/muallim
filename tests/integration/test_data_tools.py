"""Инструменты данных (ADR-0023): снимок программы, представления, фильтр ошибок, отчёты."""

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from muallim.application.ports.repositories import CurriculumVersionError
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import (
    Curriculum,
    ItemKind,
    Lesson,
    LessonItem,
    Lexicon,
    SourceRef,
)
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.curriculum import SqlCurriculumSnapshots
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import curriculum_items
from muallim.research import errors, reports
from tests.fakes import FixedClock

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _engine(session: AsyncSession) -> AsyncEngine:
    assert isinstance(session.bind, AsyncEngine)
    return session.bind


def _course(version: str = "v1", text_l02: str = "صَرَفَ صَبَرَ") -> Curriculum:
    def ref(page: int, line: int) -> SourceRef:
        return SourceRef("SRC-040", page, line)

    lesson = Lesson(
        "L01", 1, "1. ص · Сод",
        (
            LessonItem("L01-01", "صَ صِ صُ", ItemKind.LETTER, "со", name="Сод", source=ref(18, 7)),
            LessonItem("L01-02", text_l02, ItemKind.LINE, "", source=ref(18, 8)),
            LessonItem("L01-03", "سَفَرُ صَفَرُ", ItemKind.LINE, "", source=ref(19, 1),
                       note="Обратите внимание: пары похожих слов"),
        ),
    )  # fmt: skip
    return Curriculum("c", version, "t", (lesson,), _lexicon())


def _lexicon() -> Lexicon:
    from muallim.infrastructure.curriculum.yaml_loader import load_lexicon  # noqa: PLC0415

    return load_lexicon(ROOT / "curriculum" / "lexicon.ru.yaml")


async def _seed(session: AsyncSession) -> None:
    """Ученики A и B; ошибки ص→س на строках 18:8 и 19:1; одна попытка — заглушка."""
    clock, policy = FixedClock(), GradingPolicy()
    await SqlCurriculumSnapshots(session).publish(_course())
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    a = Learner(UUID(int=1), 111, "L-aaaa", "ru", clock.now(), research_consent=True)
    b = Learner(UUID(int=2), 222, "L-bbbb", "ru", clock.now())
    await learners.add(a)
    await learners.add(b)
    plan = [
        (a, 10, "L01-02", "صَرَفَ صَبَرَ", "سَرَفَ صَبَرَ", "a" * 64, "muaalem", 0),
        (b, 11, "L01-02", "صَرَفَ صَبَرَ", "سَرَفَ سَبَرَ", None, "muaalem", 1),
        (a, 12, "L01-03", "سَفَرُ صَفَرُ", "سَفَرُ سَفَرُ", "b" * 64, "muaalem", 2),
        (a, 13, "L01-03", "سَفَرُ صَفَرُ", "سَفَرُ سَفَرُ", None, "stub", 3),
    ]
    for learner, n, item, ref, heard, sha, model, day in plan:
        result = assess(ref, heard)
        await attempts.add(
            Attempt(
                UUID(int=n), learner.id, item, "v1", model, result, policy.verdict(result),
                sha, 900, 10, clock.now() + timedelta(days=day),
            ),
            tuple("msg" for _ in result.errors),
        )  # fmt: skip
    await session.commit()


# ---------- снимок программы ----------
async def test_snapshot_stores_every_item_with_book_reference(session: AsyncSession) -> None:
    assert await SqlCurriculumSnapshots(session).publish(_course()) == 3
    rows = (await session.execute(select(curriculum_items))).mappings().all()
    by_id = {r["item_id"]: r for r in rows}
    assert (by_id["L01-02"]["page"], by_id["L01-02"]["line"]) == (18, 8)
    assert by_id["L01-03"]["note"].startswith("Обратите внимание")
    assert {r["curriculum_version"] for r in rows} == {"v1"}
    assert by_id["L01-01"]["kind"] == "letter" and by_id["L01-01"]["lesson_number"] == 1


async def test_snapshot_is_idempotent_for_same_version(session: AsyncSession) -> None:
    snapshots = SqlCurriculumSnapshots(session)
    await snapshots.publish(_course())
    assert await snapshots.publish(_course()) == 0


async def test_changed_content_without_new_version_is_rejected(session: AsyncSession) -> None:
    snapshots = SqlCurriculumSnapshots(session)
    await snapshots.publish(_course())
    with pytest.raises(CurriculumVersionError, match="L01-02"):
        await snapshots.publish(_course(text_l02="صَرَفَ"))
    assert await snapshots.publish(_course("v2", text_l02="صَرَفَ")) == 3


# ---------- представления ----------
async def test_error_view_joins_book_reference_and_learner(session: AsyncSession) -> None:
    await _seed(session)
    rows = (
        (await session.execute(text("SELECT * FROM v_errors ORDER BY created_at, position")))
        .mappings()
        .all()
    )
    first = rows[0]
    assert (first["pseudonym"], first["page"], first["line"]) == ("L-aaaa", 18, 8)
    assert (first["expected"], first["heard"], first["lesson_id"]) == ("ص", "س", "L01")
    assert "telegram_user_id" not in first


async def test_attempt_view_counts_errors(session: AsyncSession) -> None:
    await _seed(session)
    row = (
        (await session.execute(text("SELECT * FROM v_attempts WHERE pseudonym = 'L-bbbb'")))
        .mappings()
        .one()
    )
    assert (row["errors"], row["page"], row["disputed"]) == (2, 18, 0)


# ---------- фильтр ошибок ----------
async def test_filter_by_letter_excludes_stub(session: AsyncSession) -> None:
    await _seed(session)
    found = await errors.find_errors(session, errors.ErrorFilter(expected="ص"))
    assert len(found) == 4 and {r["model_version"] for r in found} == {"muaalem"}


@pytest.mark.parametrize(
    ("flt", "count"),
    [
        (errors.ErrorFilter(learner="L-bbbb"), 2),
        (errors.ErrorFilter(page=19), 1),
        (errors.ErrorFilter(page=18, line=8), 3),
        (errors.ErrorFilter(lesson="L01", heard="س"), 4),
        (errors.ErrorFilter(kind="letter_substitution"), 4),
        (errors.ErrorFilter(minimal_pairs=True), 1),
        (errors.ErrorFilter(with_audio=True), 2),
        (errors.ErrorFilter(include_stub=True), 5),
        (errors.ErrorFilter(since=datetime(2026, 10, 18, tzinfo=UTC)), 3),
        (errors.ErrorFilter(limit=1), 1),
    ],
)
async def test_error_filters(session: AsyncSession, flt: errors.ErrorFilter, count: int) -> None:
    await _seed(session)
    assert len(await errors.find_errors(session, flt)) == count


async def test_unannotated_filter_and_csv(session: AsyncSession, tmp_path: Path) -> None:
    await _seed(session)
    found = await errors.find_errors(session, errors.ErrorFilter(unannotated=True))
    assert len(found) == 4
    out = tmp_path / "e.csv"
    errors.write_csv(found, out, audio_dir=tmp_path / "audio")
    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["audio_path"].endswith("a" * 64 + ".ogg") and rows[1]["audio_path"] == ""
    assert "telegram_user_id" not in rows[0]


# ---------- отчёты по книге ----------
async def test_book_reports_show_pages_lines_and_minimal_pairs(session: AsyncSession) -> None:
    await _seed(session)
    md = await reports.build_report(
        _engine(session),
        ROOT / "analytics" / "sql",
        FixedClock().now(),
    )
    book = md.split("## Трудные строки книги")[1].split("\n## ")[0]
    assert "| 18 | 8 |" in book and "| 19 | 1 |" in book
    pairs = md.split("## Пары «Обратите внимание»")[1].split("\n## ")[0]
    assert "سَفَرُ صَفَرُ" in pairs
    letters = md.split("## Ошибки по буквам")[1].split("\n## ")[0]
    assert "| ص | 4 |" in letters
