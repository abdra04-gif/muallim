"""Повтор журнала удалений после восстановления копии БД (TD-DB-05, ADR-0054).

Журнал повторяется целиком и по порядку — результат тот же, сколько раз ни запускай:
- ``delete`` — ученик и всё его удаляется (каскад), записи — после commit;
- ``withdraw`` — согласие снято, записи и разметка по ним до момента отзыва удаляются;
- ``grant`` — согласие снова включается, только если в БД есть запись о нём (``consents``) позже
  отзыва: копия старше согласия — ученик даст его заново; записи после согласия не трогаются.
Ученика, которого нет в БД (уже удалён или появился после копии), пропускаем. Считаются только
настоящие изменения.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.erasures import ErasureAction
from muallim.application.use_cases.learners import delete_unused_audio
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import consents, learners
from muallim.infrastructure.erasures import read_erasures


@dataclass(frozen=True, slots=True)
class ReapplyResult:
    deleted: int
    withdrawn: int
    granted: int
    files_deleted: int


async def reapply(session: AsyncSession, log_path: Path, audio_root: Path) -> ReapplyResult:
    attempts, people = SqlAttemptRepository(session), SqlLearnerRepository(session)
    hashes: set[str] = set()
    done = dict.fromkeys(ErasureAction, 0)
    withdrawn_at: dict[UUID, datetime] = {}
    for entry in read_erasures(log_path):
        consent = await session.scalar(
            select(learners.c.research_consent).where(learners.c.id == entry.learner_id)
        )
        if consent is None:
            continue
        if entry.action is ErasureAction.DELETE:
            hashes.update(await attempts.audio_hashes(entry.learner_id))
            await people.delete(entry.learner_id)
            done[entry.action] += 1
        elif entry.action is ErasureAction.WITHDRAW:
            withdrawn_at[entry.learner_id] = entry.at
            forgotten = await attempts.forget_audio(entry.learner_id, until=entry.at)
            await _set_consent(session, entry.learner_id, granted=False)
            hashes.update(forgotten)
            done[entry.action] += bool(consent or forgotten)
        elif not consent and await _granted_after(
            session, entry.learner_id, withdrawn_at.get(entry.learner_id)
        ):
            await _set_consent(session, entry.learner_id, granted=True)
            done[entry.action] += 1
    await session.commit()
    files = await delete_unused_audio(hashes, attempts, FileAudioStore(audio_root))
    return ReapplyResult(
        done[ErasureAction.DELETE], done[ErasureAction.WITHDRAW], done[ErasureAction.GRANT], files
    )


async def _set_consent(session: AsyncSession, learner_id: UUID, *, granted: bool) -> None:
    await session.execute(
        update(learners).where(learners.c.id == learner_id).values(research_consent=granted)
    )


async def _granted_after(session: AsyncSession, learner_id: UUID, since: datetime | None) -> bool:
    """Есть ли в БД согласие позже отзыва (без отзыва в журнале — любое)."""
    query = select(consents.c.id).where(
        consents.c.learner_id == learner_id, consents.c.granted.is_(True)
    )
    if since is not None:
        query = query.where(consents.c.at > since)
    return await session.scalar(query.limit(1)) is not None
