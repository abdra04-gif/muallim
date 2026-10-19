"""Эталонная запись «как правильно» (FR-20, ADR-0018) и её запись учителем (FR-30, ADR-0024)."""

from dataclasses import dataclass

from muallim.application.ports.repositories import UnitOfWork
from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.ports.system import EventLog
from muallim.domain.learner import Learner


@dataclass(frozen=True, slots=True)
class GetReferenceAudio:
    library: ReferenceAudioLibrary
    uow: UnitOfWork
    events: EventLog

    async def execute(self, learner: Learner, item_id: str) -> bytes | None:
        audio = await self.library.get(item_id)
        if audio is not None:
            # Слушал ли ученик образец перед попыткой — данные для разведки E-7 (ADR-0052).
            await self.events.record("reference_played", learner.id, {"item_id": item_id})
            await self.uow.commit()
        return audio


@dataclass(frozen=True, slots=True)
class RecordReference:
    """Учитель записывает «как правильно» голосовым прямо в боте. Только для teacher_ids."""

    library: ReferenceAudioLibrary
    teacher_ids: frozenset[int]
    uow: UnitOfWork
    events: EventLog

    def allowed(self, learner: Learner) -> bool:
        return learner.telegram_user_id in self.teacher_ids

    async def execute(self, learner: Learner, item_id: str, audio: bytes) -> bool:
        if not self.allowed(learner):
            return False
        await self.library.save(item_id, audio)
        await self.events.record("reference_recorded", learner.id, {"item_id": item_id})
        await self.uow.commit()
        return True
