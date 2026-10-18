"""Очередь разметки и разметчики по приглашению (FR-17).

Очередь одна для Telegram и пакета Excel (``queue_query``): попытки с записью, реальной моделью и
согласием ученика, которые этот разметчик ещё не размечал. Первыми — оспоренные учеником
(ADR-0020), потом где бот нашёл ошибки, затем новые.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ScalarSelect, Select, and_, delete, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.annotation import AnnotationTasks, AnnotatorDirectory
from muallim.domain.annotation import GUIDE_VERSION, AnnotationTask, Label
from muallim.domain.policy import Verdict
from muallim.infrastructure.db.tables import (
    annotations,
    annotator_invites,
    annotators,
    attempts,
    curriculum_items,
    detected_errors,
    interaction_events,
    learner_reports,
    learners,
)

INVITE_FAILED = "annotator_invite_failed"


def _report() -> ScalarSelect[Any]:
    return (
        select(learner_reports.c.reason)
        .where(learner_reports.c.attempt_id == attempts.c.id)
        .order_by(learner_reports.c.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )


def _tasks() -> Select[Any]:
    """Попытки, которые можно размечать: запись есть, модель настоящая, ученик согласен."""
    return (
        select(
            attempts.c.id, attempts.c.item_id, attempts.c.reference_phonemes,
            attempts.c.heard_phonemes, attempts.c.verdict, attempts.c.audio_sha256,
            curriculum_items.c.text, curriculum_items.c.page, curriculum_items.c.line,
            _report().label("report"),
        )
        .join(learners, learners.c.id == attempts.c.learner_id)
        .outerjoin(
            curriculum_items,
            and_(
                curriculum_items.c.item_id == attempts.c.item_id,
                curriculum_items.c.curriculum_version == attempts.c.curriculum_version,
            ),
        )
        .where(
            attempts.c.audio_sha256.is_not(None),
            attempts.c.model_version != "stub",
            learners.c.research_consent.is_(True),
        )
    )  # fmt: skip


def queue_query(annotator: str) -> Select[Any]:
    own = exists().where(
        annotations.c.attempt_id == attempts.c.id, annotations.c.annotator == annotator
    )
    disputed = exists().where(learner_reports.c.attempt_id == attempts.c.id)
    found_errors = exists().where(detected_errors.c.attempt_id == attempts.c.id)
    return (
        _tasks()
        .where(~own)
        .order_by(disputed.desc(), found_errors.desc(), attempts.c.created_at.desc(), attempts.c.id)
    )


async def bot_errors(
    session: AsyncSession, ids: list[UUID]
) -> dict[UUID, tuple[tuple[str, str], ...]]:
    """Ошибки, найденные ботом, по порядку ответа ученику: (нужно, услышано)."""
    found = await session.execute(
        select(detected_errors.c.attempt_id, detected_errors.c.expected, detected_errors.c.heard)
        .where(detected_errors.c.attempt_id.in_(ids))
        .order_by(detected_errors.c.attempt_id, detected_errors.c.ordinal)
    )
    parts: dict[UUID, list[tuple[str, str]]] = {}
    for attempt_id, expected, heard in found.all():
        parts.setdefault(attempt_id, []).append((expected, heard))
    return {attempt_id: tuple(items) for attempt_id, items in parts.items()}


@dataclass(frozen=True, slots=True)
class SqlAnnotationTasks(AnnotationTasks):
    session: AsyncSession

    async def _one(self, query: Select[Any]) -> AnnotationTask | None:
        row = (await self.session.execute(query.limit(1))).first()
        if row is None:
            return None
        errors = await bot_errors(self.session, [row.id])
        return AnnotationTask(
            attempt_id=row.id, item_id=row.item_id, item_text=row.text or "", page=row.page,
            line=row.line, bot_passed=row.verdict != Verdict.FAILED,
            bot_errors=errors.get(row.id, ()), reference_phonemes=row.reference_phonemes,
            bot_heard=row.heard_phonemes, learner_says=row.report, audio_sha256=row.audio_sha256,
        )  # fmt: skip

    async def next_for(self, annotator: str, exclude: frozenset[UUID]) -> AnnotationTask | None:
        query = queue_query(annotator)
        if exclude:
            query = query.where(attempts.c.id.not_in(exclude))
        return await self._one(query)

    async def get(self, attempt_id: UUID) -> AnnotationTask | None:
        return await self._one(_tasks().where(attempts.c.id == attempt_id))

    async def remaining(self, annotator: str) -> int:
        query = select(func.count()).select_from(queue_query(annotator).order_by(None).subquery())
        return int((await self.session.execute(query)).scalar_one())

    async def add(self, label: Label) -> None:
        await self.session.execute(
            insert(annotations).values(
                attempt_id=label.attempt_id, annotator=label.annotator, label=label.status,
                corrected_phonemes=label.actual, comment=label.comment,
                guide_version=GUIDE_VERSION, source=label.source,
                seconds_spent=label.seconds_spent, created_at=label.created_at,
                self_corrected=label.self_corrected,
            )
        )  # fmt: skip


@dataclass(frozen=True, slots=True)
class SqlAnnotatorDirectory(AnnotatorDirectory):
    session: AsyncSession

    async def bound_code(self, telegram_user_id: int) -> str | None:
        query = select(annotators.c.code).where(annotators.c.telegram_user_id == telegram_user_id)
        code: str | None = (await self.session.execute(query)).scalar_one_or_none()
        return code

    async def is_revoked(self, code: str) -> bool:
        query = select(annotators.c.revoked_at).where(annotators.c.code == code)
        return (await self.session.execute(query)).scalar_one_or_none() is not None

    async def redeem(self, digest: str, telegram_user_id: int, now: datetime) -> str | None:
        # Гасим приглашение одним UPDATE с условием: два одновременных входа не пройдут оба.
        used = await self.session.execute(
            update(annotator_invites)
            .where(
                annotator_invites.c.code_digest == digest,
                annotator_invites.c.used_at.is_(None),
                annotator_invites.c.expires_at > now,
            )
            .values(used_at=now)
            .returning(annotator_invites.c.annotator)
        )
        code: str | None = used.scalar_one_or_none()
        if code is None:
            return None
        # Один Telegram — один код: прежняя привязка этого человека снимается.
        await self.session.execute(
            update(annotators)
            .where(annotators.c.telegram_user_id == telegram_user_id, annotators.c.code != code)
            .values(telegram_user_id=None)
        )
        await self.session.execute(delete(annotators).where(annotators.c.code == code))
        await self.session.execute(
            insert(annotators).values(code=code, telegram_user_id=telegram_user_id, created_at=now)
        )
        return code

    async def failed_redeems(self, learner_id: UUID, since: datetime) -> int:
        query = select(func.count()).where(
            interaction_events.c.event == INVITE_FAILED,
            interaction_events.c.learner_id == learner_id,
            interaction_events.c.created_at >= since,
        )
        return int((await self.session.execute(query)).scalar_one())

    async def add_failed_redeem(self, learner_id: UUID, at: datetime) -> None:
        await self.session.execute(
            insert(interaction_events).values(
                learner_id=learner_id, event=INVITE_FAILED, payload={}, created_at=at
            )
        )
