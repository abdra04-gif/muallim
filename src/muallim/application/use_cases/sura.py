"""Сура целиком и наизусть (FR-57…FR-60, ADR-0076): проверить, засчитать, сохранить.

По тексту: все аяты чистые → засчитаны все уроки суры («всё или ничего», FR-58). Наизусть:
все аяты чистые → отметка 🧠, уроки не засчитываются (FR-59).
"""

import asyncio
import time
from dataclasses import asdict, dataclass, field

from muallim.application.ports.recognition import (
    AyahListening,
    Listening,
    RecognitionError,
    SuraListener,
    SuraRecognizer,
)
from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerRepository,
    SuraReadingRepository,
    UnitOfWork,
)
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import BuildInfo, Clock, EventLog, IdGenerator
from muallim.domain.assessment import Assessment, assess
from muallim.domain.card_check import CardDecision, accepted_references, decide, full_reading
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import CardPolicy, GradingPolicy
from muallim.domain.sura import (
    AyahOutcome,
    AyahResult,
    ReadingChunk,
    Sura,
    SuraAssessment,
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
    # «Варианты карточки» на MostafaMaroof (FR-70 ч. 7, ADR-0088); None — прежняя проверка Muaalem
    listener: SuraListener | None = None
    card_policy: CardPolicy = field(default_factory=CardPolicy)

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
        done = await self.attempts.mastered(learner.id)  # по вердикту (ADR-0088 п. 7)
        studied = bool(items) and all(i.id in done for i in items)
        ayahs = [(a.id, int(a.quran.split(":")[1]), a.text) for a in sura.ayahs]
        opening = sura.opening.text if sura.opening else ""
        preamble = self._istiadha()

        started = time.perf_counter()
        try:
            if self.listener is not None:
                heard = await self._listen(self.listener, sura, audio, ayahs, opening, preamble)
            else:
                heard = await self._recognize(audio, ayahs, opening, preamble)
        except Exception as caught:
            # не RecognitionError (KeyError словаря, ValueError numpy) — тоже сбой модели: иначе
            # обработчик принял бы KeyError за «сура убрана» (ревью FR-70)
            error = (
                caught
                if isinstance(caught, RecognitionError)
                else RecognitionError(str(caught), stage="model")
            )
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
            if error is caught:
                raise
            raise error from caught
        assessment = heard.assessment
        processing_ms = round((time.perf_counter() - started) * 1000)

        count = await self.readings.count(learner.id, number, mode)
        last = await self.readings.last_read(learner.id, number)
        now = self.clock.now()
        # Запись храним только с согласия ученика (FR-09, docs/security/privacy.md).
        audio_sha = await self.audio.save(audio) if learner.research_consent else None
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
            chunks=heard.chunks,
            credited=credited,
            model_version=heard.model_version,
            curriculum_version=self.curriculum.version,
            app_version=self.build.version,
            audio_sha256=audio_sha,
            audio_duration_ms=heard.audio_duration_ms,
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

    async def _recognize(
        self, audio: bytes, ayahs: list[tuple[str, int, str]], opening: str, preamble: str
    ) -> "_Heard":
        """Прежняя проверка (Muaalem): фонемы всей суры против эталона по словам (ADR-0076)."""
        recognition = await self.recognizer.recognize_sura(audio, ayahs, opening, preamble)
        assessment = assess_sura(
            recognition.ayahs,
            recognition.heard,
            self.policy,
            opening=recognition.opening,
            preamble=recognition.preamble,
            pauses=recognition.pauses,
        )
        chunks = tuple(
            ReadingChunk(begin, end, recognition.heard[a:b], *assessment.ayahs_between(a, b))
            for begin, end, a, b in recognition.chunks
        )
        return _Heard(assessment, chunks, recognition.model_version, recognition.audio_duration_ms)

    async def _listen(  # noqa: PLR0917 — одна запись суры и её части
        self,
        listener: SuraListener,
        sura: Sura,
        audio: bytes,
        ayahs: list[tuple[str, int, str]],
        opening: str,
        preamble: str,
    ) -> "_Heard":
        """«Варианты карточки» по каждому аяту (FR-70 ч. 7, ADR-0088 «Суры»): ``decide`` на
        отрезке аята с правилами урока суры; не засчитан — второй проход (аят вырезан)."""
        lesson = sura.lessons[0].number
        listening = await listener.listen_sura(
            audio, ayahs, opening, preamble,
            long_is_short=self.card_policy.long_is_short(lesson),
        )  # fmt: skip
        reached = [a.span_ms is not None for a in listening.ayahs]
        results = []
        chunks = []
        for k, ayah in enumerate(listening.ayahs):
            text = ayahs[k][2]
            if ayah.span_ms is None:
                outcome = AyahOutcome.SKIPPED if any(reached[k + 1 :]) else AyahOutcome.NOT_REACHED
                results.append(AyahResult(ayah.item_id, ayah.number, outcome, 0, "", ""))
                continue
            first = await self._decide(text, ayah, lesson)
            second_pass = first.outcome != "passed" and ayah.rehear is not None
            d = first
            if second_pass and ayah.rehear is not None:
                d = await self._decide(text, await ayah.rehear(), lesson)
            results.append(_ayah_result(ayah, text, d, second_pass=second_pass))
            chunks.append(ReadingChunk(*ayah.span_ms, results[-1].heard, ayah.number, ayah.number))
        assessment = SuraAssessment(
            ayahs=tuple(results),
            events=(),
            score=round(sum(r.score for r in results) / len(results)) if results else 0,
            reference="".join(r.reference for r in results),
            heard="".join(r.heard for r in results),
        )
        return _Heard(
            assessment, tuple(chunks), listening.model_version, listening.audio_duration_ms
        )

    async def _decide(
        self, text: str, ayah: AyahListening | Listening, lesson: int
    ) -> CardDecision:
        """``decide`` по аяту не в потоке бота: сотни вариантов на длинном аяте."""
        policy = self.card_policy
        accepted = [r for _, r in accepted_references(text, ayah.references)]
        return await asyncio.to_thread(
            decide, accepted, ayah.score, policy, separate_syllables=False,
            rules=policy.rules_for(lesson), sounds=ayah.sounds, score_many=ayah.score_many,
        )  # fmt: skip


@dataclass(frozen=True, slots=True)
class _Heard:
    """Итог любой из двух проверок суры — дальше сценарий общий."""

    assessment: SuraAssessment
    chunks: tuple[ReadingChunk, ...]
    model_version: str
    audio_duration_ms: int


_OUTCOME = {
    "passed": AyahOutcome.CLEAN,
    "again": AyahOutcome.AGAIN,
    "error": AyahOutcome.PRONUNCIATION,
}


def _ayah_result(
    ayah: AyahListening, text: str, d: CardDecision, *, second_pass: bool
) -> AyahResult:
    """Исход аята по решению: засчитано — чисто, «ещё раз» — свой исход с баллом 0, ошибка —
    произношение (разбор — «верное чтение против победившего варианта», ADR-0088 п. 5)."""
    reference = full_reading([r for _, r in accepted_references(text, ayah.references)])
    outcome = _OUTCOME[d.outcome]
    if outcome is AyahOutcome.AGAIN:
        assessment = Assessment(reference, "", 0, ())
    elif outcome is AyahOutcome.CLEAN:
        assessment = assess(d.winner, d.winner)
    else:
        assessment = assess(reference, d.winner)
    output = {**asdict(d), "hints": list(d.hints), "second_pass": second_pass}
    return AyahResult(
        ayah.item_id, ayah.number, outcome, assessment.score, assessment.reference,
        assessment.heard, pronunciation_errors=len(assessment.errors), model_output=output,
    )  # fmt: skip
