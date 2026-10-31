"""Чтения сур целиком и наизусть в БД (FR-60, ADR-0076)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import SuraReadingRepository
from muallim.domain.sura import SuraMode, SuraReading
from muallim.infrastructure.db.tables import (
    sura_reading_ayahs,
    sura_reading_chunks,
    sura_reading_events,
    sura_readings,
)


@dataclass(frozen=True, slots=True)
class SqlSuraReadingRepository(SuraReadingRepository):
    session: AsyncSession

    async def add(self, reading: SuraReading) -> None:
        a = reading.assessment
        await self.session.execute(
            insert(sura_readings).values(
                id=reading.id,
                learner_id=reading.learner_id,
                sura=reading.sura,
                mode=reading.mode.value,
                attempt_number=reading.attempt_number,
                days_since_last=reading.days_since_last,
                studied_by_text=reading.studied_by_text,
                clean_ayahs=a.clean_count,
                total_ayahs=len(a.ayahs),
                score=a.score,
                passed=reading.passed,
                credited=list(reading.credited),
                reference_phonemes=a.reference,
                heard_phonemes=a.heard,
                audio_sha256=reading.audio_sha256,
                audio_duration_ms=reading.audio_duration_ms,
                processing_ms=reading.processing_ms,
                model_version=reading.model_version,
                curriculum_version=reading.curriculum_version,
                app_version=reading.app_version,
                policy=None
                if reading.policy is None
                else {
                    "pass_threshold": reading.policy.pass_threshold,
                    "excellent_threshold": reading.policy.excellent_threshold,
                },
                created_at=reading.created_at,
            )
        )
        if a.ayahs:
            await self.session.execute(
                insert(sura_reading_ayahs),
                [
                    {
                        "reading_id": reading.id,
                        "ayah": r.number,
                        "item_id": r.item_id,
                        "outcome": r.outcome.value,
                        "score": r.score,
                        "forgotten_words": r.forgotten_words,
                        "extra_words": r.extra_words,
                        "pronunciation_errors": r.pronunciation_errors,
                        "reference_phonemes": r.reference,
                        "heard_phonemes": r.heard,
                    }
                    for r in a.ayahs
                ],
            )
        if reading.chunks:
            await self.session.execute(
                insert(sura_reading_chunks),
                [
                    {
                        "reading_id": reading.id,
                        "ordinal": n,
                        "start_ms": c.start_ms,
                        "end_ms": c.end_ms,
                        "first_ayah": c.first_ayah,
                        "last_ayah": c.last_ayah,
                        "heard_phonemes": c.heard,
                    }
                    for n, c in enumerate(reading.chunks, start=1)
                ],
            )
        if a.events:
            await self.session.execute(
                insert(sura_reading_events),
                [
                    {
                        "reading_id": reading.id,
                        "ordinal": n,
                        "kind": e.kind.value,
                        "ayah": e.ayah,
                        "word": e.word,
                        "expected": e.expected,
                        "heard": e.heard,
                        "error_kind": e.error_kind.value if e.error_kind else None,
                        "duration_ms": e.duration_ms,
                    }
                    for n, e in enumerate(a.events, start=1)
                ],
            )

    async def count(self, learner_id: UUID, sura: int, mode: SuraMode) -> int:
        query = select(func.count()).where(
            sura_readings.c.learner_id == learner_id,
            sura_readings.c.sura == sura,
            sura_readings.c.mode == mode.value,
        )
        return int(await self.session.scalar(query) or 0)

    async def last_read(self, learner_id: UUID, sura: int) -> datetime | None:
        query = (
            select(sura_readings.c.created_at)
            .where(sura_readings.c.learner_id == learner_id, sura_readings.c.sura == sura)
            .order_by(sura_readings.c.created_at.desc())
            .limit(1)
        )
        found: datetime | None = await self.session.scalar(query)
        return found

    async def memorized(self, learner_id: UUID) -> frozenset[int]:
        query = select(sura_readings.c.sura).where(
            sura_readings.c.learner_id == learner_id,
            sura_readings.c.mode == SuraMode.MEMORY.value,
            sura_readings.c.passed.is_(True),
        )
        return frozenset((await self.session.scalars(query)).all())

    async def credited(self, learner_id: UUID) -> frozenset[str]:
        query = select(sura_readings.c.credited).where(
            sura_readings.c.learner_id == learner_id, sura_readings.c.passed.is_(True)
        )
        return frozenset(i for row in (await self.session.scalars(query)).all() for i in row)

    async def audio_hashes(self, learner_id: UUID) -> list[str]:
        query = select(sura_readings.c.audio_sha256).where(
            sura_readings.c.learner_id == learner_id, sura_readings.c.audio_sha256.is_not(None)
        )
        return list((await self.session.scalars(query)).all())
