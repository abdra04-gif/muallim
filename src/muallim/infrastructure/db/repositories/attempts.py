from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import AttemptRepository
from muallim.domain.assessment import Assessment, ErrorKind, PronunciationError
from muallim.domain.attempt import Attempt
from muallim.domain.report import LearnerReport
from muallim.infrastructure.db.tables import (
    annotations,
    attempts,
    detected_errors,
    learner_reports,
)


@dataclass(frozen=True, slots=True)
class SqlAttemptRepository(AttemptRepository):
    session: AsyncSession

    async def add(self, attempt: Attempt, feedback: tuple[str, ...]) -> None:
        a = attempt.assessment
        await self.session.execute(
            insert(attempts).values(
                id=attempt.id,
                learner_id=attempt.learner_id,
                item_id=attempt.item_id,
                curriculum_version=attempt.curriculum_version,
                model_version=attempt.model_version,
                reference_phonemes=a.reference,
                heard_phonemes=a.heard,
                score=a.score,
                verdict=attempt.verdict,
                audio_sha256=attempt.audio_sha256,
                audio_duration_ms=attempt.audio_duration_ms,
                processing_ms=attempt.processing_ms,
                created_at=attempt.created_at,
                reference_variant=attempt.reference_variant or None,
                candidates=[
                    {
                        "variant": c.variant,
                        "reference": c.assessment.reference,
                        "score": c.assessment.score,
                    }
                    for c in attempt.candidates
                ],
                model_output=dict(attempt.model_output),
                policy={
                    "pass_threshold": attempt.policy.pass_threshold,
                    "excellent_threshold": attempt.policy.excellent_threshold,
                },
                app_version=attempt.app_version or None,
                feedback_language=attempt.feedback_language,
            )
        )
        if a.errors:
            await self.session.execute(
                insert(detected_errors),
                [
                    {
                        "attempt_id": attempt.id,
                        "ordinal": i,
                        "kind": e.kind,
                        "position": e.position,
                        "syllable": e.syllable,
                        "expected": e.expected,
                        "heard": e.heard,
                        "message": message,
                    }
                    for i, (e, message) in enumerate(zip(a.errors, feedback, strict=True))
                ],
            )

    async def best_scores(self, learner_id: UUID) -> Mapping[str, int]:
        query = (
            select(attempts.c.item_id, func.max(attempts.c.score))
            .where(attempts.c.learner_id == learner_id)
            .group_by(attempts.c.item_id)
        )
        return dict((await self.session.execute(query)).all())

    async def last_assessment(self, learner_id: UUID, item_id: str) -> Assessment | None:
        query = (
            select(attempts.c.id, attempts.c.reference_phonemes, attempts.c.heard_phonemes,
                   attempts.c.score)
            .where(attempts.c.learner_id == learner_id, attempts.c.item_id == item_id)
            .order_by(attempts.c.created_at.desc())
            .limit(1)
        )  # fmt: skip
        row = (await self.session.execute(query)).one_or_none()
        if row is None:
            return None
        found = await self.session.execute(
            select(detected_errors)
            .where(detected_errors.c.attempt_id == row.id)
            .order_by(detected_errors.c.ordinal)
        )
        errors = tuple(
            PronunciationError(ErrorKind(e.kind), e.position, e.syllable, e.expected, e.heard)
            for e in found.all()
        )
        return Assessment(row.reference_phonemes, row.heard_phonemes, row.score, errors)

    async def count(self, learner_id: UUID) -> int:
        query = (
            select(func.count()).select_from(attempts).where(attempts.c.learner_id == learner_id)
        )
        return int(await self.session.scalar(query) or 0)

    async def audio_hashes(self, learner_id: UUID) -> list[str]:
        query = select(attempts.c.audio_sha256).where(
            attempts.c.learner_id == learner_id, attempts.c.audio_sha256.is_not(None)
        )
        return list((await self.session.scalars(query)).all())

    async def forget_audio(self, learner_id: UUID, until: datetime | None = None) -> list[str]:
        scope = attempts.c.learner_id == learner_id
        if until is not None:
            scope = scope & (attempts.c.created_at <= until)
        hashes = await self.session.scalars(
            select(attempts.c.audio_sha256).where(scope, attempts.c.audio_sha256.is_not(None))
        )
        found = sorted(set(hashes.all()))
        own = select(attempts.c.id).where(scope)
        # Разметка — производная от голоса (метки ставились, слушая запись): удаляется с ней.
        await self.session.execute(delete(annotations).where(annotations.c.attempt_id.in_(own)))
        await self.session.execute(update(attempts).where(scope).values(audio_sha256=None))
        return found

    async def audio_in_use(self, sha256: str) -> bool:
        query = select(attempts.c.id).where(attempts.c.audio_sha256 == sha256).limit(1)
        return await self.session.scalar(query) is not None

    async def activity(self, learner_id: UUID) -> Mapping[date, int]:
        # Дату считаем в Python: так одинаково в PostgreSQL и SQLite (UTC, ADR-0004).
        query = select(attempts.c.created_at).where(attempts.c.learner_id == learner_id)
        days: dict[date, int] = {}
        for created in (await self.session.scalars(query)).all():
            days[created.date()] = days.get(created.date(), 0) + 1
        return days

    async def owner(self, attempt_id: UUID) -> UUID | None:
        query = select(attempts.c.learner_id).where(attempts.c.id == attempt_id)
        return await self.session.scalar(query)

    async def add_report(self, report: LearnerReport) -> None:
        await self.session.execute(
            insert(learner_reports).values(
                attempt_id=report.attempt_id,
                learner_id=report.learner_id,
                reason=report.reason,
                created_at=report.at,
            )
        )
