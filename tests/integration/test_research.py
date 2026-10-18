"""Отчёты, разметка и выгрузка датасета на SQLite с тестовыми данными."""

import csv
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations
from muallim.research import annotation, dataset, reports
from tests.fakes import FixedClock

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _engine(session: AsyncSession) -> AsyncEngine:
    assert isinstance(session.bind, AsyncEngine)
    return session.bind


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
        _engine(session),
        ROOT / "analytics" / "sql",
        FixedClock().now(),
    )
    sql_files = sorted((ROOT / "analytics" / "sql").glob("*.sql"))
    assert md.count("\n## ") == len(sql_files)
    assert "L-aaaa" in md and "111" not in md.split("## Активность")[1]  # без Telegram ID
    assert "| ص | س | 2 | 2 |" in md  # путаница ص→س у двух учеников, заглушка не в счёт


def test_markdown_table_escapes_pipes() -> None:
    assert "a\\|b" in reports.to_markdown_table(["x"], [("a|b",)])
    assert reports.to_markdown_table(["x"], []) == "_нет данных_"


def _audio(root: Path) -> Path:
    """Файлы записей попыток A (a…, b…, c…) — как их кладёт FileAudioStore."""
    store = FileAudioStore(root)
    for ch in "abc":
        path = store.path_for(ch * 64)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ogg " + ch.encode())
    return root


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _row(rows: list[dict[str, str]], n: int) -> dict[str, str]:
    return next(r for r in rows if r["attempt_id"] == str(UUID(int=n)))


def _save_like_excel(rows: list[dict[str, str]], path: Path) -> Path:
    """Excel с русской локалью: разделитель «;», BOM, переводы строк CRLF."""
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";", lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    return path


async def _package(session: AsyncSession, tmp_path: Path, annotator: str = "A1") -> Path:
    out = tmp_path / f"pkg_{annotator}"
    await annotation.export_package(session, _audio(tmp_path / "audio"), out, annotator, 10)
    return out


async def test_package_has_table_and_recordings_for_annotator(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _seed(session)
    out = tmp_path / "pkg"
    count = await annotation.export_package(session, _audio(tmp_path / "audio"), out, "A1", 10)
    assert count == 2  # только A (с согласием), без заглушки и без попытки B
    assert (out / "tasks.csv").read_bytes().startswith(b"\xef\xbb\xbf")  # Excel видит UTF-8
    rows = _read(out / "tasks.csv")
    assert tuple(rows[0]) == annotation.PACKAGE_COLUMNS
    for row in rows:
        assert row["annotator"] == "A1" and row["status"] == ""
        assert not Path(row["audio"]).is_absolute() and (out / row["audio"]).is_file()
        assert row["reference_phonemes"] == "صَ"
        # разметчик видит ответ бота: «что прозвучало» заполнено тем, что услышал бот
        assert row["actual_phonemes"] == row["bot_heard"]
    first, second = rows
    assert first["attempt_id"] == str(UUID(int=10))  # где бот нашёл ошибки — в начале
    assert first["bot_heard"] == "سَ" and "ص → س" in first["bot_errors"]
    assert first["bot_verdict"] == "не засчитано"
    # засчитанные ботом тоже в пакете — их тоже можно прослушать и оспорить
    assert second["bot_errors"] == "" and second["bot_verdict"] == "засчитано"


async def test_import_from_excel_and_queue_is_per_annotator(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    _row(rows, 10)["status"] = "agree"  # бот прав — одно слово, фонемы не трогать
    path = _save_like_excel(rows, tmp_path / "done.csv")

    result = await annotation.import_package(session, path, "A1", FixedClock())
    assert result == annotation.ImportResult(imported=1, unchanged=0, skipped_empty=1)
    row = (await session.execute(select(annotations))).mappings().one()
    assert (row["label"], row["corrected_phonemes"], row["annotator"], row["guide_version"]) == (
        "agree", "سَ", "A1", annotation.GUIDE_VERSION,
    )  # fmt: skip
    # A1 больше не получит эту попытку, A2 получит всё: размечают оба, независимо
    assert len(_read(await _package(session, tmp_path, "A1") / "tasks.csv")) == 1
    assert len(_read(await _package(session, tmp_path, "A2") / "tasks.csv")) == 2


async def test_reimport_adds_nothing_and_correction_keeps_history(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    _row(rows, 11)["status"] = "agree"
    path = _save_like_excel(rows, tmp_path / "done.csv")
    clock = FixedClock()
    await annotation.import_package(session, path, "A1", clock)

    again = await annotation.import_package(session, path, "A1", clock)
    assert (again.imported, again.unchanged) == (0, 1)  # тот же файл второй раз — без дублей

    _row(rows, 11).update(status="fix", actual_phonemes="سَ")  # разметчик передумал
    fixed = await annotation.import_package(
        session, _save_like_excel(rows, tmp_path / "fixed.csv"), "A1", clock
    )
    assert fixed.imported == 1
    stored = (await session.execute(select(annotations.c.corrected_phonemes))).scalars().all()
    assert stored == ["صَ", "سَ"]  # история сохраняется, в метриках — последняя


async def test_import_strips_invisible_marks(session: AsyncSession, tmp_path: Path) -> None:
    """Excel и редакторы добавляют знаки направления письма и неразрывные пробелы."""
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    _row(rows, 11).update(status="fix", actual_phonemes="\u200f س َ\u00a0")
    await annotation.import_package(
        session, _save_like_excel(rows, tmp_path / "d.csv"), "A1", FixedClock()
    )
    assert await session.scalar(select(annotations.c.corrected_phonemes)) == "سَ"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"status": "maybe"}, "Строка 2"),  # нет такой метки
        ({"status": "fix", "actual_phonemes": "sa"}, "Строка 2"),  # не фонемы
        ({"status": "fix", "actual_phonemes": ""}, "Строка 2"),  # без того, что прозвучало
        ({"status": "agree", "actual_phonemes": "صَ"}, "fix"),  # «согласен», но фонемы правил
        ({"status": "fix"}, "agree"),  # «исправил», но ничего не изменил
        ({"status": "agree", "annotator": "A2"}, "A2"),  # чужой пакет под своим кодом
    ],
)
async def test_import_rejects_bad_rows(
    session: AsyncSession, tmp_path: Path, change: dict[str, str], message: str
) -> None:
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    _row(rows, 10).update(change)  # первая строка: бот услышал «سَ»
    path = _save_like_excel(rows, tmp_path / "bad.csv")
    with pytest.raises(annotation.AnnotationError, match=message):
        await annotation.import_package(session, path, "A1", FixedClock())
    assert (
        await session.scalar(select(func.count()).select_from(annotations)) == 0
    )  # всё или ничего


async def test_import_rejects_file_without_required_columns(
    session: AsyncSession, tmp_path: Path
) -> None:
    path = tmp_path / "x.csv"
    path.write_text("attempt_id;label\n1;ok\n", encoding="utf-8")
    with pytest.raises(annotation.AnnotationError, match="колонк"):
        await annotation.import_package(session, path, "A1", FixedClock())


async def test_import_skips_attempts_deleted_or_without_consent(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Пока разметчик работал, ученик удалил данные или отозвал согласие — метку не сохраняем."""
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    for row in rows:
        row["status"] = "agree"
    path = _save_like_excel(rows, tmp_path / "done.csv")
    await SqlLearnerRepository(session).delete(UUID(int=1))
    await session.commit()
    result = await annotation.import_package(session, path, "A1", FixedClock())
    assert (result.imported, result.skipped_gone) == (0, 2)


async def test_import_keeps_multiline_comment(session: AsyncSession, tmp_path: Path) -> None:
    """Excel сохраняет перенос строки внутри ячейки — комментарий не склеивается."""
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    _row(rows, 11).update(status="agree", comment="шум\nв конце")
    await annotation.import_package(
        session, _save_like_excel(rows, tmp_path / "d.csv"), "A1", FixedClock()
    )
    assert await session.scalar(select(annotations.c.comment)) == "шум\nв конце"


async def test_package_is_readable_only_by_owner(session: AsyncSession, tmp_path: Path) -> None:
    await _seed(session)
    out = await _package(session, tmp_path)
    for path in (out, out / "tasks.csv", out / "audio"):
        assert path.stat().st_mode & 0o077 == 0, path


async def test_annotation_requires_annotator(session: AsyncSession, tmp_path: Path) -> None:
    with pytest.raises(annotation.AnnotationError):
        await annotation.import_package(session, tmp_path / "x.csv", "", FixedClock())
    with pytest.raises(annotation.AnnotationError):
        await annotation.export_package(session, tmp_path, tmp_path / "o", "../A1", 10)


async def test_dataset_only_consenting_real_attempts(session: AsyncSession) -> None:
    await _seed(session)
    rows = await dataset.dataset_rows(session)
    assert [r["pseudonym"] for r in rows] == ["L-aaaa", "L-aaaa"]
    assert all("telegram" not in key for r in rows for key in r)
    assert {r["model_version"] for r in rows} == {"muaalem"}


def test_guide_version_matches_document() -> None:
    guide = (ROOT / "docs" / "data" / "annotation-guide.md").read_text(encoding="utf-8")
    assert f"Версия: {annotation.GUIDE_VERSION}" in guide
    for status in annotation.AttemptStatus:
        assert f"`{status}`" in guide, f"метка {status} не описана в руководстве"


async def test_disputed_attempts_come_first_in_package(
    session: AsyncSession, tmp_path: Path
) -> None:
    from muallim.domain.report import LearnerReport, ReportReason  # noqa: PLC0415

    await _seed(session)
    # оспорим более старую попытку A (n=10) — она должна встать первой
    await SqlAttemptRepository(session).add_report(
        LearnerReport(UUID(int=10), UUID(int=1), ReportReason.READ_CORRECTLY, FixedClock().now())
    )
    await session.commit()
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    assert rows[0]["attempt_id"] == str(UUID(int=10))
    assert "learner_report" not in rows[0]  # жалоба ученика не подсказывает разметчику


async def test_dataset_carries_every_annotator_and_consensus(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _seed(session)
    clock = FixedClock()
    for annotator in ("A1", "A2"):
        rows = _read(await _package(session, tmp_path, annotator) / "tasks.csv")
        for row in rows:
            row["status"] = "agree"  # оба согласны с ботом: 10 — «سَ», 11 — «صَ»
        path = _save_like_excel(rows, tmp_path / f"{annotator}.csv")
        await annotation.import_package(session, path, annotator, clock)
    by_id = {r["attempt_id"]: r for r in await dataset.dataset_rows(session)}
    first = by_id[str(UUID(int=10))]
    assert [a["annotator"] for a in first["annotations"]] == ["A1", "A2"]
    assert first["consensus_phonemes"] == "سَ"

    dataset.write_iqraeval(list(by_id.values()), tmp_path)
    truth = _read(tmp_path / "truth.csv")
    assert tuple(truth[0]) == ("ID", "Reference_phn", "Annotated_phn")
    assert {r["ID"]: r["Annotated_phn"] for r in truth}[str(UUID(int=10))] == "س َ"
    predictions = _read(tmp_path / "predictions.csv")
    assert {r["ID"]: r["Prediction"] for r in predictions}[str(UUID(int=10))] == "س َ"


async def test_dataset_has_no_consensus_with_single_annotator(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Согласованная разметка — когда оценили минимум двое (размечают оба, ADR-0040)."""
    await _seed(session)
    rows = _read(await _package(session, tmp_path) / "tasks.csv")
    for row in rows:
        row["status"] = "agree"
    await annotation.import_package(
        session, _save_like_excel(rows, tmp_path / "A1.csv"), "A1", FixedClock()
    )
    assert all(r["consensus_phonemes"] is None for r in await dataset.dataset_rows(session))


async def test_dataset_has_no_consensus_when_annotators_disagree(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _seed(session)
    clock = FixedClock()
    for annotator, status in (("A1", "agree"), ("A2", "fix")):
        rows = _read(await _package(session, tmp_path, annotator) / "tasks.csv")
        for row in rows:
            row["status"] = status
            if status == "fix":  # A2 слышит обратное тому, что услышал бот
                row["actual_phonemes"] = "صَ" if row["bot_heard"] == "سَ" else "سَ"
        await annotation.import_package(
            session, _save_like_excel(rows, tmp_path / f"{annotator}.csv"), annotator, clock
        )
    rows = await dataset.dataset_rows(session)
    assert all(r["consensus_phonemes"] is None for r in rows)
    dataset.write_iqraeval(rows, tmp_path)
    assert _read(tmp_path / "truth.csv") == []  # спорные — только после разбора, не в эталон
