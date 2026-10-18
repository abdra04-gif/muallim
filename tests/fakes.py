"""Тестовые реализации портов: в памяти, детерминированные."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from muallim.application.ports.recognition import Recognition, RecognitionError
from muallim.domain.assessment import Assessment
from muallim.domain.attempt import Attempt
from muallim.domain.learner import ConsentRecord, Learner, LearnerProfile
from muallim.domain.report import LearnerReport


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


class SequentialIds:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


@dataclass
class InMemoryLearners:
    by_tg: dict[int, Learner] = field(default_factory=dict)
    consents: list[ConsentRecord] = field(default_factory=list)

    async def get_by_telegram_id(self, telegram_user_id: int) -> Learner | None:
        return self.by_tg.get(telegram_user_id)

    async def add(self, learner: Learner) -> None:
        self.by_tg[learner.telegram_user_id] = learner

    async def save(self, learner: Learner) -> None:
        self.by_tg[learner.telegram_user_id] = learner

    async def add_consent(self, record: ConsentRecord) -> None:
        self.consents.append(record)

    async def delete(self, learner_id: UUID) -> None:
        self.by_tg = {k: v for k, v in self.by_tg.items() if v.id != learner_id}
        self.consents = [c for c in self.consents if c.learner_id != learner_id]


@dataclass
class InMemoryProfiles:
    """Анкета ученика (FR-44): одна на ученика."""

    by_learner: dict[UUID, LearnerProfile] = field(default_factory=dict)

    async def get(self, learner_id: UUID) -> LearnerProfile | None:
        return self.by_learner.get(learner_id)

    async def add(self, profile: LearnerProfile) -> None:
        self.by_learner[profile.learner_id] = profile


@dataclass
class InMemoryAttempts:
    items: list[tuple[Attempt, tuple[str, ...]]] = field(default_factory=list)
    reports: list[LearnerReport] = field(default_factory=list)

    async def owner(self, attempt_id: UUID) -> UUID | None:
        return next((a.learner_id for a, _ in self.items if a.id == attempt_id), None)

    async def add_report(self, report: LearnerReport) -> None:
        self.reports.append(report)

    async def add(self, attempt: Attempt, feedback: tuple[str, ...]) -> None:
        # как в БД: у каждой ошибки — свой текст (detected_errors, zip strict)
        assert len(feedback) == len(attempt.assessment.errors)
        self.items.append((attempt, feedback))

    async def last_assessment(self, learner_id: UUID, item_id: str) -> Assessment | None:
        return next(
            (
                a.assessment
                for a, _ in reversed(self.items)
                if a.learner_id == learner_id and a.item_id == item_id
            ),
            None,
        )

    async def best_scores(self, learner_id: UUID) -> Mapping[str, int]:
        best: dict[str, int] = {}
        for a, _ in self.items:
            if a.learner_id == learner_id:
                best[a.item_id] = max(best.get(a.item_id, 0), a.assessment.score)
        return best

    async def count(self, learner_id: UUID) -> int:
        return sum(1 for a, _ in self.items if a.learner_id == learner_id)

    async def audio_hashes(self, learner_id: UUID) -> list[str]:
        return [
            a.audio_sha256 for a, _ in self.items if a.learner_id == learner_id and a.audio_sha256
        ]

    async def activity(self, learner_id: UUID) -> Mapping[date, int]:
        days: dict[date, int] = {}
        for a, _ in self.items:
            if a.learner_id == learner_id:
                day = a.created_at.date()
                days[day] = days.get(day, 0) + 1
        return days


@dataclass
class InMemoryAudio:
    files: dict[str, bytes] = field(default_factory=dict)

    async def save(self, audio: bytes) -> str:
        import hashlib  # noqa: PLC0415

        sha = hashlib.sha256(audio).hexdigest()
        self.files[sha] = audio
        return sha

    async def delete(self, sha256: str) -> None:
        self.files.pop(sha256, None)


@dataclass
class ScriptedRecognizer:
    """Возвращает заранее заданное «услышанное»; эталон — текст карточки."""

    heard: str | None = None
    fail: bool = False
    fail_stage: str = "model"

    async def recognize(self, audio: bytes, text: str) -> Recognition:
        if self.fail:
            raise RecognitionError("битая запись", stage=self.fail_stage)
        heard = text if self.heard is None else self.heard
        return Recognition(
            heard=heard,
            references=(("wasl", text + "\u064e"), ("waqf", text)),
            model_version="scripted",
            audio_duration_ms=1500,
            raw={"phonemes": heard},
        )


@dataclass
class SpyUoW:
    commits: int = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


@dataclass
class ListEventLog:
    events: list[tuple[str, UUID | None, dict[str, str | int | None]]] = field(default_factory=list)

    async def record(
        self, event: str, learner_id: UUID | None, payload: dict[str, str | int | None]
    ) -> None:
        self.events.append((event, learner_id, payload))


@dataclass
class InMemoryReferenceAudio:
    files: dict[str, bytes] = field(default_factory=dict)

    def has(self, item_id: str) -> bool:
        return item_id in self.files

    async def get(self, item_id: str) -> bytes | None:
        return self.files.get(item_id)

    async def save(self, item_id: str, audio: bytes) -> None:
        self.files[item_id] = audio


@dataclass
class ScriptedReadingGuide:
    """«Как читается» без фонетизатора: фонемы = текст карточки без пробелов; None — не умеет."""

    fail: bool = False

    def phonemes(self, text: str) -> str | None:
        return None if self.fail else text.replace(" ", "")
