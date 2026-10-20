"""Главный сценарий: ученик прислал голосовое — проверить, объяснить, сохранить."""

import time
from dataclasses import dataclass

from muallim.application.feedback import Explanation, FeedbackCatalog
from muallim.application.ports.recognition import PronunciationRecognizer, RecognitionError
from muallim.application.ports.repositories import AttemptRepository, UnitOfWork
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import BuildInfo, Clock, EventLog, IdGenerator
from muallim.application.transcription import Reading, as_text, legend, reading
from muallim.application.use_cases.cards import OpenItem
from muallim.domain.assessment import Assessment, assess_variants, unread_from
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, LessonItem, Lexicon
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy, Verdict


@dataclass(frozen=True, slots=True)
class RecitationResult:
    item: LessonItem
    attempt: Attempt
    feedback: tuple[Explanation, ...]  # разбор для ученика (в БД — текст к каждой ошибке)
    heard_transcription: str  # «что прозвучало» буквами языка ученика
    next_item: LessonItem | None  # None — это была последняя карточка программы
    lesson_completed: bool = False  # этой попыткой засчитана последняя строка урока
    expected_reading: Reading = ()  # «Нужно» по слогам, слоги с ошибкой отмечены (FR-43)
    heard_reading: Reading = ()  # «У тебя» по слогам
    legend: tuple[str, ...] = ()  # пояснения к значкам транскрипции
    practice: tuple[str, ...] = ()  # слоги с ошибками — сказать медленно 3 раза
    unread_from: int | None = None  # с какого слога ``expected_reading`` строка не дочитана
    previous_score: int | None = None  # балл прошлой попытки этой строки
    fixed: tuple[str, ...] = ()  # слоги с ошибкой в прошлый раз, верные теперь

    @property
    def verdict(self) -> Verdict:
        return self.attempt.verdict


@dataclass(frozen=True, slots=True)
class AssessRecitation:
    curriculum: Curriculum
    cards: OpenItem
    recognizer: PronunciationRecognizer
    attempts: AttemptRepository
    audio: AudioStore
    policy: GradingPolicy
    catalog: FeedbackCatalog
    uow: UnitOfWork
    clock: Clock
    ids: IdGenerator
    events: EventLog
    build: BuildInfo

    async def execute(
        self, learner: Learner, audio: bytes, item_id: str | None = None
    ) -> RecitationResult:
        """Проверить чтение текущей карточки или ``item_id`` (начало занятия: курсор на месте)."""
        item = self.curriculum.item(item_id) if item_id else self.cards.current(learner)
        started = time.perf_counter()
        try:
            recognition = await self.recognizer.recognize(audio, item.text)
        except RecognitionError as error:
            # Сбой — в журнал, иначе долю сбоев не посчитать (NFR-REL-02). Без текста ошибки.
            await self.events.record(
                "recognition_failed",
                learner.id,
                {
                    "item_id": item.id,
                    "stage": error.stage,
                    "processing_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            await self.uow.commit()
            raise
        best, candidates = assess_variants(recognition.references, recognition.heard)
        processing_ms = round((time.perf_counter() - started) * 1000)

        # Запись храним только с согласия ученика (FR-09, docs/security/privacy.md).
        audio_sha = await self.audio.save(audio) if learner.research_consent else None

        language = self.catalog.resolve(learner)
        renderer = self.catalog.renderer(language)
        attempt = Attempt(
            id=self.ids.new_id(),
            learner_id=learner.id,
            item_id=item.id,
            curriculum_version=self.curriculum.version,
            model_version=recognition.model_version,
            assessment=best.assessment,
            verdict=self.policy.verdict(best.assessment),
            audio_sha256=audio_sha,
            audio_duration_ms=recognition.audio_duration_ms,
            processing_ms=processing_ms,
            created_at=self.clock.now(),
            reference_variant=best.variant,
            candidates=candidates,
            model_output=dict(recognition.raw),
            policy=self.policy,
            app_version=self.build.version,
            feedback_language=language,
        )
        errors = best.assessment.errors
        reference = best.assessment.reference
        unread = unread_from(reference, recognition.heard)
        expected = _read_part(
            reading(reference, renderer.lexicon, [e.syllable for e in errors]), unread
        )
        heard = reading(recognition.heard, renderer.lexicon)
        lesson, _ = self.curriculum.locate(item.id)
        was_done = await self._lesson_done(learner, lesson.practice_items)
        previous = await self.attempts.last_assessment(learner.id, item.id)
        await self.attempts.add(attempt, renderer.render(errors, reference))
        await self.events.record(
            "attempt_assessed",
            learner.id,
            {"item_id": item.id, "score": best.assessment.score, "verdict": attempt.verdict},
        )
        await self.uow.commit()
        return RecitationResult(
            item=item,
            attempt=attempt,
            feedback=renderer.explain(errors, reference, unread),
            heard_transcription=as_text(heard),
            next_item=self.curriculum.next_item(item.id),
            lesson_completed=not was_done
            and await self._lesson_done(learner, lesson.practice_items),
            expected_reading=expected,
            heard_reading=heard,
            legend=legend(as_text(expected) + as_text(heard), renderer.lexicon),
            practice=tuple(dict.fromkeys(text for text, wrong in expected[:unread] if wrong)),
            unread_from=unread,
            previous_score=previous.score if previous else None,
            fixed=_fixed(previous, expected, renderer.lexicon) if previous else (),
        )

    async def _lesson_done(self, learner: Learner, items: tuple[LessonItem, ...]) -> bool:
        best = await self.attempts.best_scores(learner.id)
        return bool(items) and all(self.policy.is_mastered(best.get(i.id, 0)) for i in items)


def _read_part(shown: Reading, unread: int | None) -> Reading:
    """Непрочитанный конец — не ошибки: с ``unread`` слоги без отметки."""
    if unread is None:
        return shown
    return shown[:unread] + tuple((text, False) for text, _ in shown[unread:])


def _fixed(previous: Assessment, now: Reading, lexicon: Lexicon) -> tuple[str, ...]:
    """Слоги, где в прошлый раз была ошибка, а теперь нет (сравниваем по тексту слога).

    Непрочитанный в прошлый раз конец — не исправление: тогда это были не ошибки.
    """
    before = _read_part(
        reading(previous.reference, lexicon, [e.syllable for e in previous.errors]),
        unread_from(previous.reference, previous.heard),
    )
    wrong_now = {text for text, wrong in now if wrong}
    return tuple(dict.fromkeys(text for text, wrong in before if wrong and text not in wrong_now))
