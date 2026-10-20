"""Сценарии бота на тестовых портах: без Telegram, БД, модели и без настоящего учебного контента.

Контент меняет человек (curriculum/), поэтому сценарии проверяются на своей маленькой программе.
"""

from dataclasses import dataclass
from datetime import timedelta

import pytest

from muallim.application.feedback import FeedbackCatalog
from muallim.application.ports.recognition import RecognitionError
from muallim.application.ports.system import BuildInfo
from muallim.application.transcription import as_text
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.learners import (
    DeleteMyData,
    EnsureLearner,
    Questionnaire,
    SetFeedbackLanguage,
    SetResearchConsent,
)
from muallim.application.use_cases.progress import GetProgress, LessonStatus
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.reports import ReportMistake
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem
from muallim.domain.learner import ArabicReading, ConsentKind, Learner, NativeLanguage
from muallim.domain.policy import GradingPolicy, Verdict
from muallim.domain.report import ReportReason
from tests.fakes import (
    FixedClock,
    InMemoryAttempts,
    InMemoryAudio,
    InMemoryLearners,
    InMemoryProfiles,
    InMemoryReferenceAudio,
    ListErasureLog,
    ListEventLog,
    ScriptedReadingGuide,
    ScriptedRecognizer,
    SequentialIds,
    SpyUoW,
)


@dataclass
class World:
    curriculum: Curriculum
    catalog: FeedbackCatalog
    learners: InMemoryLearners
    attempts: InMemoryAttempts
    audio: InMemoryAudio
    recognizer: ScriptedRecognizer
    uow: SpyUoW
    events: ListEventLog
    clock: FixedClock
    ids: SequentialIds
    erasures: ListErasureLog

    def ensure(self) -> EnsureLearner:
        return EnsureLearner(self.learners, self.uow, self.clock, self.ids, self.events)

    def consent(self) -> SetResearchConsent:
        return SetResearchConsent(
            self.learners, self.attempts, self.audio, self.uow, self.clock, self.events,
            self.erasures,
        )  # fmt: skip

    def delete(self) -> DeleteMyData:
        return DeleteMyData(
            self.learners, self.attempts, self.audio, self.uow, self.events, self.erasures
        )

    def cards(self) -> OpenItem:
        return OpenItem(self.curriculum, self.learners, self.uow, self.events)

    def assess(self) -> AssessRecitation:
        return AssessRecitation(
            self.curriculum, self.cards(), self.recognizer, self.attempts, self.audio,
            GradingPolicy(), self.catalog, self.uow, self.clock, self.ids, self.events,
            BuildInfo("test-1.0"),
        )  # fmt: skip

    def progress(self) -> GetProgress:
        return GetProgress(self.curriculum, self.attempts, GradingPolicy(), self.clock)

    async def learner(self) -> Learner:
        learner, _ = await self.ensure().execute(42, "ru")
        return learner


LETTERS = "أبتثجحخدذرزسشصضطظعغفقكلمنوهي"  # L01-14 — صَ


@pytest.fixture(scope="module")
def course(curriculum: Curriculum) -> Curriculum:
    letters = tuple(
        LessonItem(f"L01-{i:02}", f"{c}\u064e", ItemKind.LETTER, "x", name="x")
        for i, c in enumerate(LETTERS, start=1)
    )
    lines = tuple(
        LessonItem(f"L02-{i:02}", text, ItemKind.LINE, "")
        for i, text in enumerate(["رَرْ رِرْ", "أَزْ إِزْ", "مَرْمَرُ"], start=1)
    )
    return Curriculum(
        "test", "test-1", "Тест",
        (Lesson("L01", 1, "Буквы", letters), Lesson("L02", 2, "Строки", lines)),
        curriculum.lexicon,
    )  # fmt: skip


@pytest.fixture
def w(course: Curriculum, catalog: FeedbackCatalog) -> World:
    journal: list[str] = []  # общий журнал: commit и удаление файлов — проверяем порядок
    attempts = InMemoryAttempts()
    return World(
        course, catalog, InMemoryLearners(cascade_to=attempts), attempts,
        InMemoryAudio(journal=journal),
        ScriptedRecognizer(), SpyUoW(journal=journal), ListEventLog(), FixedClock(),
        SequentialIds(), ListErasureLog(journal=journal),
    )  # fmt: skip


# ---------- регистрация ----------
async def test_new_learner_gets_pseudonym_and_no_consent(w: World) -> None:
    learner, created = await w.ensure().execute(42, "ru")
    assert created and learner.pseudonym.startswith("L-") and not learner.research_consent
    assert str(learner.telegram_user_id) not in learner.pseudonym


async def test_existing_learner_is_not_recreated(w: World) -> None:
    first, _ = await w.ensure().execute(42, "ru")
    again, created = await w.ensure().execute(42, "ru")
    assert again is first and not created


async def test_missing_language_defaults_to_ru(w: World) -> None:
    learner, _ = await w.ensure().execute(7, None)
    assert learner.language == "ru"


# ---------- согласие ----------
async def test_consent_change_is_journaled(w: World) -> None:
    learner = await w.learner()
    uc = w.consent()
    await uc.execute(learner, True)
    await uc.execute(learner, False)
    assert [c.granted for c in w.learners.consents] == [True, False]
    assert all(c.kind is ConsentKind.RESEARCH_AUDIO for c in w.learners.consents)
    assert not learner.research_consent


async def test_withdrawn_consent_deletes_recordings_after_commit(w: World) -> None:
    """privacy.md: голос хранится «до отзыва согласия». Попытки (баллы) остаются для прогресса."""
    learner = await w.learner()
    await w.consent().execute(learner, True)
    await w.assess().execute(learner, b"ogg")
    sha = w.attempts.items[0][0].audio_sha256
    assert sha is not None
    w.audio.journal.clear()
    await w.consent().execute(learner, False)
    assert w.audio.files == {}
    assert [a.audio_sha256 for a, _ in w.attempts.items] == [None]
    # файл удаляется только после фиксации в БД: иначе при сбое БД ссылается на пустоту
    files = [e for e in w.audio.journal if not e.startswith("erase:")]
    assert files == ["commit", f"delete:{sha}"]


async def test_withdrawn_consent_keeps_recording_shared_with_another_learner(w: World) -> None:
    """Ученик переслал чужое голосовое — та же запись (тот же SHA-256) у двоих."""
    first = await w.learner()
    second, _ = await w.ensure().execute(43, "ru")
    for learner in (first, second):
        await w.consent().execute(learner, True)
        await w.assess().execute(learner, b"same voice")
    await w.consent().execute(first, False)
    assert len(w.audio.files) == 1  # запись второго ученика на месте


async def test_erasure_is_logged_before_commit(w: World) -> None:
    """Журнал удалений — вне БД: после восстановления старой копии удаление повторяется (TD-DB-05).

    Удаление и отзыв — до commit: сбой commit не теряет намерение ученика, повтор безвреден.
    Согласие — после commit: журнал не должен утверждать согласие, которого нет в БД.
    """
    learner = await w.learner()
    w.audio.journal.clear()
    await w.consent().execute(learner, True)
    await w.consent().execute(learner, False)
    await w.delete().execute(learner)
    assert [a for a, _ in w.erasures.entries] == ["grant", "withdraw", "delete"]
    assert all(lid == learner.id for _, lid in w.erasures.entries)
    order = [e for e in w.audio.journal if e.startswith(("erase:", "commit"))]
    assert order == ["commit", "erase:grant", "erase:withdraw", "commit", "erase:delete", "commit"]


async def test_granting_consent_deletes_nothing(w: World) -> None:
    learner = await w.learner()
    await w.consent().execute(learner, True)
    assert not any(e.startswith("delete:") for e in w.audio.journal)


# ---------- анкета (FR-44) ----------
def _questionnaire(w: World) -> Questionnaire:
    consent = w.consent()
    return Questionnaire(InMemoryProfiles(), consent, w.uow, w.clock, w.events)


async def test_questionnaire_asked_only_after_research_consent(w: World) -> None:
    learner, q = await w.learner(), _questionnaire(w)
    assert not await q.needed(learner)  # без согласия эти данные не нужны и не собираются
    await w.consent().execute(learner, True)
    assert await q.needed(learner)


async def test_questionnaire_saved_once_and_not_asked_again(w: World) -> None:
    learner, q = await w.learner(), _questionnaire(w)
    learner.research_consent = True
    assert await q.answer(learner, adult=True, native=NativeLanguage.KK, reading=ArabicReading.NONE)
    profile = await q.profiles.get(learner.id)
    assert profile is not None
    assert (profile.adult, profile.native_language, profile.arabic_reading) == (
        True, NativeLanguage.KK, ArabicReading.NONE,
    )  # fmt: skip
    assert profile.answered_at < w.clock.now() and profile.questionnaire_version  # часы тикают
    assert not await q.needed(learner)
    # второй ответ не перезаписывает первый: анкета — один раз
    assert not await q.answer(learner, adult=True, native=NativeLanguage.RU, reading=None)
    assert (await q.profiles.get(learner.id)) == profile


async def test_minor_keeps_learning_but_voice_is_not_kept(w: World) -> None:
    learner, q = await w.learner(), _questionnaire(w)
    await w.consent().execute(learner, True)
    assert await q.answer(learner, adult=False)
    assert not learner.research_consent  # участие в исследовании — только 18+ (TD-SEC-05)
    assert [c.granted for c in w.learners.consents] == [True, False]
    profile = await q.profiles.get(learner.id)
    assert profile is not None and not profile.adult and profile.native_language is None
    assert not await q.needed(learner)


async def test_questionnaire_event_has_no_answers(w: World) -> None:
    learner, q = await w.learner(), _questionnaire(w)
    learner.research_consent = True
    await q.answer(
        learner, adult=True, native=NativeLanguage.RU, reading=ArabicReading.SOME_LETTERS
    )
    assert ("questionnaire_answered", learner.id, {}) in w.events.events  # ответы — только в анкете
    assert w.uow.commits >= 1


# ---------- проверка чтения ----------
async def test_correct_reading_is_excellent_and_saved(w: World) -> None:
    learner = await w.learner()
    result = await w.assess().execute(learner, b"ogg")
    assert result.verdict is Verdict.EXCELLENT and result.feedback == ()
    ((attempt, _),) = w.attempts.items
    assert attempt.item_id == w.curriculum.first_item().id
    assert attempt.curriculum_version == w.curriculum.version
    assert attempt.model_version == "scripted"


async def test_errors_are_explained_and_stored_with_attempt(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L01-14")  # صَ
    w.recognizer.heard = "سَ"
    result = await w.assess().execute(learner, b"ogg")
    assert result.verdict is Verdict.FAILED
    (shown,) = result.feedback
    assert "с̣" in shown.text and shown.more  # коротко + «подробнее»
    ((_, stored),) = w.attempts.items
    assert len(stored) == 1 and "«ص»" in stored[0]  # в БД — полный текст ошибки


async def test_audio_not_stored_without_consent(w: World) -> None:
    learner = await w.learner()
    await w.assess().execute(learner, b"ogg")
    assert w.audio.files == {} and w.attempts.items[0][0].audio_sha256 is None


async def test_audio_stored_with_consent(w: World) -> None:
    learner = await w.learner()
    learner.research_consent = True
    await w.assess().execute(learner, b"ogg")
    sha = w.attempts.items[0][0].audio_sha256
    assert sha is not None and w.audio.files[sha] == b"ogg"


async def test_recognition_failure_saves_nothing(w: World) -> None:
    learner = await w.learner()
    w.recognizer.fail = True
    with pytest.raises(RecognitionError):
        await w.assess().execute(learner, b"ogg")
    assert w.attempts.items == []


async def test_recognition_failure_is_logged_and_committed(w: World) -> None:
    """NFR-REL-02, QAS-04: сбой виден в журнале, иначе долю сбоев не посчитать."""
    learner = await w.learner()
    item_id = w.cards().current(learner).id
    w.recognizer.fail, w.recognizer.fail_stage = True, "decode"
    commits = w.uow.commits
    with pytest.raises(RecognitionError):
        await w.assess().execute(learner, b"ogg")
    event, learner_id, payload = w.events.events[-1]
    assert (event, learner_id) == ("recognition_failed", learner.id)
    assert payload["item_id"] == item_id and payload["stage"] == "decode"
    assert isinstance(payload["processing_ms"], int)
    assert set(payload) == {"item_id", "stage", "processing_ms"}  # без текста ошибки
    assert w.uow.commits == commits + 1


async def test_recognition_failure_keeps_current_item(w: World) -> None:
    learner = await w.learner()
    before = w.cards().current(learner).id
    w.recognizer.fail = True
    with pytest.raises(RecognitionError):
        await w.assess().execute(learner, b"ogg")
    assert w.cards().current(learner).id == before


def test_recognition_error_stage_defaults_to_model() -> None:
    assert RecognitionError("x").stage == "model"
    assert RecognitionError("x", stage="decode").stage == "decode"


async def test_next_item_follows_current(w: World) -> None:
    learner = await w.learner()
    result = await w.assess().execute(learner, b"ogg")
    assert result.next_item == w.curriculum.next_item(result.item.id)


async def test_next_after_last_card_is_next_lesson(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L01-28")
    result = await w.assess().execute(learner, b"ogg")
    assert result.next_item is not None and result.next_item.id == "L02-01"


async def test_lesson_completed_when_every_line_mastered(w: World) -> None:
    learner = await w.learner()
    flags = []
    for item_id in ("L02-01", "L02-02", "L02-03"):
        await w.cards().execute(learner, item_id)
        flags.append((await w.assess().execute(learner, b"ogg")).lesson_completed)
    assert flags == [False, False, True]
    again = await w.assess().execute(learner, b"ogg")  # повтор уже пройденного — без праздника
    assert again.lesson_completed is False


async def test_attempt_is_logged_as_event(w: World) -> None:
    learner = await w.learner()
    await w.assess().execute(learner, b"ogg")
    assert ("attempt_assessed", learner.id) in [(e, lid) for e, lid, _ in w.events.events]


# ---------- карточки ----------
async def test_open_item_remembers_position(w: World) -> None:
    learner = await w.learner()
    item = await w.cards().execute(learner, "L02-03")
    assert learner.current_item_id == "L02-03" and w.cards().current(learner) == item


async def test_open_unknown_item_raises(w: World) -> None:
    learner = await w.learner()
    with pytest.raises(KeyError):
        await w.cards().execute(learner, "L99-01")


async def test_removed_item_falls_back_to_first(w: World) -> None:
    learner = await w.learner()
    learner.current_item_id = "L99-01"
    assert w.cards().current(learner) == w.curriculum.first_item()


# ---------- прогресс ----------
async def test_progress_counts_mastered_and_weak(w: World) -> None:
    learner = await w.learner()
    await w.assess().execute(learner, b"1")  # L01-01 верно
    await w.cards().execute(learner, "L01-02")
    w.recognizer.heard = "سِ"
    await w.assess().execute(learner, b"2")  # L01-02 с ошибками
    progress = await w.progress().execute(learner)
    first = progress.lessons[0]
    assert (first.mastered, [i.id for i in first.weak]) == (1, ["L01-02"])
    assert first.percent == round(100 / 28) and progress.attempts_total == 2


async def test_lesson_statuses_new_started_done(w: World) -> None:
    learner = await w.learner()
    for item_id in ("L02-01", "L02-02", "L02-03"):
        await w.cards().execute(learner, item_id)
        await w.assess().execute(learner, b"ogg")
    await w.cards().execute(learner, "L01-01")
    await w.assess().execute(learner, b"ogg")
    statuses = {lp.lesson.id: lp.status for lp in (await w.progress().execute(learner)).lessons}
    assert statuses == {"L01": LessonStatus.STARTED, "L02": LessonStatus.DONE}


async def test_continue_from_where_learner_left(w: World) -> None:
    learner = await w.learner()
    assert (await w.progress().execute(learner)).continue_item == w.curriculum.first_item()
    await w.cards().execute(learner, "L02-02")
    item = (await w.progress().execute(learner)).continue_item
    assert item is not None and item.id == "L02-02"


async def test_streak_counts_consecutive_days(w: World) -> None:
    learner = await w.learner()
    for _ in range(3):  # FixedClock: каждый вызов +1 с — все попытки сегодня
        await w.assess().execute(learner, b"ogg")
    p = await w.progress().execute(learner)
    assert (p.streak_days, p.today_attempts) == (1, 3)
    w.clock.current += timedelta(days=1)
    await w.assess().execute(learner, b"ogg")
    assert (await w.progress().execute(learner)).streak_days == 2
    w.clock.current += timedelta(days=3)  # пропуск — серия обнулилась
    assert (await w.progress().execute(learner)).streak_days == 0


# ---------- удаление данных ----------
async def test_delete_my_data_removes_learner_attempts_and_audio(w: World) -> None:
    learner = await w.learner()
    learner.research_consent = True
    await w.assess().execute(learner, b"ogg")
    await w.delete().execute(learner)
    assert await w.learners.get_by_telegram_id(42) is None
    assert w.audio.files == {}
    assert w.events.events[-1] == ("learner_deleted", None, {})


async def test_delete_my_data_removes_files_only_after_commit(w: World) -> None:
    learner = await w.learner()
    learner.research_consent = True
    await w.assess().execute(learner, b"ogg")
    sha = w.attempts.items[0][0].audio_sha256
    w.audio.journal.clear()
    await w.delete().execute(learner)
    files = [e for e in w.audio.journal if not e.startswith("erase:")]
    assert files == ["commit", f"delete:{sha}"]


async def test_delete_my_data_keeps_recording_shared_with_another_learner(w: World) -> None:
    first = await w.learner()
    second, _ = await w.ensure().execute(43, "ru")
    for learner in (first, second):
        learner.research_consent = True
        await w.assess().execute(learner, b"same voice")
    await w.delete().execute(first)
    assert len(w.audio.files) == 1


# ---------- след решения (FR-24, ADR-0019) ----------
async def test_attempt_keeps_full_decision_trace(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L01-14")  # صَ
    w.recognizer.heard = "سَ"
    result = await w.assess().execute(learner, b"ogg")
    a = result.attempt
    assert a.reference_variant == "waqf"  # «صَ» ближе к эталону с остановкой
    assert [(c.variant, c.assessment.reference) for c in a.candidates] == [
        ("wasl", "صَ\u064e"), ("waqf", "صَ"),
    ]  # fmt: skip
    assert a.candidates[1].assessment.score == a.assessment.score
    assert a.model_output == {"phonemes": "سَ"}
    assert (a.policy.pass_threshold, a.policy.excellent_threshold) == (80, 90)
    assert a.app_version == "test-1.0" and a.feedback_language == "ru"


async def test_heard_is_transcribed_for_learner(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L01-14")
    w.recognizer.heard = "سَ"
    result = await w.assess().execute(learner, b"ogg")
    assert result.heard_transcription == "са"


async def test_result_compares_expected_and_heard_by_syllables(w: World) -> None:
    """FR-43: «Нужно» и «У тебя» по слогам, слог с ошибкой отмечен, его же — потренировать."""
    learner = await w.learner()
    await w.cards().execute(learner, "L02-03")  # مَرْمَرُ
    w.recognizer.heard = "مَلْمَرُ"
    result = await w.assess().execute(learner, b"ogg")
    assert [t for t, _ in result.heard_reading] == ["мал", "ма", "ру"]
    assert [wrong for _, wrong in result.expected_reading] == [True, False, False]
    assert result.practice == ("мар",)


async def test_unread_tail_is_one_item_and_marked_on_result(w: World) -> None:
    """Прочитан только первый слог «мар» — один пункт «не дочитана», дальше — непрочитанное."""
    learner = await w.learner()
    await w.cards().execute(learner, "L02-03")  # مَرْمَرُ
    w.recognizer.heard = "مَرْ"
    result = await w.assess().execute(learner, b"ogg")
    assert result.unread_from == 1
    (m,) = result.feedback
    assert m.text.startswith("📖")
    # непрочитанное — не ошибки: не подчёркнуто и не в «скажи 3 раза»
    assert [wrong for _, wrong in result.expected_reading] == [False, False, False]
    assert result.practice == ()


async def test_finishing_the_line_is_not_counted_as_fixed(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L02-03")  # مَرْمَرُ
    w.recognizer.heard = "مَرْ"
    await w.assess().execute(learner, b"ogg")
    w.recognizer.heard = None
    result = await w.assess().execute(learner, b"ogg")
    assert result.previous_score is not None and result.fixed == ()


async def test_every_error_is_stored_with_its_own_message(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L02-03")
    w.recognizer.heard = "مَرْ"
    result = await w.assess().execute(learner, b"ogg")
    ((attempt, messages),) = w.attempts.items
    assert len(messages) == len(attempt.assessment.errors) > len(result.feedback)


async def test_second_try_shows_score_before_and_fixed_syllables(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L02-03")  # مَرْمَرُ
    w.recognizer.heard = "مَلْمَرُ"
    first = await w.assess().execute(learner, b"ogg")
    assert first.previous_score is None and first.fixed == ()
    w.recognizer.heard = None  # теперь верно
    second = await w.assess().execute(learner, b"ogg")
    assert second.previous_score == first.attempt.assessment.score
    assert second.fixed == ("мар",)


async def test_previous_try_is_of_the_same_line_only(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L02-02")
    await w.assess().execute(learner, b"ogg")
    await w.cards().execute(learner, "L02-03")
    result = await w.assess().execute(learner, b"ogg")
    assert result.previous_score is None


async def test_correct_reading_has_nothing_to_practice(w: World) -> None:
    learner = await w.learner()
    result = await w.assess().execute(learner, b"ogg")
    assert result.practice == () and not any(wrong for _, wrong in result.expected_reading)


async def test_result_legend_explains_special_marks(w: World) -> None:
    learner = await w.learner()
    await w.cards().execute(learner, "L01-14")  # صَ
    result = await w.assess().execute(learner, b"ogg")
    assert any("твёрд" in line for line in result.legend)


# ---------- «как читается» на карточке (FR-43) ----------
async def test_how_to_read_gives_syllables_and_legend(w: World) -> None:
    learner = await w.learner()
    shown = HowToRead(ScriptedReadingGuide(), w.catalog).execute(
        learner, w.curriculum.item("L01-14")
    )
    assert shown is not None
    assert as_text(shown.reading) == "с̣а" and shown.legend


async def test_how_to_read_is_absent_without_phonetizer(w: World) -> None:
    learner = await w.learner()
    guide = ScriptedReadingGuide(fail=True)
    assert HowToRead(guide, w.catalog).execute(learner, w.curriculum.item("L01-14")) is None


# ---------- язык объяснений (FR-22) ----------
async def test_feedback_language_is_saved_and_validated(w: World) -> None:
    learner = await w.learner()
    uc = SetFeedbackLanguage(w.learners, w.catalog, w.uow, w.events)
    assert await uc.execute(learner, "ru") is True
    assert learner.feedback_language == "ru"
    assert await uc.execute(learner, "kk") is False  # черновик выключен
    assert learner.feedback_language == "ru"


# ---------- «Бот ошибся» (FR-23, ADR-0020) ----------
async def test_learner_can_dispute_own_attempt(w: World) -> None:
    learner = await w.learner()
    result = await w.assess().execute(learner, b"ogg")
    uc = ReportMistake(w.attempts, w.uow, w.clock, w.events)
    assert await uc.execute(learner, result.attempt.id, ReportReason.READ_CORRECTLY) is True
    (report,) = w.attempts.reports
    assert (report.attempt_id, report.learner_id, report.reason) == (
        result.attempt.id, learner.id, ReportReason.READ_CORRECTLY,
    )  # fmt: skip
    assert w.events.events[-1][0] == "attempt_disputed"


async def test_second_dispute_of_same_attempt_is_not_counted_twice(w: World) -> None:
    """Ученик нажал «Бот ошибся» дважды — одна жалоба, одно событие (TD-DB-02)."""
    learner = await w.learner()
    result = await w.assess().execute(learner, b"ogg")
    uc = ReportMistake(w.attempts, w.uow, w.clock, w.events)
    assert await uc.execute(learner, result.attempt.id, ReportReason.READ_CORRECTLY) is True
    assert await uc.execute(learner, result.attempt.id, ReportReason.OTHER) is True
    assert len(w.attempts.reports) == 1
    assert [e for e, *_ in w.events.events].count("attempt_disputed") == 1


async def test_cannot_dispute_someone_elses_attempt(w: World) -> None:
    learner = await w.learner()
    result = await w.assess().execute(learner, b"ogg")
    stranger, _ = await w.ensure().execute(777, "ru")
    uc = ReportMistake(w.attempts, w.uow, w.clock, w.events)
    assert await uc.execute(stranger, result.attempt.id, ReportReason.OTHER) is False
    assert w.attempts.reports == []


# ---------- эталонное аудио (FR-20, ADR-0018) ----------
async def test_teacher_records_reference_others_cannot(w: World) -> None:
    learner = await w.learner()  # telegram id 42
    library = InMemoryReferenceAudio()
    uc = RecordReference(library, frozenset({42}), w.uow, w.events)
    assert await uc.execute(learner, "L02-01", b"voice") is True
    assert library.files == {"L02-01": b"voice"}
    assert w.events.events[-1] == ("reference_recorded", learner.id, {"item_id": "L02-01"})
    stranger, _ = await w.ensure().execute(777, "ru")
    assert await uc.execute(stranger, "L02-02", b"x") is False and "L02-02" not in library.files


async def test_reference_audio_is_returned_and_logged(w: World) -> None:
    learner = await w.learner()
    library = InMemoryReferenceAudio({"L01-02": b"voice"})
    uc = GetReferenceAudio(library, w.uow, w.events)
    assert await uc.execute(learner, "L01-02") == b"voice"
    assert w.events.events[-1] == ("reference_played", learner.id, {"item_id": "L01-02"})
    assert await uc.execute(learner, "L01-03") is None


# ---------- ID ученика (FR-25) ----------
async def test_pseudonym_is_stable_and_derived_from_internal_id(w: World) -> None:
    learner = await w.learner()
    assert learner.pseudonym == f"L-{learner.id.hex[:8]}"


# ---------- закрепление (ADR-0025) ----------
async def test_quiz_needs_started_letters_and_logs_answers(curriculum: Curriculum) -> None:
    from muallim.application.use_cases.quiz import PracticeQuiz  # noqa: PLC0415

    attempts, events, uow = InMemoryAttempts(), ListEventLog(), SpyUoW()
    learners = InMemoryLearners()
    learner, _ = await EnsureLearner(learners, uow, FixedClock(), SequentialIds(), events).execute(
        1, "ru"
    )
    quiz = PracticeQuiz(curriculum, attempts, events, uow)
    assert await quiz.next(learner, seed=1) is None  # ещё ничего не читал
    letters = [les for les in curriculum.lessons if les.section == "letter"][:3]
    learner.current_item_id = letters[2].items[0].id
    for les in letters[:2]:
        await attempts.add(_attempt_for(learner, les.items[0].id), ())
    q = await quiz.next(learner, seed=5)
    heads = {i.id for les in letters for i in les.items if i.kind is ItemKind.LETTER}
    assert q is not None and q.item_id in heads
    again = await quiz.answer(learner, q.item_id, q.vowel, q.seed, q.answer)
    assert again == q
    assert events.events[-1] == (
        "quiz_answered", learner.id, {"item_id": q.item_id, "vowel": q.vowel, "correct": True},
    )  # fmt: skip


def _attempt_for(learner: Learner, item_id: str):  # type: ignore[no-untyped-def]
    from muallim.domain.assessment import assess  # noqa: PLC0415
    from muallim.domain.attempt import Attempt  # noqa: PLC0415

    a = assess("بَ", "بَ")
    return Attempt(
        SequentialIds().new_id(), learner.id, item_id, "v", "m", a, Verdict.EXCELLENT,
        None, None, 1, FixedClock().now(),
    )  # fmt: skip


async def test_progress_week_marks_days_with_attempts(w: World) -> None:
    """Неделя для картинки прогресса (ADR-0050): 7 дней, последний — сегодня."""
    learner = await w.learner()
    await w.assess().execute(learner, b"1")
    progress = await w.progress().execute(learner)
    assert progress.week == (False,) * 6 + (True,)
    assert progress.today == w.clock.current.date()


# ---------- «Продолжить» после последнего шага урока (FR-49, FR-50) ----------
@pytest.fixture
def steps(course: Curriculum, catalog: FeedbackCatalog) -> World:
    """Уроки с правилом и таблицей алфавита: последний шаг бывает и без чтения."""
    rule = ItemKind.RULE
    lessons = (
        Lesson("S01", 1, "Начало", (
            LessonItem("S01-01", "بَ", rule, "x", name="x"),
            LessonItem("S01-02", "رَرْ رِرْ", ItemKind.LINE, ""),
            LessonItem("S01-03", "أَزْ إِزْ", ItemKind.LINE, ""),
        )),
        Lesson("S02", 2, "Алфавит", (
            LessonItem("S02-01", "بَ", rule, "x", name="x"),
            LessonItem("S02-02", "ا ب ت", ItemKind.ALPHABET, "", name="элиф · бэ · тэ"),
        )),
        Lesson("S03", 3, "Строки", (
            LessonItem("S03-01", "مَرْمَرُ", ItemKind.LINE, ""),
            LessonItem("S03-02", "رَرْ رِرْ", ItemKind.LINE, ""),
        )),
    )  # fmt: skip
    cur = Curriculum("test", "steps-1", "Тест", lessons, course.lexicon)
    attempts = InMemoryAttempts()
    return World(
        cur, catalog, InMemoryLearners(cascade_to=attempts), attempts, InMemoryAudio(),
        ScriptedRecognizer(), SpyUoW(), ListEventLog(), FixedClock(), SequentialIds(),
        ListErasureLog(),
    )  # fmt: skip


async def _read(w: World, learner: Learner, item_id: str, heard: str | None = None) -> None:
    await w.cards().execute(learner, item_id)
    w.recognizer.heard = heard
    await w.assess().execute(learner, b"ogg")


async def _continue(w: World, learner: Learner) -> str | None:
    item = (await w.progress().execute(learner)).continue_item
    return item.id if item else None


async def test_continue_after_finished_lesson_is_next_lesson(steps: World) -> None:
    learner = await steps.learner()
    await _read(steps, learner, "S01-02")
    await _read(steps, learner, "S01-03")
    assert learner.current_item_id == "S01-03"
    p = await steps.progress().execute(learner)
    assert p.of("S01").status is LessonStatus.DONE
    assert await _continue(steps, learner) == "S02-01"


async def test_continue_after_failed_last_step_is_next_lesson(steps: World) -> None:
    """Не получилось — можно идти дальше; строка вернётся в «повторить»."""
    learner = await steps.learner()
    await _read(steps, learner, "S01-03", heard="سَ")
    p = await steps.progress().execute(learner)
    assert p.of("S01").status is not LessonStatus.DONE
    assert await _continue(steps, learner) == "S02-01"


async def test_failed_line_stays_in_repeat_list(steps: World) -> None:
    learner = await steps.learner()
    await _read(steps, learner, "S01-03", heard="سَ")
    p = await steps.progress().execute(learner)
    assert [i.id for i in p.of("S01").weak] == ["S01-03"]


async def test_continue_after_last_step_without_reading_is_next_lesson(steps: World) -> None:
    """Последний шаг — таблица алфавита: читать нечего, дальше — следующий урок."""
    learner = await steps.learner()
    await steps.cards().execute(learner, "S02-02")
    assert await _continue(steps, learner) == "S03-01"


async def test_continue_stays_on_untried_last_step(steps: World) -> None:
    learner = await steps.learner()
    await steps.cards().execute(learner, "S01-03")
    assert await _continue(steps, learner) == "S01-03"


async def test_continue_stays_inside_lesson_if_not_on_last_step(steps: World) -> None:
    learner = await steps.learner()
    await _read(steps, learner, "S01-02")
    await _read(steps, learner, "S01-03")
    await steps.cards().execute(learner, "S01-02")  # вернулся повторить
    assert await _continue(steps, learner) == "S01-02"


async def test_continue_after_last_lesson_of_program_stays_on_it(steps: World) -> None:
    """После последнего урока программы следующего нет — остаёмся, где были."""
    learner = await steps.learner()
    await _read(steps, learner, "S03-01")
    await _read(steps, learner, "S03-02")
    assert await _continue(steps, learner) == "S03-02"


async def test_quiz_options_are_from_letters_the_learner_started(curriculum: Curriculum) -> None:
    """Ответы-обманки — из начатых букв; тот же вопрос восстанавливается по кнопке."""
    from muallim.application.use_cases.quiz import PracticeQuiz  # noqa: PLC0415

    attempts, events, uow = InMemoryAttempts(), ListEventLog(), SpyUoW()
    learner, _ = await EnsureLearner(
        InMemoryLearners(), uow, FixedClock(), SequentialIds(), events
    ).execute(2, "ru")
    letters = [les for les in curriculum.lessons if les.section == "letter"][:3]  # ء ر ز
    for les in letters:
        await attempts.add(_attempt_for(learner, les.items[0].id), ())
    allowed = {
        s
        for les in letters
        for i in les.items
        if i.kind is ItemKind.LETTER
        for s in i.sound.split(" · ")
    }
    quiz = PracticeQuiz(curriculum, attempts, events, uow)
    for seed in range(20):
        q = await quiz.next(learner, seed=seed)
        assert q is not None
        assert set(q.options) <= allowed, (seed, q.options)
        assert await quiz.answer(learner, q.item_id, q.vowel, q.seed, 0) == q
