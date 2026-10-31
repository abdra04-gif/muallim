"""Голос чтения суры целиком (FR-60, ADR-0076): сверка хранилища, согласие, удаление.

Аудит безопасности 2026-10-31: ``verify`` не знал ``sura_readings`` — ``--delete-orphans`` стёр бы
голоса сур с согласием, а голос суры без согласия был бы не виден. Ветки сур в ``forget_audio``,
``audio_hashes``, ``audio_in_use`` (отзыв согласия, /delete) тестами не были покрыты.
"""

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.learner import Learner
from muallim.domain.sura import SuraMode
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.suras import SqlSuraReadingRepository
from muallim.infrastructure.db.tables import sura_readings
from muallim.research import integrity
from tests.fakes import FixedClock
from tests.integration.test_sura_readings_sql import _reading

pytestmark = pytest.mark.integration


async def _sura_with_audio(
    session: AsyncSession, store: FileAudioStore, *, consent: bool
) -> tuple[Learner, str]:
    clock = FixedClock()
    learner = Learner(UUID(int=1), 1, "L-1", "ru", clock.now(), research_consent=consent)
    await SqlLearnerRepository(session).add(learner)
    sha = await store.save(b"sura-voice")
    reading = replace(
        _reading(learner, clock, n=1, heard="قُلْهُوَ", mode=SuraMode.MEMORY), audio_sha256=sha
    )
    await SqlSuraReadingRepository(session).add(reading)
    await session.commit()
    return learner, sha


async def test_sura_voice_with_consent_is_not_an_orphan(
    session: AsyncSession, tmp_path: Path
) -> None:
    store = FileAudioStore(tmp_path)
    _, sha = await _sura_with_audio(session, store, consent=True)
    report = await integrity.check(session, tmp_path)
    assert sha not in report.orphans
    assert report.ok
    assert await integrity.delete_orphans(session, report, tmp_path, min_age_s=0) == 0
    assert store.path_for(sha).exists()


async def test_delete_orphans_double_checks_sura_readings(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Перед удалением «лишнего» файла БД спрашивается ещё раз — и про суры тоже."""
    store = FileAudioStore(tmp_path)
    _, sha = await _sura_with_audio(session, store, consent=True)
    stale = integrity.IntegrityReport(
        missing=[], orphans=[sha], corrupted=[], without_consent=0, checked=1
    )
    assert await integrity.delete_orphans(session, stale, tmp_path, min_age_s=0) == 0
    assert store.path_for(sha).exists()


async def test_sura_voice_without_consent_is_reported(
    session: AsyncSession, tmp_path: Path
) -> None:
    store = FileAudioStore(tmp_path)
    await _sura_with_audio(session, store, consent=False)
    report = await integrity.check(session, tmp_path)
    assert report.without_consent == 1


async def test_withdrawing_consent_forgets_sura_voice(
    session: AsyncSession, tmp_path: Path
) -> None:
    store = FileAudioStore(tmp_path)
    learner, sha = await _sura_with_audio(session, store, consent=True)
    attempts = SqlAttemptRepository(session)
    assert await attempts.audio_hashes(learner.id) == [sha]
    assert await attempts.audio_in_use(sha)
    assert await attempts.forget_audio(learner.id) == [sha]
    await session.commit()
    left = (await session.scalars(select(sura_readings.c.audio_sha256))).all()
    assert left == [None]
    assert not await attempts.audio_in_use(sha)


async def test_forget_audio_until_keeps_later_sura_voice(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Повтор журнала удалений после восстановления (``until``) не трогает более поздние записи."""
    store = FileAudioStore(tmp_path)
    learner, sha = await _sura_with_audio(session, store, consent=True)
    before = learner.created_at  # раньше записи суры
    assert await SqlAttemptRepository(session).forget_audio(learner.id, until=before) == []
    assert await SqlAttemptRepository(session).audio_in_use(sha)
