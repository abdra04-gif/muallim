"""Сценарий проверки карточки на «вариантах карточки» (FR-70 п. 2–9; ADR-0088 п. 1, 5–9).

Слушатель — ``ScriptedCardListener``: эталоны из фонетизатора бота (фикстура уроков 1–41), баллы —
таблицей по звукам MostafaMaroof. Карточки — из curriculum/course.ru.yaml: L010-04 «بُ» (урок 10),
L010-03 «بِ», L004-05 «رَ رِ رُ», L034-01 «كَلَامُ», L038-01 «رَبَّ».

Предложенный интерфейс: ``AssessRecitation(..., listener=CardListener | None,
card_policy=CardPolicy())``; ``AttemptRepository.last_verdict(learner_id, item_id)`` и
``.mastered(learner_id)``. Вердикт: «засчитано» без подсказок — EXCELLENT, с подсказкой — PASSED.
Решение автора 2026-11-19: MostafaMaroof — на всю книгу (``CardPolicy.maroof_lessons`` — все уроки);
без слушателя (``checker=muaalem``) — прежний путь.
"""

import json
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from typing import Any
from uuid import UUID

import pytest

from muallim.application.feedback import FeedbackCatalog
from muallim.application.ports.recognition import Listening, RecognitionError
from muallim.application.ports.system import BuildInfo
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.recitation import AssessRecitation, RecitationResult
from muallim.domain.assessment import Assessment, assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import CardPolicy, GradingPolicy, Verdict
from tests.fakes import (
    FixedClock,
    InMemoryAttempts,
    InMemoryAudio,
    InMemoryLearners,
    ListEventLog,
    ScriptedCardListener,
    ScriptedRecognizer,
    SequentialIds,
    SpyUoW,
)

BU, BI, TRIPLE, KALAM, RABBA = "L010-04", "L010-03", "L004-05", "L034-01", "L038-01"


@dataclass
class World:
    curriculum: Curriculum
    catalog: FeedbackCatalog
    listener: ScriptedCardListener
    recognizer: ScriptedRecognizer
    attempts: InMemoryAttempts
    events: ListEventLog
    uow: SpyUoW
    learner: Learner

    def assess(self) -> AssessRecitation:
        learners = InMemoryLearners()
        cards = OpenItem(self.curriculum, learners, self.uow, self.events)
        return AssessRecitation(
            self.curriculum, cards, self.recognizer, self.attempts, InMemoryAudio(),
            GradingPolicy(), self.catalog, self.uow, FixedClock(), SequentialIds(), self.events,
            BuildInfo("test-1.0"), listener=self.listener, card_policy=CardPolicy(),
        )  # fmt: skip

    async def read(self, item_id: str, scores: dict[str, float]) -> RecitationResult:
        self.listener.scores = scores
        return await self.assess().execute(self.learner, b"ogg", item_id)


@pytest.fixture
def w(curriculum: Curriculum, catalog: FeedbackCatalog) -> World:
    learner = Learner(UUID(int=7), 77, "L-00000007", "ru", FixedClock().now())
    return World(
        curriculum, catalog, ScriptedCardListener(), ScriptedRecognizer(), InMemoryAttempts(),
        ListEventLog(), SpyUoW(), learner,
    )  # fmt: skip


def _late_item(c: Curriculum) -> str:
    """Карточка урока 42+, которую бот проверяет голосом."""
    return next(i.id for les in c.lessons if les.number >= 42 for i in les.items if i.is_checkable)


# ---------- ответ: засчитано / ошибка / ещё раз ----------
async def test_correct_reading_without_hints_is_excellent(w: World) -> None:
    r = await w.read(BU, {"بُ": -1.0})
    assert r.verdict is Verdict.EXCELLENT
    assert r.attempt.assessment.score == 100 and r.attempt.assessment.errors == ()
    assert r.feedback == ()


async def test_correct_reading_with_a_soft_hint_is_passed_and_keeps_the_hint(w: World) -> None:
    """Урок 38: без шадды — только мягкая подсказка (ADR-0086 п. 3)."""
    r = await w.read(RABBA, {"رَببَ": -10.0, "رَببڇ": -11.0, "رَبَ": -2.0})
    assert r.verdict is Verdict.PASSED
    assert "no_shadda" in r.attempt.model_output["hints"]


async def test_reading_with_a_stop_is_correct_and_has_no_errors(w: World) -> None:
    """Победило чтение с остановкой — разбор строится от него, не от слитного (иначе «ошибка»
    в последней гласной при засчитанной карточке)."""
    r = await w.read(RABBA, {"رَببڇ": -1.0})
    assert r.verdict is Verdict.EXCELLENT
    assert r.attempt.assessment.errors == ()


async def test_error_is_failed_and_explained_like_before(w: World) -> None:
    """Разбор и объяснения — через Assessment(верное, победившая ошибка) (ADR-0088 п. 5)."""
    r = await w.read(BU, {"بُ": -10.0, "بِ": -2.0})
    assert r.verdict is Verdict.FAILED
    assert r.attempt.assessment == assess("بُ", "بِ")
    assert r.attempt.reference_variant == "wasl"
    assert r.feedback and r.breakdown is not None and r.breakdown.groups
    (stored,) = [f for a, f in w.attempts.items]
    assert len(stored) == len(r.attempt.assessment.errors)


async def test_unsure_model_asks_to_read_again(w: World) -> None:
    r = await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    assert r.verdict is Verdict.AGAIN
    assert not r.attempt.model_output.get("for_teacher")


async def test_single_syllable_card_read_without_vowel_is_an_error(w: World) -> None:
    """«بُ» без гласной — не чтение с остановкой: карточка из слогов читается с гласными
    (FR-70 п. 2)."""
    r = await w.read(BU, {"بُ": -10.0, "ب": -2.0})
    assert r.verdict is Verdict.FAILED


async def test_separate_syllables_accept_only_the_reading_with_vowels(w: World) -> None:
    """«رَ رِ رُ» без последней гласной — «ещё раз, протяни последнюю гласную», не «засчитано»."""
    r = await w.read(TRIPLE, {"رَرِرُ": -10.0, "رَرِر": -1.0})
    assert r.verdict is Verdict.AGAIN
    assert "last_vowel" in r.attempt.model_output["hints"]


# ---------- «ещё раз» не больше раза подряд (FR-70 п. 6) ----------
async def test_second_again_in_a_row_is_passed_and_goes_to_the_teacher(w: World) -> None:
    unsure = {"بُ": -5.0, "بَ": -3.0}
    first = await w.read(BU, unsure)
    second = await w.read(BU, unsure)
    assert first.verdict is Verdict.AGAIN
    assert second.verdict is Verdict.PASSED
    assert second.attempt.model_output["for_teacher"] is True


async def test_again_on_another_card_does_not_count(w: World) -> None:
    await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    r = await w.read(BI, {"بِ": -5.0, "بَ": -3.0})
    assert r.verdict is Verdict.AGAIN


async def test_again_after_an_error_is_again(w: World) -> None:
    await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    await w.read(BU, {"بُ": -10.0, "بِ": -2.0})
    r = await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    assert r.verdict is Verdict.AGAIN


# ---------- что уходит слушателю и в БД ----------
@pytest.mark.parametrize(("item_id", "long_is_short"), [(BU, True), (KALAM, False)])
async def test_listener_gets_the_lesson_rule_for_long_vowels(
    w: World, item_id: str, long_is_short: bool
) -> None:
    await w.read(item_id, {})
    ((text, flag),) = w.listener.calls
    assert text == w.curriculum.item(item_id).text
    assert flag is long_is_short


async def test_decision_trace_is_stored_as_json_without_inf(w: World) -> None:
    """Учитель видит маржи, победивший вариант, «другой слог», подсказки и что модель услышала
    без подсказки (FR-70 п. 9); в PostgreSQL JSON без inf и nan."""
    w.listener.raw = "b i"
    for scores in ({}, {"بُ": -1.0}, {"بُ": -10.0, "زُ": -3.0}):
        r = await w.read(BU, scores)
        out = r.attempt.model_output
        json.dumps(out, allow_nan=False)
        assert {"margin", "margin_other", "winner", "kind", "other_syllable", "hints"} <= set(out)
        assert out["raw"] == "b i"
        assert r.attempt.model_version == "scripted-maroof"
        assert r.attempt.audio_duration_ms == 1200


async def test_margin_is_against_a_real_error_not_a_sound_alike_of_the_correct(w: World) -> None:
    """«كَلَامُ» с остановкой (мадд 4) и «нет гласной» (мадд 2) — для модели одно и то же."""
    r = await w.read(KALAM, {"كَلَاااام": -1.0, "كَلَاامِ": -6.0})
    assert r.verdict is Verdict.EXCELLENT
    assert r.attempt.model_output["margin"] == pytest.approx(5.0, abs=1e-3)


async def test_listener_failure_is_journaled_and_nothing_is_saved(w: World) -> None:
    w.listener.fail, w.listener.fail_stage = True, "decode"
    with pytest.raises(RecognitionError):
        await w.read(BU, {})
    assert w.attempts.items == []
    event, _, payload = w.events.events[-1]
    assert event == "recognition_failed" and payload["stage"] == "decode"


async def test_lessons_after_41_also_go_through_the_card_listener(w: World) -> None:
    """Решение автора: MostafaMaroof — на всю книгу; распознаватель Muaalem для карточек не
    вызывается (здесь он сломан: вызов дал бы RecognitionError)."""
    item_id = _late_item(w.curriculum)
    w.recognizer.fail = True
    w.listener.references = (("wasl", "بُ"), ("waqf", "بڇ"))  # эталон этой проверки не важен
    r = await w.read(item_id, {"بُ": -1.0})
    assert [text for text, _ in w.listener.calls] == [w.curriculum.item(item_id).text]
    assert r.attempt.model_version == "scripted-maroof"


async def test_again_counter_starts_over_after_a_forced_pass(w: World) -> None:
    """«Ещё раз» → «ещё раз» (засчитано, учителю) → «ещё раз» снова: счёт начат заново."""
    unsure = {"بُ": -5.0, "بَ": -3.0}
    verdicts = [(await w.read(BU, unsure)).verdict for _ in range(3)]
    assert verdicts == [Verdict.AGAIN, Verdict.PASSED, Verdict.AGAIN]
    last_attempt, _ = w.attempts.items[-1]
    assert not last_attempt.model_output.get("for_teacher")


async def test_again_after_a_pass_is_again(w: World) -> None:
    await w.read(BU, {"بُ": -1.0})
    r = await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    assert r.verdict is Verdict.AGAIN


@pytest.mark.parametrize("scores", [{}, {"بُ": -1.0}, {"بِ": -2.0}, {"ب": -2.0}])
async def test_trace_is_json_safe_when_the_model_finds_a_variant_impossible(
    w: World, scores: dict[str, float]
) -> None:
    """Настоящая CTC даёт −inf невозможному варианту (короткая запись, долгая на уроках 3–30)."""
    w.listener.unheard = -math.inf
    r = await w.read(BU, scores)
    json.dumps(dict(r.attempt.model_output), allow_nan=False)


async def test_drawn_out_vowel_is_not_an_error_where_long_counts_as_short(w: World) -> None:
    """Урок 10 (3–30): ученик протянул «у» в «بُ» — для проверки это та же короткая гласная."""
    r = await w.read(BU, {"بُۥۥ": -1.0, "بَ": -6.0})
    assert r.verdict is Verdict.EXCELLENT


async def test_without_listener_every_lesson_goes_the_old_way(w: World) -> None:
    """``checker=muaalem``: слушателя нет — прежний путь и на уроках 1–41 (откат настройкой)."""
    from dataclasses import replace  # noqa: PLC0415

    uc = replace(w.assess(), listener=None)
    r = await uc.execute(w.learner, b"ogg", BU)
    assert r.attempt.model_version == "scripted"


# ---------- освоение — по вердикту (ADR-0088 п. 7) ----------
def _old_attempt(w: World, n: int, item_id: str, verdict: Verdict, score: int) -> Attempt:
    text = w.curriculum.item(item_id).text
    return Attempt(
        UUID(int=500 + n), w.learner.id, item_id, "v", "m", Assessment(text, text, score, ()),
        verdict, None, 900, 10, FixedClock().now(),
    )  # fmt: skip


async def test_failed_with_a_high_score_does_not_complete_the_lesson(w: World) -> None:
    """Все строки урока 10, кроме «بُ», — «ошибка» с баллом 85: «بُ» верно — урок не пройден."""
    lesson, _ = w.curriculum.locate(BU)
    others = [i.id for i in lesson.practice_items if i.id != BU]
    for n, item_id in enumerate(others):
        w.attempts.items.append((_old_attempt(w, n, item_id, Verdict.FAILED, 85), ()))
    r = await w.read(BU, {"بُ": -1.0})
    assert r.verdict is Verdict.EXCELLENT
    assert not r.lesson_completed


async def test_old_passed_attempts_still_complete_the_lesson(w: World) -> None:
    lesson, _ = w.curriculum.locate(BU)
    others = [i.id for i in lesson.practice_items if i.id != BU]
    for n, item_id in enumerate(others):
        w.attempts.items.append((_old_attempt(w, n, item_id, Verdict.PASSED, 85), ()))
    r = await w.read(BU, {"بُ": -1.0})
    assert r.lesson_completed


# ---------- подсчёт вариантов — не в потоке бота (блокер ревью) ----------
@dataclass
class _ThreadSpy:
    """Слушатель-обёртка: запоминает, в каком потоке зовут ``score`` (и ``score_many``, если
    порт его даёт). Поток цикла событий бота — поток теста."""

    inner: ScriptedCardListener
    threads: set[int]

    async def listen(self, audio: bytes, text: str, *, long_is_short: bool) -> Listening:
        listening = await self.inner.listen(audio, text, long_is_short=long_is_short)
        score = listening.score

        def spied(variant: str) -> float:
            self.threads.add(threading.get_ident())
            return score(variant)

        changes: dict[str, Any] = {"score": spied}
        many = getattr(listening, "score_many", None)
        if many is not None:

            def spied_many(variants: Sequence[str]) -> Sequence[float]:
                self.threads.add(threading.get_ident())
                scored: list[float] = list(many(variants))
                return scored

            changes["score_many"] = spied_many
        return dc_replace(listening, **changes)


@pytest.mark.parametrize("scores", [{"بُ": -1.0}, {"بُ": -5.0, "بَ": -3.0}, {"بُ": -10.0, "بِ": -2.0}])
async def test_variants_are_scored_off_the_event_loop_thread(
    w: World, scores: dict[str, float]
) -> None:
    """``decide`` (сотни вариантов, на длинной строке — секунды) идёт через ``asyncio.to_thread``:
    бот в это время отвечает другим ученикам."""
    threads: set[int] = set()
    w.listener.scores = scores
    uc = dc_replace(w.assess(), listener=_ThreadSpy(w.listener, threads))
    loop_thread = threading.get_ident()
    r = await uc.execute(w.learner, b"ogg", BU)
    assert threads, "баллы не считались"
    assert loop_thread not in threads
    assert r.verdict in set(Verdict)


@pytest.mark.parametrize("scores", [{"بُ": -1.0}, {"بُ": -5.0, "بَ": -3.0}, {"بُ": -10.0, "بِ": -2.0}])
async def test_scenario_scores_variants_in_one_batch(w: World, scores: dict[str, float]) -> None:
    """Сценарий передаёт ``listening.score_many`` в ``decide``: баллы — 1–2 вызовами батча,
    поштучный ``score`` не зовётся (иначе батч-CTC не ускоряет бота)."""
    from muallim.application.ports.recognition import Listening  # noqa: PLC0415

    assert "score_many" in Listening.__dataclass_fields__, "у порта нет score_many"
    await w.read(BU, scores)
    assert 1 <= len(w.listener.many_calls) <= 2
    assert w.listener.single_calls == 0


# ---------- тишина дважды подряд — не «засчитано» (блокер ревью) ----------
async def test_silence_twice_in_a_row_is_again_both_times(w: World) -> None:
    """Модель не слышит ничего (все баллы −inf): оба раза «ещё раз», учителю не уходит."""
    w.listener.unheard = -math.inf
    first = await w.read(BU, {})
    second = await w.read(BU, {})
    assert (first.verdict, second.verdict) == (Verdict.AGAIN, Verdict.AGAIN)
    for r in (first, second):
        assert not r.attempt.model_output.get("for_teacher")
        assert r.attempt.model_output["unheard"] is True


async def test_silence_after_an_unsure_again_is_again(w: World) -> None:
    """Тишина после «не уверен» — тоже «ещё раз»: засчитывать нечего."""
    await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    w.listener.unheard = -math.inf
    r = await w.read(BU, {})
    assert r.verdict is Verdict.AGAIN
    assert not r.attempt.model_output.get("for_teacher")


async def test_unsure_after_silence_is_a_first_again(w: World) -> None:
    """Тишина — не попытка (решение автора 2026-11-20): «не уверен» после неё — первое «ещё
    раз», учителю не уходит; следующее «не уверен» — уже второе подряд."""
    unsure = {"بُ": -5.0, "بَ": -3.0}
    w.listener.unheard = -math.inf
    await w.read(BU, {})
    first = await w.read(BU, unsure)
    assert first.verdict is Verdict.AGAIN
    assert not first.attempt.model_output.get("for_teacher")
    second = await w.read(BU, unsure)
    assert second.verdict is Verdict.PASSED
    assert second.attempt.model_output["for_teacher"] is True


async def test_unsure_again_trace_is_not_unheard(w: World) -> None:
    r = await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    assert r.attempt.model_output["unheard"] is False


# ---------- «ещё раз» — без балла и разбора (блокер ревью) ----------
@pytest.mark.parametrize(
    "scores",
    [{"بُ": -5.0, "بَ": -3.0}, {}],  # не уверен; тишина (unheard ниже)
)
async def test_again_has_score_zero_and_no_breakdown(w: World, scores: dict[str, float]) -> None:
    """У «ещё раз» нет балла верного чтения (иначе в БД и отчётах — 100, как у «отлично») и нет
    разбора: эталон не показывается ученику и учителю как «услышанное»."""
    if not scores:
        w.listener.unheard = -math.inf
    r = await w.read(BU, scores)
    assert r.verdict is Verdict.AGAIN
    a = r.attempt.assessment
    assert a.score == 0
    assert a.errors == ()
    assert r.feedback == ()
    assert r.heard_transcription == ""
    assert r.heard_reading == ()
    assert r.breakdown is None or not r.breakdown.groups
    ((_, stored),) = w.attempts.items
    assert stored == ()
    (event,) = [p for name, _, p in w.events.events if name == "attempt_assessed"]
    assert event["score"] == 0


async def test_before_and_after_skips_an_again_attempt(w: World) -> None:
    """«Было → стало» не сравнивает с «ещё раз» (решение автора 2026-11-20): ошибка → ещё раз →
    верно — «было» от ошибки, не 0 от «ещё раз»."""
    failed = await w.read(BU, {"بُ": -10.0, "بِ": -2.0})
    await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    r = await w.read(BU, {"بُ": -1.0})
    assert r.previous_score == failed.attempt.assessment.score
    assert r.fixed  # исправлена ошибка прошлой настоящей попытки


async def test_first_reading_after_only_an_again_has_no_before(w: World) -> None:
    await w.read(BU, {"بُ": -5.0, "بَ": -3.0})
    r = await w.read(BU, {"بُ": -1.0})
    assert r.previous_score is None
    assert r.fixed == ()


async def test_forced_pass_after_two_unsure_keeps_the_score_of_the_correct_reading(
    w: World,
) -> None:
    """Второе «не уверен» подряд — «засчитано» (учителю): балл не 0, как у засчитанной."""
    unsure = {"بُ": -5.0, "بَ": -3.0}
    await w.read(BU, unsure)
    r = await w.read(BU, unsure)
    assert r.verdict is Verdict.PASSED
    assert r.attempt.assessment.score == 100
