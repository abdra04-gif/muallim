"""Главный сценарий: ученик прислал голосовое — проверить, объяснить, сохранить."""

import time
from dataclasses import dataclass

from muallim.application.breakdown import Breakdown, ErrorGroup, build_breakdown
from muallim.application.feedback import Explanation, FeedbackCatalog
from muallim.application.ports.recognition import PronunciationRecognizer, RecognitionError
from muallim.application.ports.repositories import AttemptRepository, UnitOfWork
from muallim.application.ports.storage import AudioStore
from muallim.application.ports.system import BuildInfo, Clock, EventLog, IdGenerator
from muallim.application.transcription import Reading, as_text, legend, reading
from muallim.application.use_cases.cards import OpenItem
from muallim.domain.assessment import Assessment, assess_variants, unread_from
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, LessonItem, Lexicon, lesson_letter
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
    fixed: tuple[str, ...] = ()  # подписи групп ошибок прошлой попытки, которых теперь нет
    breakdown: Breakdown | None = None  # разбор группами для экрана (FR-54); сценарий заполняет

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
        letter = lesson_letter(lesson)
        breakdown = build_breakdown(
            best.assessment, item.text, renderer.lexicon, unread=unread, lesson_letter=letter
        )
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
            fixed=_fixed(previous, breakdown, item.text, renderer.lexicon, letter)
            if previous
            else (),
            breakdown=breakdown,
        )

    async def _lesson_done(self, learner: Learner, items: tuple[LessonItem, ...]) -> bool:
        best = await self.attempts.best_scores(learner.id)
        return bool(items) and all(self.policy.is_mastered(best.get(i.id, 0)) for i in items)


def _read_part(shown: Reading, unread: int | None) -> Reading:
    """Непрочитанный конец — не ошибки: с ``unread`` слоги без отметки."""
    if unread is None:
        return shown
    return shown[:unread] + tuple((text, False) for text, _ in shown[unread:])


def _fixed(
    previous: Assessment, now: Breakdown, text: str, lexicon: Lexicon, letter: str | None
) -> tuple[str, ...]:
    """Ошибки прошлой попытки (группы), которых теперь нет, — их подписи (FR-54, Р1).

    Сравнение по виду и нужному звуку, без прозвучавшего: ح→ه, а теперь ح→خ — не исправлено (I6).
    Прошлые ошибки в словах, до которых сейчас не дочитал, — не исправление; непрочитанный в
    прошлый раз конец — тоже (тогда это были не ошибки).
    """
    before = build_breakdown(
        previous,
        text,
        lexicon,
        unread=unread_from(previous.reference, previous.heard),
        lesson_letter=letter,
    )
    still = {_key(g) for g in now.groups}
    unread = set(now.unread)
    return tuple(
        dict.fromkeys(
            g.need_label
            for g in before.groups
            if _key(g) not in still and any(p.word_index not in unread for p in g.places)
        )
    )


def _key(g: ErrorGroup) -> tuple[str, ...]:
    return (g.kind, g.expected)
