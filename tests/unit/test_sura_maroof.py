"""Сура целиком на MostafaMaroof (FR-70 ч. 7, FR-57, FR-58; ADR-0076, ADR-0088 «Суры — решения
автора», PHASE_3 §11.8k).

Сценарий ``ReadSura`` со слушателем суры (порт ``SuraListener``): каждый аят — ``decide`` на своём
отрезке с правилами урока суры (`CardPolicy`) → исход аята «засчитано» / «ещё раз» / «ошибка»;
аят, не засчитанный с первого раза, слушается вторым проходом (вырезан из записи); зачёт суры —
«всё или ничего», как в ADR-0076 (`SuraAssessment.complete`); маржи аята — в ``model_output``.
Muaalem при этом не зовётся. Модель не грузится: ``ScriptedSuraListener`` (`tests/fakes.py`).

Предложенный интерфейс (принимает человек):
- ``ReadSura(..., listener: SuraListener | None = None, card_policy: CardPolicy = CardPolicy())``;
- исход аята «ещё раз» — ``AyahOutcome.AGAIN = "again"``; «ошибка» — ``PRONUNCIATION``,
  не дочитан — ``NOT_REACHED``, засчитан — ``CLEAN``;
- ``AyahResult.model_output: Mapping[str, Any]`` — ``margin``, ``margin_other``, ``winner``,
  ``kind``, ``unheard``, ``second_pass`` (JSON без inf и nan).
"""

import json
from dataclasses import replace
from uuid import UUID

import pytest

from muallim.application.ports.recognition import RecognitionError
from muallim.application.ports.system import BuildInfo
from muallim.application.use_cases.progress import GetProgress, LessonStatus
from muallim.application.use_cases.sura import ReadSura
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import CardPolicy, GradingPolicy
from muallim.domain.sura import AyahOutcome, SuraMode
from tests.fakes import (
    FixedClock,
    InMemoryAttempts,
    InMemoryAudio,
    InMemoryLearners,
    InMemorySuraReadings,
    ListEventLog,
    ScriptedSuraListener,
    ScriptedSuraRecognizer,
    SequentialIds,
    SpyUoW,
)

IKHLAS = 112  # аль-Ихлас: урок L123, басмала L123-01, аяты L123-02…05


class World:
    def __init__(self, curriculum: Curriculum, listener: ScriptedSuraListener) -> None:
        self.clock = FixedClock()
        self.readings = InMemorySuraReadings()
        self.attempts = InMemoryAttempts(suras=self.readings)
        self.events = ListEventLog()
        self.recognizer = ScriptedSuraRecognizer()  # Muaalem: при MostafaMaroof не зовётся
        self.listener = listener
        self.learner = Learner(UUID(int=7), 77, "L-00000007", "ru", self.clock.now())
        self.learner.research_consent = True
        self.uc = ReadSura(
            curriculum=curriculum,
            recognizer=self.recognizer,
            readings=self.readings,
            attempts=self.attempts,
            audio=InMemoryAudio(),
            policy=GradingPolicy(),
            uow=SpyUoW(),
            clock=self.clock,
            ids=SequentialIds(),
            events=self.events,
            build=BuildInfo("test-1.0"),
            learners=InMemoryLearners(),
            listener=listener,
            card_policy=CardPolicy(),
        )
        self.progress = GetProgress(curriculum, self.attempts, GradingPolicy(), self.clock)

    async def status(self, lesson_id: str) -> LessonStatus:
        return (await self.progress.execute(self.learner)).of(lesson_id).status


def _world(curriculum: Curriculum, **script: object) -> World:
    return World(curriculum, ScriptedSuraListener(**script))  # type: ignore[arg-type]


def _outcomes(result: object) -> list[AyahOutcome]:
    return [a.outcome for a in result.reading.assessment.ayahs]  # type: ignore[attr-defined]


# ---------- какая модель слушает ----------
async def test_maroof_listens_to_the_sura_and_muaalem_is_not_called(
    curriculum: Curriculum,
) -> None:
    """Аяты, басмала и истиаза уходят слушателю суры; Muaalem (``recognizer``) не зовётся."""
    w = _world(curriculum)
    await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert w.recognizer.calls == []
    (call,) = w.listener.calls
    assert [(i, n) for i, n, _ in call["ayahs"]] == [
        ("L123-02", 1), ("L123-03", 2), ("L123-04", 3), ("L123-05", 4),
    ]  # fmt: skip
    assert [t for _, _, t in call["ayahs"]] == [
        curriculum.item(f"L123-0{k}").text for k in range(2, 6)
    ]
    assert call["opening"] == curriculum.item("L123-01").text
    assert call["preamble"] == curriculum.item("L001-02").text


async def test_long_is_short_comes_from_the_card_policy_of_the_sura_lesson(
    curriculum: Curriculum,
) -> None:
    w = _world(curriculum)
    await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    lesson = curriculum.lesson("L123")
    assert w.listener.calls[0]["long_is_short"] is CardPolicy().long_is_short(lesson.number)


# ---------- исходы аятов и «всё или ничего» (FR-58, ADR-0076) ----------
async def test_all_ayahs_passed_counts_every_lesson_of_the_sura(curriculum: Curriculum) -> None:
    w = _world(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert _outcomes(result) == [AyahOutcome.CLEAN] * 4
    assert result.reading.passed
    assert set(result.reading.credited) == {
        i.id for lesson in result.sura.lessons for i in lesson.practice_items
    }
    assert await w.status("L123") is LessonStatus.DONE


async def test_ayah_again_is_its_own_outcome_and_the_sura_is_not_counted(
    curriculum: Curriculum,
) -> None:
    """«Ещё раз» — на уровне аята (свой исход ``again``); сура при этом не засчитана."""
    w = _world(curriculum, first={2: "again"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert _outcomes(result) == [
        AyahOutcome.CLEAN, AyahOutcome.AGAIN, AyahOutcome.CLEAN, AyahOutcome.CLEAN,
    ]  # fmt: skip
    assert not result.reading.passed
    assert result.reading.credited == ()
    assert await w.status("L123") is LessonStatus.NEW


async def test_ayah_error_is_pronunciation_and_the_sura_is_not_counted(
    curriculum: Curriculum,
) -> None:
    w = _world(curriculum, first={3: "error"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert _outcomes(result)[2] is AyahOutcome.PRONUNCIATION
    assert not result.reading.passed
    assert result.reading.credited == ()


async def test_reading_cut_short_leaves_last_ayahs_not_reached(curriculum: Curriculum) -> None:
    """Дочитал не до конца: аят без отрезка — «не дочитан», его не слушают вторым проходом."""
    w = _world(curriculum, first={4: "not_reached"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert _outcomes(result) == [AyahOutcome.CLEAN] * 3 + [AyahOutcome.NOT_REACHED]
    assert not result.reading.passed
    assert w.listener.reheard == []


async def test_silence_on_an_ayah_is_again_not_an_error(curriculum: Curriculum) -> None:
    """Модель не слышит аят вовсе (все варианты −inf) — «ещё раз», а не ошибка."""
    w = _world(curriculum, first={1: "unheard"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    first = result.reading.assessment.ayahs[0]
    assert first.outcome is AyahOutcome.AGAIN
    assert first.model_output["unheard"] is True
    json.dumps(dict(first.model_output), allow_nan=False)


async def test_skipped_middle_ayah_is_skipped_and_the_sura_is_not_counted(
    curriculum: Curriculum,
) -> None:
    """Главная ошибка «наизусть» — забытый аят: нет отрезка, а следующие прочитаны →
    ``SKIPPED`` (как у Muaalem, ``domain/sura.py``); соседи не получают ложной «ошибки»; второго
    прохода у пропущенного нет."""
    w = _world(curriculum, first={2: "skipped"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.MEMORY)
    assert _outcomes(result) == [
        AyahOutcome.CLEAN, AyahOutcome.SKIPPED, AyahOutcome.CLEAN, AyahOutcome.CLEAN,
    ]  # fmt: skip
    assert not result.reading.passed
    assert await w.readings.memorized(w.learner.id) == frozenset()
    assert w.listener.reheard == []


async def test_skipped_ayah_by_text_counts_no_lessons(curriculum: Curriculum) -> None:
    w = _world(curriculum, first={3: "skipped"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert _outcomes(result)[2] is AyahOutcome.SKIPPED
    assert result.reading.credited == ()


# ---------- второй проход (PHASE_3 §11.8k) ----------
async def test_only_an_unpassed_ayah_is_heard_a_second_time(curriculum: Curriculum) -> None:
    """Аят, не засчитанный с первого раза, слушается отдельно; засчитанные — нет."""
    w = _world(curriculum, first={2: "again", 4: "error"}, second={2: "again", 4: "again"})
    await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert sorted(w.listener.reheard) == [2, 4]


async def test_second_pass_decides_the_ayah(curriculum: Curriculum) -> None:
    """Решение по аяту — по второму проходу: «ещё раз» → «засчитано» спасает суру."""
    w = _world(curriculum, first={2: "again"}, second={2: "passed"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert w.listener.reheard == [2]
    assert _outcomes(result) == [AyahOutcome.CLEAN] * 4
    assert result.reading.passed


async def test_second_pass_can_turn_an_error_into_again(curriculum: Curriculum) -> None:
    w = _world(curriculum, first={3: "error"}, second={3: "again"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert _outcomes(result)[2] is AyahOutcome.AGAIN


async def test_ayah_model_output_keeps_margins_rival_and_second_pass(
    curriculum: Curriculum,
) -> None:
    """Учителю и исследованию (ADR-0088 «Суры» п. 7): маржи, победивший вариант, вид ошибки,
    «не расслышал», был ли второй проход — JSON без inf и nan (столбец ``model_output``)."""
    w = _world(curriculum, first={2: "error"}, second={2: "error"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    first, second = result.reading.assessment.ayahs[:2]
    for ayah in (first, second):
        output = ayah.model_output
        assert {"margin", "margin_other", "winner", "kind", "unheard", "second_pass"} <= set(output)
        json.dumps(dict(output), allow_nan=False)
    assert first.model_output["second_pass"] is False
    assert second.model_output["second_pass"] is True
    assert second.model_output["margin_other"] < CardPolicy().other_error


# ---------- наизусть, данные, сбои ----------
async def test_memory_reading_on_maroof_marks_memorized_and_counts_no_lessons(
    curriculum: Curriculum,
) -> None:
    w = _world(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.MEMORY)
    assert result.reading.passed
    assert result.reading.credited == ()
    assert await w.readings.memorized(w.learner.id) == {IKHLAS}


async def test_memory_reading_with_an_ayah_again_is_not_memorized(curriculum: Curriculum) -> None:
    """«Ещё раз» у одного аята — сура наизусть не отмечена выученной (🧠 нет)."""
    w = _world(curriculum, first={3: "again"})
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.MEMORY)
    assert not result.reading.passed
    assert await w.readings.memorized(w.learner.id) == frozenset()


async def test_reading_keeps_maroof_version_and_duration(curriculum: Curriculum) -> None:
    w = _world(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert result.reading.model_version == "scripted-maroof-sura"
    assert result.reading.audio_duration_ms == 12000
    assert w.readings.items == [result.reading]
    [(_, _, payload)] = [e for e in w.events.events if e[0] == "sura_read"]
    assert (payload["clean"], payload["total"], payload["passed"]) == (4, 4, 1)


async def test_listener_failure_saves_nothing_and_logs_the_stage(curriculum: Curriculum) -> None:
    w = _world(curriculum, fail=True, fail_stage="decode")
    with pytest.raises(RecognitionError):
        await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert w.readings.items == []
    [(_, _, payload)] = [e for e in w.events.events if e[0] == "sura_recognition_failed"]
    assert payload["stage"] == "decode"


# ---------- любой сбой внутри проверки — RecognitionError(stage="model") (ревью FR-70) ----------
async def _fails_as_model_error(w: World) -> None:
    with pytest.raises(RecognitionError) as error:
        await w.uc.execute(w.learner, b"ogg", IKHLAS, SuraMode.TEXT)
    assert error.value.stage == "model"
    assert w.readings.items == []
    [(_, _, payload)] = [e for e in w.events.events if e[0] == "sura_recognition_failed"]
    assert payload["stage"] == "model"


@pytest.mark.parametrize(
    "error", [KeyError("sh"), ValueError("operands could not be broadcast"), RuntimeError("x")]
)
async def test_unexpected_listener_error_is_a_model_error(
    curriculum: Curriculum, error: Exception
) -> None:
    """Не ``RecognitionError`` из слушателя (KeyError — звука нет в словаре; ValueError numpy) —
    не утекает наружу: иначе обработчик принял бы KeyError за «сура убрана» и показал «кнопка
    устарела»."""
    await _fails_as_model_error(_world(curriculum, error=error))


async def test_failure_while_deciding_an_ayah_is_a_model_error(curriculum: Curriculum) -> None:
    """Сбой в подсчёте баллов аята (внутри ``decide``) — тоже ``RecognitionError``."""
    await _fails_as_model_error(_world(curriculum, first={2: "broken"}))


async def test_unexpected_error_of_the_muaalem_path_is_a_model_error(
    curriculum: Curriculum, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Прежняя проверка (без слушателя суры) — то же правило."""
    w = _world(curriculum)

    async def broken(*args: object, **kwargs: object) -> object:
        raise KeyError("sh")

    monkeypatch.setattr(w.recognizer, "recognize_sura", broken)
    w.uc = replace(w.uc, listener=None)
    await _fails_as_model_error(w)
