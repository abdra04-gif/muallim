"""Системные реализации портов времени и идентификаторов."""

import uuid
from datetime import UTC, datetime

from muallim.application.ports.system import Clock, IdGenerator


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class RandomIdGenerator(IdGenerator):
    def new_id(self) -> uuid.UUID:
        return uuid.uuid4()
