"""Журнал удалений вне БД и его повтор после восстановления копии (TD-DB-05, ADR-0054).

Копия БД от понедельника не знает, что во вторник ученик удалил данные или отозвал согласие.
Журнал лежит вне БД и вне копий; после восстановления он повторяется — право на удаление цело.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.erasures import ErasureAction
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import ConsentKind, ConsentRecord, Learner
from muallim.domain.policy import Verdict
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import learners
from muallim.infrastructure.erasures import FileErasureLog, read_erasures
from muallim.research import erasures, integrity

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
A, B = UUID(int=1), UUID(int=2)


class StepClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        self.current += timedelta(minutes=1)
        return self.current


async def test_log_appends_lines_readable_only_by_owner(tmp_path: Path) -> None:
    path = tmp_path / "erasures" / "erasures.jsonl"
    log = FileErasureLog(path, StepClock(T0))
    await log.record(ErasureAction.WITHDRAW, A)
    await log.record(ErasureAction.DELETE, B)
    entries = read_erasures(path)
    assert [(e.action, e.learner_id) for e in entries] == [
        (ErasureAction.WITHDRAW, A),
        (ErasureAction.DELETE, B),
    ]
    assert entries[0].at < entries[1].at
    assert path.stat().st_mode & 0o077 == 0 and path.parent.stat().st_mode & 0o077 == 0
    assert "telegram" not in path.read_text(encoding="utf-8")  # только UUID ученика


async def test_grant_without_consent_record_keeps_consent_off(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Копия старше нового согласия: в ней нет записи о нём — включать запись голоса нельзя."""
    await _seed(session, FileAudioStore(tmp_path / "audio"))
    path = tmp_path / "erasures.jsonl"
    log = FileErasureLog(path, StepClock(T0))
    await log.record(ErasureAction.WITHDRAW, B)
    await log.record(ErasureAction.GRANT, B)
    result = await erasures.reapply(session, path, tmp_path / "audio")
    assert (result.withdrawn, result.granted) == (1, 0)
    consent = await session.scalar(select(learners.c.research_consent).where(learners.c.id == B))
    assert consent is False  # ученик даст согласие снова


def test_torn_last_line_is_skipped(tmp_path: Path) -> None:
    """Сбой посреди записи оставляет оборванную последнюю строку — её пропускаем, остальное цело."""
    path = tmp_path / "e.jsonl"
    good = f'{{"at": "{T0.isoformat()}", "action": "delete", "learner_id": "{A}"}}\n'
    path.write_text(good + '{"at": "2026-10-20T12:0', encoding="utf-8")
    assert [e.learner_id for e in read_erasures(path)] == [A]


def test_missing_log_is_empty_and_broken_line_is_an_error(tmp_path: Path) -> None:
    assert read_erasures(tmp_path / "nope.jsonl") == []
    broken = tmp_path / "e.jsonl"
    broken.write_text('{"at": "2026-10-20T12:00:00+00:00"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="строка 1"):
        read_erasures(broken)


async def _seed(session: AsyncSession, store: FileAudioStore) -> dict[str, str]:
    """Как в восстановленной копии: A и B с согласием, у каждого по записи до T0."""
    repo, people = SqlAttemptRepository(session), SqlLearnerRepository(session)
    sha = {}
    for n, learner_id in enumerate((A, B), start=1):
        await people.add(Learner(learner_id, n, f"L-{n}", "ru", T0, research_consent=True))
        sha[str(n)] = await store.save(f"voice {n}".encode())
        await repo.add(
            Attempt(
                UUID(int=100 + n), learner_id, "L01-14", "v1", "m", assess("صَ", "صَ"),
                Verdict.EXCELLENT, sha[str(n)], 900, 10, T0,
            ),
            (),
        )  # fmt: skip
    await session.commit()
    return sha


async def test_reapply_after_restore_deletes_again(session: AsyncSession, tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path / "audio")
    sha = await _seed(session, store)
    path = tmp_path / "erasures.jsonl"
    log = FileErasureLog(path, StepClock(T0))
    await log.record(ErasureAction.DELETE, A)  # после копии A удалил данные
    await log.record(ErasureAction.WITHDRAW, B)  # B отозвал согласие

    before = await integrity.check(session, tmp_path / "audio", erasure_log=path)
    assert before.pending_erasures == 2 and not before.ok

    result = await erasures.reapply(session, path, tmp_path / "audio")
    assert (result.deleted, result.withdrawn, result.files_deleted) == (1, 1, 2)
    assert await session.scalar(select(func.count()).select_from(learners)) == 1
    assert await session.scalar(select(learners.c.research_consent)) is False
    assert await SqlAttemptRepository(session).audio_hashes(B) == []
    assert not store.path_for(sha["1"]).exists() and not store.path_for(sha["2"]).exists()

    after = await integrity.check(session, tmp_path / "audio", erasure_log=path)
    assert after.pending_erasures == 0
    again = await erasures.reapply(session, path, tmp_path / "audio")  # повтор безвреден
    assert again == erasures.ReapplyResult(deleted=0, withdrawn=0, granted=0, files_deleted=0)


async def test_reapply_keeps_recordings_made_after_new_consent(
    session: AsyncSession, tmp_path: Path
) -> None:
    """B отозвал согласие, потом снова дал и записался: новая запись остаётся."""
    store = FileAudioStore(tmp_path / "audio")
    await _seed(session, store)
    path = tmp_path / "erasures.jsonl"
    clock = StepClock(T0)
    log = FileErasureLog(path, clock)
    await log.record(ErasureAction.WITHDRAW, B)
    await log.record(ErasureAction.GRANT, B)
    # согласие сохранено в БД (consents) — копия новее согласия
    await SqlLearnerRepository(session).add_consent(
        ConsentRecord(B, ConsentKind.RESEARCH_AUDIO, True, "v", clock.now())
    )
    late_sha = await store.save(b"after new consent")
    await SqlAttemptRepository(session).add(
        Attempt(
            UUID(int=200), B, "L01-14", "v1", "m", assess("صَ", "صَ"), Verdict.EXCELLENT,
            late_sha, 900, 10, clock.now(),
        ),
        (),
    )  # fmt: skip
    await session.commit()

    result = await erasures.reapply(session, path, tmp_path / "audio")
    assert (result.withdrawn, result.granted) == (1, 1)
    assert await SqlAttemptRepository(session).audio_hashes(B) == [late_sha]
    consent = await session.scalar(select(learners.c.research_consent).where(learners.c.id == B))
    assert consent is True
    assert store.path_for(late_sha).exists()
