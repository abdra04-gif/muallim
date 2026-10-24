"""Разметка в Telegram (FR-17, ADR-0041, ADR-0072): доступ разметчика, очередь, метка.

Доступ открыт: кто написал /annotate, тот разметчик с новым кодом (решение автора 2026-10-24,
ADR-0072). Прежние пути — ANNOTATOR_IDS и приглашение — остаются. Отозванный код закрывает доступ
навсегда, и /annotate его не возвращает. Права проверяются при каждом действии, а не один раз при
входе: кнопка того, кто не входил или отозван, ничего не сделает.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from muallim.application.ports.annotation import AnnotationTasks, AnnotatorDirectory
from muallim.application.ports.repositories import UnitOfWork
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import Clock, EventLog
from muallim.domain.annotation import (
    INVITE_LOCK,
    MAX_INVITE_FAILURES,
    USABLE,
    AnnotationSource,
    AnnotationStatus,
    AnnotationTask,
    Label,
    check_label,
    check_phonemes,
    check_self_correction,
    clean_phonemes,
    invite_digest,
)
from muallim.domain.learner import Learner


class NotAnnotatorError(PermissionError):
    """Нет доступа к разметке (не в списке, не приглашён или отозван)."""


NotAnnotator = NotAnnotatorError


@dataclass(frozen=True, slots=True)
class AnnotatorAccess:
    directory: AnnotatorDirectory
    configured: Mapping[int, str]  # Telegram ID → код из ANNOTATOR_IDS

    async def code_for(self, telegram_user_id: int) -> str | None:
        code = self.configured.get(telegram_user_id) or await self.directory.bound_code(
            telegram_user_id
        )
        if code is None or await self.directory.is_revoked(code):
            return None
        return code

    async def require(self, learner: Learner) -> str:
        code = await self.code_for(learner.telegram_user_id)
        if code is None:
            raise NotAnnotatorError
        return code


class RedeemResult(StrEnum):
    GRANTED = "granted"
    INVALID = "invalid"  # нет такого, истекло или уже использовано
    LOCKED = "locked"  # слишком много неверных кодов за час


@dataclass(frozen=True, slots=True)
class RedeemInvite:
    directory: AnnotatorDirectory
    uow: UnitOfWork
    events: EventLog
    clock: Clock

    async def execute(self, learner: Learner, code: str) -> tuple[RedeemResult, str | None]:
        now = self.clock.now()
        if (
            await self.directory.failed_redeems(learner.id, now - INVITE_LOCK)
            >= MAX_INVITE_FAILURES
        ):
            return RedeemResult.LOCKED, None
        annotator = await self.directory.redeem(invite_digest(code), learner.telegram_user_id, now)
        if annotator is None:
            await self.directory.add_failed_redeem(learner.id, now)
            await self.uow.commit()
            return RedeemResult.INVALID, None
        await self.events.record("annotator_invite_redeemed", learner.id, {"annotator": annotator})
        await self.uow.commit()
        return RedeemResult.GRANTED, annotator


@dataclass(frozen=True, slots=True)
class JoinAnnotation:
    """Вход по /annotate без кода и ID (ADR-0072). Отозванного не пускает снова."""

    access: AnnotatorAccess
    directory: AnnotatorDirectory
    uow: UnitOfWork
    events: EventLog
    clock: Clock

    async def execute(self, learner: Learner) -> tuple[str, bool] | None:
        """(код, впервые ли) или None — доступ этому человеку закрыт исследователем."""
        tg = learner.telegram_user_id
        if (code := await self.access.code_for(tg)) is not None:
            return code, False
        if tg in self.access.configured or await self.directory.bound_code(tg) is not None:
            return None  # код был, но отозван
        code = await self.directory.register(
            tg, frozenset(self.access.configured.values()), self.clock.now()
        )
        await self.events.record("annotator_joined", learner.id, {"annotator": code})
        await self.uow.commit()
        return code, True


@dataclass(frozen=True, slots=True)
class ShownTask:
    annotator: str
    task: AnnotationTask
    audio: bytes
    remaining: int  # сколько ещё в очереди, включая эту


@dataclass(frozen=True, slots=True)
class NextAnnotation:
    access: AnnotatorAccess
    tasks: AnnotationTasks
    audio: AudioStore
    events: EventLog
    uow: UnitOfWork

    async def execute(
        self, learner: Learner, exclude: frozenset[UUID] = frozenset()
    ) -> ShownTask | None:
        annotator = await self.access.require(learner)
        skipped = set(exclude)
        while (task := await self.tasks.next_for(annotator, frozenset(skipped))) is not None:
            audio = await self.audio.read(task.audio_sha256)
            if audio is not None:
                remaining = await self.tasks.remaining(annotator)
                await self.events.record(
                    "annotation_shown", learner.id,
                    {"annotator": annotator, "attempt_id": str(task.attempt_id)},
                )  # fmt: skip
                await self.uow.commit()
                return ShownTask(annotator, task, audio, remaining)
            skipped.add(task.attempt_id)  # файла нет — покажет muallim-research verify
        return None

    async def again(self, learner: Learner, attempt_id: UUID) -> ShownTask | None:
        """«↩️ Переделать»: та же запись ещё раз. Новая метка ляжет рядом, в данных — последняя.

        None — записи больше нет (ученик удалил данные или отозвал согласие) или нет файла.
        """
        annotator = await self.access.require(learner)
        task = await self.tasks.get(attempt_id)
        audio = await self.audio.read(task.audio_sha256) if task is not None else None
        if task is None or audio is None:
            return None
        remaining = await self.tasks.remaining(annotator)
        await self.events.record(
            "annotation_redo", learner.id, {"annotator": annotator, "attempt_id": str(attempt_id)}
        )
        await self.uow.commit()
        return ShownTask(annotator, task, audio, remaining)


@dataclass(frozen=True, slots=True)
class SubmitAnnotation:
    access: AnnotatorAccess
    tasks: AnnotationTasks
    uow: UnitOfWork
    events: EventLog
    clock: Clock

    async def execute(
        self,
        learner: Learner,
        attempt_id: UUID,
        status: AnnotationStatus,
        *,
        actual: str | None = None,
        comment: str = "",
        seconds_spent: int | None = None,
        self_corrected: bool = False,
    ) -> bool:
        """Сохраняет метку. False — попытки больше нет (ученик удалил данные или отозвал согласие).

        LabelError — метка противоречит руководству (текст — подсказка разметчику).
        """
        annotator = await self.access.require(learner)
        task = await self.tasks.get(attempt_id)
        if task is None:
            return False
        phonemes: str | None = None
        if status is AnnotationStatus.AGREE:
            phonemes = task.bot_heard
        elif status in USABLE:
            phonemes = clean_phonemes(actual or "")
            check_phonemes(phonemes)
        check_label(status, phonemes, task.bot_heard)
        check_self_correction(status, self_corrected=self_corrected)
        await self.tasks.add(
            Label(
                attempt_id, annotator, status, phonemes, comment.strip(),
                AnnotationSource.TELEGRAM, seconds_spent, self.clock.now(), self_corrected,
            )
        )  # fmt: skip
        await self.events.record(
            "annotation_submitted", learner.id,
            {"annotator": annotator, "attempt_id": str(attempt_id), "status": str(status)},
        )  # fmt: skip
        await self.uow.commit()
        return True
