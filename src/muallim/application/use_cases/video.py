"""Ролик «🎬 Как произносить» (FR-56, ADR-0074): отдать ролик и записать просмотр.

Ролик отдаётся без записи в журнал: ушёл ли он в Telegram, знает только presentation. Просмотр
(``video_played``) пишется после успешной отправки — сбой отправки события не оставляет.
"""

from dataclasses import dataclass

from muallim.application.ports.repositories import UnitOfWork
from muallim.application.ports.storage import ArticulationVideoLibrary, Video
from muallim.application.ports.system import EventLog
from muallim.domain.learner import Learner


@dataclass(frozen=True, slots=True)
class GetArticulationVideo:
    library: ArticulationVideoLibrary

    async def execute(self, key: str) -> Video | None:
        return await self.library.get(key)


@dataclass(frozen=True, slots=True)
class RecordVideoPlayed:
    """``source`` — откуда показан: card, auto, after (``from`` в журнале;
    breakdown и sheet — только у старых кнопок, ADR-0074)."""

    uow: UnitOfWork
    events: EventLog

    async def execute(
        self,
        learner: Learner,
        key: str,
        *,
        source: str,
        item_id: str | None = None,
        letter: str | None = None,
    ) -> None:
        payload: dict[str, str | int | None] = {"video": key}
        if item_id is not None:
            payload["item_id"] = item_id
        if letter is not None:
            payload["letter"] = letter
        payload["from"] = source
        await self.events.record("video_played", learner.id, payload)
        await self.uow.commit()
