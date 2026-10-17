"""Регистрация ученика, согласие на исследование, удаление данных."""

from dataclasses import dataclass

from muallim.application.feedback import FeedbackCatalog
from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerRepository,
    UnitOfWork,
)
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import Clock, EventLog, IdGenerator
from muallim.domain.learner import ConsentKind, ConsentRecord, Learner

# Меняйте версию при каждом изменении текста согласия в presentation/telegram/texts.py.
CONSENT_TEXT_VERSION = "2026-10-17"


@dataclass(frozen=True, slots=True)
class EnsureLearner:
    learners: LearnerRepository
    uow: UnitOfWork
    clock: Clock
    ids: IdGenerator
    events: EventLog

    async def execute(self, telegram_user_id: int, language: str | None) -> tuple[Learner, bool]:
        """Возвращает ученика и признак «зарегистрирован только что»."""
        learner = await self.learners.get_by_telegram_id(telegram_user_id)
        if learner is not None:
            return learner, False
        learner_id = self.ids.new_id()
        learner = Learner(
            id=learner_id,
            telegram_user_id=telegram_user_id,
            pseudonym=f"L-{learner_id.hex[:8]}",
            language=(language or "ru")[:8],
            created_at=self.clock.now(),
        )
        await self.learners.add(learner)
        await self.events.record("learner_registered", learner.id, {})
        await self.uow.commit()
        return learner, True


@dataclass(frozen=True, slots=True)
class SetResearchConsent:
    learners: LearnerRepository
    uow: UnitOfWork
    clock: Clock
    events: EventLog

    async def execute(self, learner: Learner, granted: bool) -> None:
        learner.research_consent = granted
        await self.learners.save(learner)
        await self.learners.add_consent(
            ConsentRecord(
                learner_id=learner.id,
                kind=ConsentKind.RESEARCH_AUDIO,
                granted=granted,
                text_version=CONSENT_TEXT_VERSION,
                at=self.clock.now(),
            )
        )
        await self.events.record("consent_changed", learner.id, {"granted": int(granted)})
        await self.uow.commit()


@dataclass(frozen=True, slots=True)
class DeleteMyData:
    learners: LearnerRepository
    attempts: AttemptRepository
    audio: AudioStore
    uow: UnitOfWork
    events: EventLog

    async def execute(self, learner: Learner) -> None:
        for sha in await self.attempts.audio_hashes(learner.id):
            await self.audio.delete(sha)
        await self.learners.delete(learner.id)
        # Факт удаления фиксируем без привязки к ученику: его записи больше нет.
        await self.events.record("learner_deleted", None, {})
        await self.uow.commit()


@dataclass(frozen=True, slots=True)
class SetFeedbackLanguage:
    """Выбор языка объяснений ошибок (FR-22). Только среди включённых языков."""

    learners: LearnerRepository
    catalog: FeedbackCatalog
    uow: UnitOfWork
    events: EventLog

    async def execute(self, learner: Learner, code: str) -> bool:
        if code not in self.catalog.enabled():
            return False
        learner.feedback_language = code
        await self.learners.save(learner)
        await self.events.record("feedback_language_set", learner.id, {"language": code})
        await self.uow.commit()
        return True
