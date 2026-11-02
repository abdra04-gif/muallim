"""Сура целиком и наизусть (FR-57…FR-60, ADR-0076): проверить, засчитать, сохранить.

По тексту: все аяты чистые → засчитаны все уроки суры («всё или ничего», FR-58). Наизусть:
все аяты чистые → отметка 🧠, уроки не засчитываются (FR-59).
"""

import time
from dataclasses import dataclass

from muallim.application.ports.recognition import RecognitionError, SuraRecognizer
from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerRepository,
    SuraReadingRepository,
    UnitOfWork,
)
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import BuildInfo, Clock, EventLog, IdGenerator
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.domain.sura import (
    ReadingChunk,
    Sura,
    SuraMode,
    SuraReading,
    assess_sura,
    suras,
)

ISTIADHA_ITEM = "L001-02"  # «أَعُوذُ بِٱللَّهِ…» — урок 1, начало занятия (ADR-0050)


@dataclass(frozen=True, slots=True)
class SuraReadingResult:
    sura: Sura
    reading: SuraReading


@dataclass(frozen=True, slots=True)
class ReadSura:
    curriculum: Curriculum
    recognizer: SuraRecognizer
    readings: SuraReadingRepository
    attempts: AttemptRepository
    audio: AudioStore
    policy: GradingPolicy
    uow: UnitOfWork
    clock: Clock
    ids: IdGenerator
    events: EventLog
    build: BuildInfo
    learners: LearnerRepository  # сдал суру — «Продолжить» за неё (автор 2026-10-31)

    async def memorized(self, learner: Learner) -> frozenset[int]:
        """Суры, прочитанные наизусть без ошибок (отметка в списке)."""
        return await self.readings.memorized(learner.id)

    async def _move_past(self, learner: Learner, sura: Sura) -> None:
        """«Продолжить» — на урок после суры, если ученик был в ней или раньше; назад — нет."""
        last = sura.lessons[-1].items[-1]
        following = self.curriculum.next_item(last.id)
        if following is None:
            return
        order = [i.id for lesson in self.curriculum.lessons for i in lesson.items]
        current = learner.current_item_id
        if current in order and order.index(current) > order.index(last.id):
            return
        learner.current_item_id = following.id
        await self.learners.save(learner)

    def _istiadha(self) -> str:
        """Истиаза из урока 1 — необязательное начало перед сурой (ревью кода 2026-10-31)."""
        try:
            return self.curriculum.item(ISTIADHA_ITEM).text
        except KeyError:
            return ""

    def sura(self, number: int) -> Sura:
        for sura in suras(self.curriculum):
            if sura.number == number:
                return sura
        raise KeyError(number)

    async def execute(
        self, learner: Learner, audio: bytes, number: int, mode: SuraMode
    ) -> SuraReadingResult:
        sura = self.sura(number)
        items = tuple(i for lesson in sura.lessons for i in lesson.practice_items)
        best = await self.attempts.best_scores(learner.id)
        studied = bool(items) and all(self.policy.is_mastered(best.get(i.id, 0)) for i in items)
        ayahs = [(a.id, int(a.quran.split(":")[1]), a.text) for a in sura.ayahs]
        opening = sura.opening.text if sura.opening else ""
        preamble = self._istiadha()

        started = time.perf_counter()
        try:
            recognition = await self.recognizer.recognize_sura(audio, ayahs, opening, preamble)
        except RecognitionError as error:
            await self.events.record(
                "sura_recognition_failed",
                learner.id,
                {
                    "sura": number,
                    "mode": mode.value,
                    "stage": error.stage,
                    "processing_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            await self.uow.commit()
            raise
        assessment = assess_sura(
            recognition.ayahs,
            recognition.heard,
            self.policy,
            opening=recognition.opening,
            preamble=recognition.preamble,
            pauses=recognition.pauses,
        )
        processing_ms = round((time.perf_counter() - started) * 1000)

        count = await self.readings.count(learner.id, number, mode)
        last = await self.readings.last_read(learner.id, number)
        now = self.clock.now()
        # Запись храним только с согласия ученика (FR-09, docs/security/privacy.md).
        audio_sha = await self.audio.save(audio) if learner.research_consent else None
        chunks = tuple(
            ReadingChunk(begin, end, recognition.heard[a:b], *assessment.ayahs_between(a, b))
            for begin, end, a, b in recognition.chunks
        )
        credited = (
            tuple(i.id for i in items) if mode is SuraMode.TEXT and assessment.complete else ()
        )
        reading = SuraReading(
            id=self.ids.new_id(),
            learner_id=learner.id,
            sura=number,
            mode=mode,
            attempt_number=count + 1,
            days_since_last=None if last is None else (now - last).days,
            studied_by_text=studied,
            assessment=assessment,
            chunks=chunks,
            credited=credited,
            model_version=recognition.model_version,
            curriculum_version=self.curriculum.version,
            app_version=self.build.version,
            audio_sha256=audio_sha,
            audio_duration_ms=recognition.audio_duration_ms,
            processing_ms=processing_ms,
            created_at=now,
            policy=self.policy,
        )
        await self.readings.add(reading)
        if credited:
            await self._move_past(learner, sura)
        await self.events.record(
            "sura_read",
            learner.id,
            {
                "sura": number,
                "mode": mode.value,
                "clean": assessment.clean_count,
                "total": len(assessment.ayahs),
                "passed": int(reading.passed),
            },
        )
        await self.uow.commit()
        return SuraReadingResult(sura, reading)
