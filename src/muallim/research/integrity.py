"""Сверка БД и файлов записей (NFR-TR-03): ничего не потеряно, лишнего не хранится.

- ``missing`` — попытка ссылается на запись, а файла нет (потеря данных);
- ``orphans`` — файл есть, а попытки нет (голос, который нельзя удалить кнопкой «удалить мои
  данные»: остаётся после сбоя между сохранением файла и записью в БД или после сбоя удаления);
- ``corrupted`` — SHA-256 файла не совпадает с именем (файл повреждён или подменён);
- ``without_consent`` — у ученика без согласия остались записи (так быть не должно, privacy.md);
- ``stale_copies`` — копии в пакетах разметки и выгрузках, которые больше нельзя хранить: попытки
  нет (ученик удалил данные) или ученик отозвал согласие. Удаляет исследователь;
- ``pending_erasures`` — журнал удалений говорит «удалить» или «согласие отозвано», а в БД это не
  так (восстановили старую копию): ``muallim-research reapply-erasures``.

Выводятся только SHA-256 — без псевдонимов и Telegram ID.
"""

import hashlib
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.erasures import ErasureAction
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.db.tables import attempts, learners, sura_readings
from muallim.infrastructure.erasures import read_erasures


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    missing: list[str]
    orphans: list[str]
    corrupted: list[str]
    without_consent: int
    checked: int  # файлов проверено
    stale_copies: list[str] = field(default_factory=list)
    pending_erasures: int = 0

    @property
    def ok(self) -> bool:
        problems = (self.missing, self.orphans, self.corrupted, self.stale_copies)
        return not (any(problems) or self.without_consent or self.pending_erasures)


_SHA = re.compile(r"[0-9a-f]{64}")
MIN_ORPHAN_AGE_S = 600  # бот пишет файл до commit попытки: свежий «лишний» может стать нужным


def _stored(audio_root: Path) -> dict[str, Path]:
    if not audio_root.is_dir():
        return {}
    return {p.stem: p for p in audio_root.glob("*/*.ogg") if _SHA.fullmatch(p.stem)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Все таблицы со ссылкой на запись голоса: попытки по карточкам и чтения сур (FR-60, ADR-0076).
# Новая таблица с audio_sha256 — сюда, иначе verify сочтёт её записи лишними.
_VOICE_TABLES = (attempts, sura_readings)


async def _hashes(session: AsyncSession, consent: bool | None = None) -> set[str]:
    """Хеши всех записей; ``consent`` — только у учеников с согласием (True) или без (False)."""
    found: set[str] = set()
    for table in _VOICE_TABLES:
        query = select(table.c.audio_sha256).where(table.c.audio_sha256.is_not(None))
        if consent is not None:
            query = query.join(learners, learners.c.id == table.c.learner_id).where(
                learners.c.research_consent.is_(consent)
            )
        found.update((await session.scalars(query)).all())
    return found


async def _count(session: AsyncSession, *, consent: bool | None = None) -> int:
    total = 0
    for table in _VOICE_TABLES:
        query = select(func.count()).select_from(table).where(table.c.audio_sha256.is_not(None))
        if consent is not None:
            query = query.join(learners, learners.c.id == table.c.learner_id).where(
                learners.c.research_consent.is_(consent)
            )
        total += int(await session.scalar(query) or 0)
    return total


async def _in_use(session: AsyncSession, sha: str) -> bool:
    for table in _VOICE_TABLES:
        query = select(table.c.id).where(table.c.audio_sha256 == sha).limit(1)
        if await session.scalar(query) is not None:
            return True
    return False


async def check(
    session: AsyncSession,
    audio_root: Path,
    copies: Iterable[Path] = (),
    erasure_log: Path | None = None,
) -> IntegrityReport:
    """``copies`` — папки с копиями записей (data/annotation, data/exports)."""
    consented = await _hashes(session, consent=True)
    stale = sorted(
        str(p)
        for root in copies
        if root.is_dir()
        for p in root.rglob("*.ogg")
        if _SHA.fullmatch(p.stem) and p.stem not in consented
    )
    referenced = await _hashes(session)
    without_consent = await _count(session, consent=False)
    files = _stored(audio_root)
    return IntegrityReport(
        missing=sorted(referenced - files.keys()),
        orphans=sorted(files.keys() - referenced),
        corrupted=sorted(sha for sha, path in files.items() if _sha256(path) != sha),
        without_consent=int(without_consent or 0),
        checked=len(files),
        stale_copies=stale,
        pending_erasures=await _pending(session, erasure_log) if erasure_log else 0,
    )


async def _pending(session: AsyncSession, erasure_log: Path) -> int:
    """Ученики, чьё последнее действие в журнале — удаление или отзыв, а в БД это не так."""
    last = {e.learner_id: e for e in read_erasures(erasure_log)}
    if not last:
        return 0
    rows = await session.execute(
        select(learners.c.id, learners.c.research_consent).where(learners.c.id.in_(last))
    )
    pending = 0
    for learner_id, consent in rows.all():
        entry = last[learner_id]
        if entry.action is ErasureAction.DELETE:
            pending += 1
        elif entry.action is ErasureAction.WITHDRAW:
            kept = 0
            for table in _VOICE_TABLES:
                kept += int(
                    await session.scalar(
                        select(func.count())
                        .select_from(table)
                        .where(
                            table.c.learner_id == learner_id,
                            table.c.audio_sha256.is_not(None),
                            table.c.created_at <= entry.at,
                        )
                    )
                    or 0
                )
            pending += bool(consent or kept)
    return pending


async def delete_orphans(
    session: AsyncSession,
    report: IntegrityReport,
    audio_root: Path,
    min_age_s: float = MIN_ORPHAN_AGE_S,
) -> int:
    """Удаляет файлы без попыток. Запускает человек: это голоса учеников (CLAUDE.md).

    Свежие файлы не трогаем, и перед каждым удалением ещё раз спрашиваем БД: бот мог как раз
    сохранить попытку с этой записью.
    """
    store, now, deleted = FileAudioStore(audio_root), time.time(), 0
    for sha in report.orphans:
        path = store.path_for(sha)
        if not path.exists() or now - path.stat().st_mtime < min_age_s:
            continue
        if not await _in_use(session, sha):
            path.unlink(missing_ok=True)
            deleted += 1
    return deleted


def render(report: IntegrityReport) -> str:
    if report.ok:
        return f"Хранилище в порядке: файлов {report.checked}, все на месте и целы."
    lines = [f"Проверено файлов: {report.checked}"]
    sections = (
        ("Нет файла (потеря данных — восстановить из копии)", report.missing),
        ("Лишний файл без попытки (удалить: verify --delete-orphans)", report.orphans),
        ("Файл повреждён (SHA-256 не совпадает — восстановить из копии)", report.corrupted),
    )
    for title, items in sections:
        if items:
            lines += [f"{title}: {len(items)}", *(f"  {sha}" for sha in items)]
    if report.without_consent:
        lines.append(f"Записей у учеников без согласия: {report.without_consent}")
    if report.pending_erasures:
        lines.append(
            f"Не применены удаления из журнала: {report.pending_erasures} "
            "(восстановлена старая копия?) — muallim-research reapply-erasures"
        )
    if report.stale_copies:
        lines += [
            f"Копии, которые больше нельзя хранить (удалить вручную): {len(report.stale_copies)}",
            *(f"  {path}" for path in report.stale_copies),
        ]
    return "\n".join(lines)
