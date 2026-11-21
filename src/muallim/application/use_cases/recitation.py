"""Главный сценарий: ученик прислал голосовое — проверить, объяснить, сохранить."""

import asyncio
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from muallim.application.breakdown import Breakdown, ErrorGroup, build_breakdown
from muallim.application.feedback import Explanation, FeedbackCatalog
from muallim.application.ports.recognition import (
    CardListener,
    PronunciationRecognizer,
    RecognitionError,
)
from muallim.application.ports.repositories import AttemptRepository, UnitOfWork
from muallim.application.ports.storage import AudioStore, SplitSalt
from muallim.application.ports.system import BuildInfo, Clock, EventLog, IdGenerator
from muallim.application.transcription import Reading, as_text, legend, reading
from muallim.application.use_cases.cards import OpenItem
from muallim.domain.assessment import Assessment, Candidate, assess, assess_variants, unread_from
from muallim.domain.attempt import Attempt
from muallim.domain.card_check import (
    accepted_references,
    card_verdict,
    decide,
    full_reading,
    syllable_card,
)
from muallim.domain.curriculum import Curriculum, Lesson, LessonItem, Lexicon, lesson_letter
from muallim.domain.learner import Learner
from muallim.domain.policy import CardPolicy, GradingPolicy, Verdict
from muallim.domain.split import Part, part_of


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
    hints: tuple[str, ...] = ()  # подсказки «вариантов карточки» (FR-70 п. 3, 5)
    other_syllable: bool = False  # прочитан другой слог (FR-70 п. 3)
    unheard: bool = False  # «ещё раз» из-за тишины: бот ничего не расслышал (FR-70 п. 6)
    forced_pass: bool = False  # второе «не уверен» подряд — засчитано (ADR-0087 п. 4)

    @property
    def verdict(self) -> Verdict:
        return self.attempt.verdict


@dataclass(frozen=True, slots=True)
class _Heard:
    """Итог распознавания любой из двух проверок — дальше сценарий общий."""

    best: Candidate
    candidates: tuple[Candidate, ...]
    heard: str  # что прозвучало, в записи бота
    verdict: Verdict
    model_version: str
    audio_duration_ms: int
    model_output: Mapping[str, Any]
    hints: tuple[str, ...] = ()
    other_syllable: bool = False
    unheard: bool = False
    forced_pass: bool = False


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
    # «Варианты карточки» на MostafaMaroof (FR-70, ADR-0088); None — прежняя проверка Muaalem
    listener: CardListener | None = None
    card_policy: CardPolicy = field(default_factory=CardPolicy)
    # деление на учёбу и тест (TD-FN-174, предрегистрация 0.7); None — всё в учёбу
    split_salt: SplitSalt | None = None

    async def execute(
        self, learner: Learner, audio: bytes, item_id: str | None = None
    ) -> RecitationResult:
        """Проверить чтение текущей карточки или ``item_id`` (карточка на экране)."""
        item = self.curriculum.item(item_id) if item_id else self.cards.current(learner)
        lesson, _ = self.curriculum.locate(item.id)
        started = time.perf_counter()
        try:
            if self.listener is not None and lesson.number in self.card_policy.maroof_lessons:
                result = await self._listen(self.listener, learner, audio, item, lesson)
            else:
                result = await self._recognize(audio, item)
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
        best = result.best
        processing_ms = round((time.perf_counter() - started) * 1000)

        # Номер попытки — до сохранения: по нему часть (учёба / тест), тестовый голос — в закрытую.
        attempt_id = self.ids.new_id()
        part = part_of(attempt_id, self.split_salt.get()) if self.split_salt else Part.TRAIN
        # Запись храним только с согласия ученика (FR-09, docs/security/privacy.md).
        audio_sha = await self.audio.save(audio, part) if learner.research_consent else None

        language = self.catalog.resolve(learner)
        renderer = self.catalog.renderer(language)
        attempt = Attempt(
            id=attempt_id,
            learner_id=learner.id,
            item_id=item.id,
            curriculum_version=self.curriculum.version,
            model_version=result.model_version,
            assessment=best.assessment,
            verdict=result.verdict,
            audio_sha256=audio_sha,
            audio_duration_ms=result.audio_duration_ms,
            processing_ms=processing_ms,
            created_at=self.clock.now(),
            reference_variant=best.variant,
            candidates=result.candidates,
            model_output=dict(result.model_output),
            policy=self.policy,
            app_version=self.build.version,
            feedback_language=language,
            part=part,
        )
        errors = best.assessment.errors
        reference = best.assessment.reference
        letter = lesson_letter(lesson)
        # «ещё раз» (FR-70): ни разбора, ни «услышанного» — бот не уверен, что услышал
        again = result.verdict is Verdict.AGAIN
        unread = None if again else unread_from(reference, result.heard)
        expected: Reading = (
            ()
            if again
            else _read_part(
                reading(reference, renderer.lexicon, [e.syllable for e in errors]), unread
            )
        )
        heard: Reading = () if again else reading(result.heard, renderer.lexicon)
        breakdown = (
            None
            if again
            else build_breakdown(
                best.assessment, item.text, renderer.lexicon, unread=unread, lesson_letter=letter
            )
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
            heard_transcription="" if again else as_text(heard),
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
            if previous and breakdown
            else (),
            breakdown=breakdown,
            hints=result.hints,
            other_syllable=result.other_syllable,
            unheard=result.unheard,
            forced_pass=result.forced_pass,
        )

    async def _recognize(self, audio: bytes, item: LessonItem) -> _Heard:
        """Прежняя проверка: строка фонем Muaalem против эталонов, балл 0–100 → вердикт."""
        recognition = await self.recognizer.recognize(audio, item.text)
        best, candidates = assess_variants(recognition.references, recognition.heard)
        return _Heard(
            best, candidates, recognition.heard, self.policy.verdict(best.assessment),
            recognition.model_version, recognition.audio_duration_ms, recognition.raw,
        )  # fmt: skip

    async def _listen(
        self, listener: CardListener, learner: Learner, audio: bytes, item: LessonItem,
        lesson: Lesson,
    ) -> _Heard:  # fmt: skip
        """«Варианты карточки» (ADR-0088 п. 5, 6): решение в домене по баллам вариантов; разбор —
        ``Assessment(верное, победивший вариант)``; «ещё раз» — не больше раза подряд."""
        policy = self.card_policy
        listening = await listener.listen(
            audio, item.text, long_is_short=policy.long_is_short(lesson.number)
        )
        references = accepted_references(item.text, listening.references)
        accepted = [reading for _, reading in references]
        # сотни вариантов — секунды на длинной строке: не в потоке бота
        d = await asyncio.to_thread(
            decide, accepted, listening.score, policy,
            separate_syllables=syllable_card(item.text), rules=policy.rules_for(lesson.number),
            sounds=listening.sounds, score_many=listening.score_many,
        )  # fmt: skip
        if d.unheard:  # тишина — не попытка для «ещё раз подряд» (автор 2026-11-20)
            verdict, for_teacher = Verdict.AGAIN, False
        else:
            previous = await self.attempts.last_verdict(learner.id, item.id)
            verdict, for_teacher = policy.after_repeat(previous, card_verdict(d))
        heard = "" if verdict is Verdict.AGAIN else d.winner
        reference = d.winner if d.outcome != "error" else full_reading(accepted)
        if verdict is Verdict.AGAIN:  # балла верного чтения нет: 0, без ошибок (FR-70)
            reference = full_reading(accepted)
            candidates = tuple(
                Candidate(name, Assessment(ref, "", 0, ())) for name, ref in references
            )
        else:
            candidates = tuple(Candidate(name, assess(ref, heard)) for name, ref in references)
        best = next(c for c in candidates if c.assessment.reference == reference)
        output = {**asdict(d), "hints": list(d.hints), "raw": listening.raw,
                  "for_teacher": for_teacher}  # fmt: skip
        return _Heard(
            best, candidates, heard, verdict, listening.model_version,
            listening.audio_duration_ms, output, d.hints, d.other_syllable,
            d.unheard and verdict is Verdict.AGAIN, for_teacher,
        )  # fmt: skip

    async def _lesson_done(self, learner: Learner, items: tuple[LessonItem, ...]) -> bool:
        done = await self.attempts.mastered(learner.id)  # по вердикту (ADR-0088 п. 7)
        return bool(items) and all(i.id in done for i in items)


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
