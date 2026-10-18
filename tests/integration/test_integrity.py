"""Сверка БД и файлов записей (NFR-TR-03): ничего не потеряно, лишнего не хранится."""

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.research import integrity
from tests.fakes import FixedClock

pytestmark = pytest.mark.integration


async def _seed(session: AsyncSession, store: FileAudioStore) -> dict[str, str]:
    """Попытки: ok (файл цел), missing (файла нет), corrupted (файл подменён), без согласия."""
    clock = FixedClock()
    learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
    yes = Learner(UUID(int=1), 1, "L-1", "ru", clock.now(), research_consent=True)
    no = Learner(UUID(int=2), 2, "L-2", "ru", clock.now())
    await learners.add(yes)
    await learners.add(no)
    sha = {name: await store.save(name.encode()) for name in ("ok", "corrupted", "orphan", "no")}
    sha["missing"] = "f" * 64
    store.path_for(sha["corrupted"]).write_bytes(b"tampered")
    for n, (learner, name) in enumerate(
        [(yes, "ok"), (yes, "missing"), (yes, "corrupted"), (no, "no")], start=1
    ):
        await attempts.add(
            Attempt(
                UUID(int=100 + n), learner.id, "L01-14", "v1", "m", assess("صَ", "صَ"),
                Verdict.EXCELLENT, sha[name], 900, 10, clock.now(),
            ),
            (),
        )  # fmt: skip
    await session.commit()
    return sha


async def test_check_finds_missing_orphan_corrupted_and_unconsented(
    session: AsyncSession, tmp_path: Path
) -> None:
    store = FileAudioStore(tmp_path)
    sha = await _seed(session, store)
    report = await integrity.check(session, tmp_path)
    assert report.missing == [sha["missing"]]
    assert report.orphans == [sha["orphan"]]
    assert report.corrupted == [sha["corrupted"]]
    assert report.without_consent == 1  # запись ученика, который не давал или отозвал согласие
    assert not report.ok


async def test_delete_orphans_removes_only_old_unreferenced_files(
    session: AsyncSession, tmp_path: Path
) -> None:
    store = FileAudioStore(tmp_path)
    sha = await _seed(session, store)
    report = await integrity.check(session, tmp_path)
    assert await integrity.delete_orphans(session, report, tmp_path, min_age_s=0) == 1
    assert not store.path_for(sha["orphan"]).exists()
    assert store.path_for(sha["ok"]).exists()


async def test_delete_orphans_spares_fresh_files(session: AsyncSession, tmp_path: Path) -> None:
    """Бот сохраняет файл до commit попытки: свежий «лишний» файл может стать нужным."""
    store = FileAudioStore(tmp_path)
    sha = await _seed(session, store)
    report = await integrity.check(session, tmp_path)
    assert await integrity.delete_orphans(session, report, tmp_path) == 0
    assert store.path_for(sha["orphan"]).exists()


async def test_stray_files_with_bad_names_do_not_break_check(
    session: AsyncSession, tmp_path: Path
) -> None:
    (tmp_path / "zz").mkdir()
    (tmp_path / "zz" / "notes.ogg").write_bytes(b"x")
    report = await integrity.check(session, tmp_path)
    assert report.orphans == [] and report.checked == 0


async def test_copies_of_deleted_recordings_are_found(
    session: AsyncSession, tmp_path: Path
) -> None:
    """После отзыва согласия копии остаются в пакетах разметки и выгрузках — verify их находит."""
    store = FileAudioStore(tmp_path / "audio")
    sha = await _seed(session, store)
    package = tmp_path / "annotation" / "A1_x" / "audio"
    package.mkdir(parents=True)
    (package / f"{sha['ok']}.ogg").write_bytes(b"ok")  # ученик с согласием — нормально
    (package / f"{sha['no']}.ogg").write_bytes(b"no")  # без согласия — удалить
    (package / f"{'e' * 64}.ogg").write_bytes(b"gone")  # попытки нет — удалить
    report = await integrity.check(
        session, tmp_path / "audio", copies=[tmp_path / "annotation", tmp_path / "exports"]
    )
    assert sorted(Path(p).name for p in report.stale_copies) == sorted(
        [f"{sha['no']}.ogg", f"{'e' * 64}.ogg"]
    )
    assert not report.ok


async def test_clean_storage_is_ok(session: AsyncSession, tmp_path: Path) -> None:
    report = await integrity.check(session, tmp_path / "empty")
    assert report.ok and report.missing == report.orphans == report.corrupted == []


def test_render_lists_problems_without_personal_data(tmp_path: Path) -> None:
    report = integrity.IntegrityReport(
        missing=["a" * 64], orphans=[], corrupted=[], without_consent=2, checked=3,
        stale_copies=["data/annotation/A1_x/audio/b.ogg"],
    )  # fmt: skip
    text = integrity.render(report)
    assert "a" * 64 in text and "2" in text and "A1_x" in text
