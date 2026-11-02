"""Сценарий «прочитать суру» (FR-57…FR-60, ADR-0076): проверка, зачёт, отметка 🧠, данные.

Зачёт по тексту — «всё или ничего»: все аяты чистые → засчитаны все уроки суры. Наизусть — только
отметка 🧠, уроки не засчитываются (решения автора 2026-10-31).
"""

from datetime import timedelta
from uuid import UUID

import pytest

from muallim.application.ports.recognition import RecognitionError
from muallim.application.ports.system import BuildInfo
from muallim.application.use_cases.progress import GetProgress, LessonStatus
from muallim.application.use_cases.sura import ReadSura
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.domain.sura import AyahOutcome, SuraMode
from tests.fakes import (
    FixedClock,
    InMemoryAttempts,
    InMemoryAudio,
    InMemoryLearners,
    InMemorySuraReadings,
    ListEventLog,
    ScriptedSuraRecognizer,
    SequentialIds,
    SpyUoW,
)

DUHA = 93  # ад-Духа: уроки L099 и L100, 11 аятов, басмала перед сурой


class World:
    def __init__(self, curriculum: Curriculum, *, consent: bool = True, skip: int | None = None):
        self.clock = FixedClock()
        self.readings = InMemorySuraReadings()
        self.attempts = InMemoryAttempts(suras=self.readings)
        self.audio = InMemoryAudio()
        self.events = ListEventLog()
        self.recognizer = ScriptedSuraRecognizer(skip_ayah=skip)
        self.learner = Learner(UUID(int=7), 77, "L-00000007", "ru", self.clock.now())
        self.learner.research_consent = consent
        self.learners = InMemoryLearners()
        self.uc = ReadSura(
            curriculum=curriculum,
            recognizer=self.recognizer,
            readings=self.readings,
            attempts=self.attempts,
            audio=self.audio,
            policy=GradingPolicy(),
            uow=SpyUoW(),
            clock=self.clock,
            ids=SequentialIds(),
            events=self.events,
            build=BuildInfo("test-1.0"),
            learners=self.learners,
        )
        self.progress = GetProgress(curriculum, self.attempts, GradingPolicy(), self.clock)

    async def status(self, lesson_id: str) -> LessonStatus:
        return (await self.progress.execute(self.learner)).of(lesson_id).status


async def test_clean_text_reading_counts_every_lesson_of_the_sura(curriculum: Curriculum) -> None:
    w = World(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert result.sura.number == DUHA
    assert result.reading.passed
    assert result.reading.assessment.clean_count == 11
    assert await w.status("L099") is LessonStatus.DONE  # с басмалой — весь урок
    assert await w.status("L100") is LessonStatus.DONE


async def test_one_bad_ayah_counts_nothing(curriculum: Curriculum) -> None:
    """«Всё или ничего» (FR-58): один пропущенный аят — ни одного урока."""
    w = World(curriculum, skip=4)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert not result.reading.passed
    assert result.reading.assessment.ayahs[3].outcome is AyahOutcome.SKIPPED
    assert result.reading.credited == ()
    assert await w.status("L099") is LessonStatus.NEW
    assert await w.status("L100") is LessonStatus.NEW


async def test_memory_reading_marks_memorized_but_counts_no_lessons(curriculum: Curriculum) -> None:
    w = World(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.MEMORY)
    assert result.reading.passed and result.reading.mode is SuraMode.MEMORY
    assert result.reading.credited == ()
    assert await w.readings.memorized(w.learner.id) == {DUHA}
    assert await w.status("L099") is LessonStatus.NEW


async def test_memory_reading_works_for_a_sura_never_opened(curriculum: Curriculum) -> None:
    """Наизусть — доступно всегда, даже если сура не начата (FR-59)."""
    w = World(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", 114, SuraMode.MEMORY)
    assert result.sura.name == "ан-Нас"
    assert not result.reading.studied_by_text


async def test_reading_numbers_and_days_since_last(curriculum: Curriculum) -> None:
    """Для исследования: какая по счёту попытка в этом режиме, сколько дней с прошлого чтения."""
    w = World(curriculum)
    first = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.MEMORY)
    assert (first.reading.attempt_number, first.reading.days_since_last) == (1, None)
    w.clock.current += timedelta(days=3)
    second = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.MEMORY)
    assert (second.reading.attempt_number, second.reading.days_since_last) == (2, 3)
    text = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert (text.reading.attempt_number, text.reading.days_since_last) == (1, 0)


async def test_studied_by_text_is_known_before_memory_reading(curriculum: Curriculum) -> None:
    w = World(curriculum)
    before = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.MEMORY)
    await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    after = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.MEMORY)
    assert not before.reading.studied_by_text
    assert after.reading.studied_by_text


async def test_basmala_goes_to_the_recognizer_as_opening(curriculum: Curriculum) -> None:
    w = World(curriculum)
    await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    (ayahs,) = w.recognizer.calls
    assert [n for _, n, _ in ayahs] == list(range(1, 12))
    assert all(item_id.startswith(("L099", "L100")) for item_id, _, _ in ayahs)


async def test_istiadha_goes_to_the_recognizer_as_preamble(curriculum: Curriculum) -> None:
    """Истиаза перед сурой — необязательное начало, как басмала (ревью кода 2026-10-31)."""
    w = World(curriculum)
    await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert w.recognizer.preambles == [curriculum.item("L001-02").text]


async def test_chunks_know_their_ayahs(curriculum: Curriculum) -> None:
    """Куски 6–10 с — строки для разметки и датасета: секунды и какие аяты покрывают (FR-60)."""
    w = World(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    first, second = result.reading.chunks
    assert (first.start_ms, first.end_ms, second.end_ms) == (0, 6000, 12000)
    assert first.first_ayah == 1
    assert second.last_ayah == 11
    assert first.last_ayah is not None and second.first_ayah is not None
    assert first.last_ayah <= second.first_ayah
    assert "".join(c.heard for c in result.reading.chunks) == result.reading.assessment.heard


@pytest.mark.parametrize("consent", [True, False])
async def test_voice_is_kept_only_with_consent(curriculum: Curriculum, consent: bool) -> None:
    w = World(curriculum, consent=consent)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert (result.reading.audio_sha256 is not None) is consent
    assert bool(w.audio.files) is consent


async def test_reading_keeps_versions_for_research(curriculum: Curriculum) -> None:
    w = World(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    reading = result.reading
    assert reading.model_version == "scripted"
    assert reading.curriculum_version == curriculum.version
    assert reading.app_version == "test-1.0"
    assert reading.audio_duration_ms == 12000
    assert w.readings.items == [reading]
    assert any(name == "sura_read" for name, _, _ in w.events.events)


async def test_recognition_failure_saves_nothing(curriculum: Curriculum) -> None:
    w = World(curriculum)
    w.recognizer.fail = True
    with pytest.raises(RecognitionError):
        await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert w.readings.items == []
    assert any(name == "sura_recognition_failed" for name, _, _ in w.events.events)


async def test_unknown_sura_is_an_error(curriculum: Curriculum) -> None:
    w = World(curriculum)
    with pytest.raises(KeyError):
        await w.uc.execute(w.learner, b"ogg", 50, SuraMode.TEXT)


async def test_passed_whole_sura_moves_continue_past_the_sura(curriculum: Curriculum) -> None:
    """Решение автора 2026-10-31: сдал суру целиком — «Продолжить» ведёт на следующий урок."""
    w = World(curriculum)
    w.learner.current_item_id = "L099-03"  # ученик в середине первой части ад-Духа
    await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert w.learner.current_item_id == curriculum.lesson("L101").items[0].id
    assert (await w.learners.get_by_telegram_id(77)) is w.learner


async def test_cursor_ahead_of_the_sura_stays(curriculum: Curriculum) -> None:
    """Ученик уже дальше суры (вернулся повторить) — курсор назад не двигаем."""
    w = World(curriculum)
    w.learner.current_item_id = "L110-02"
    await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert w.learner.current_item_id == "L110-02"


async def test_failed_or_memory_reading_keeps_the_cursor(curriculum: Curriculum) -> None:
    for world, mode in (
        (World(curriculum, skip=2), SuraMode.TEXT),
        (World(curriculum), SuraMode.MEMORY),
    ):
        world.learner.current_item_id = "L099-03"
        await world.uc.execute(world.learner, b"ogg", DUHA, mode)
        assert world.learner.current_item_id == "L099-03"


async def test_reading_keeps_the_grading_policy(curriculum: Curriculum) -> None:
    """След решения (ADR-0019): по какому порогу оценено — порог может смениться (TD-FN-116)."""
    w = World(curriculum)
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.TEXT)
    assert result.reading.policy == GradingPolicy()
