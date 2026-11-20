"""«Прочитай ещё раз» нигде не засчитано; освоение — по вердикту (FR-70 п. 6, 8; ADR-0088 п. 6, 7).

Тексты ученику пишет человек: здесь только проверяется, что строка для каждого вердикта и каждой
подсказки есть в `presentation/telegram/texts.py` и не пустая; содержание — не проверяется.
Предложенный ключ подсказок — ``texts.CARD_HINTS``: вид подсказки → строка.
"""

from dataclasses import replace
from uuid import UUID

import pytest

from muallim.application.feedback import FeedbackRenderer
from muallim.application.use_cases.progress import GetProgress, LessonStatus
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import Assessment, assess
from muallim.domain.attempt import Attempt
from muallim.domain.card_check import LAST_VOWEL, OTHER_SYLLABLE
from muallim.domain.curriculum import Curriculum
from muallim.domain.policy import CardPolicy, GradingPolicy, Verdict
from muallim.domain.quiz import read_passed
from muallim.presentation.telegram import screens, texts
from tests.fakes import FixedClock, InMemoryAttempts

LEARNER = UUID(int=7)


@pytest.mark.parametrize(
    ("verdict", "passed"),
    [
        (Verdict.EXCELLENT, True),
        (Verdict.PASSED, True),
        (Verdict.FAILED, False),
        (Verdict.AGAIN, False),
    ],
)
def test_quiz_read_step_is_passed_only_by_a_passing_verdict(verdict: Verdict, passed: bool) -> None:
    """Ступень ③ закрепления: «ещё раз» — не ответ на вопрос (ADR-0066 п. 8)."""
    assert read_passed(verdict) is passed


# ---------- экран результата ----------
def _result(c: Curriculum, renderer: FeedbackRenderer, verdict: Verdict) -> RecitationResult:
    item = c.item("L010-04")
    a = assess(item.text, item.text)
    attempt = Attempt(
        UUID(int=1), LEARNER, item.id, "v", "stub", a, verdict, None, None, 1, FixedClock().now()
    )
    return RecitationResult(item, attempt, renderer.explain(a.errors, a.reference, None), "", None)


@pytest.mark.parametrize("verdict", list(Verdict))
def test_every_verdict_has_its_own_learner_text(
    curriculum: Curriculum, renderer: FeedbackRenderer, verdict: Verdict
) -> None:
    line = screens._VERDICT[verdict]
    assert isinstance(line, str) and line.strip()
    assert line in vars(texts).values()
    shown = screens.result(curriculum, _result(curriculum, renderer, verdict), has_audio=True)
    assert line in shown.caption + "\n" + shown.details


def test_again_text_is_not_the_text_of_another_verdict() -> None:
    others = {screens._VERDICT[v] for v in Verdict if v is not Verdict.AGAIN}
    assert screens._VERDICT[Verdict.AGAIN] not in others


@pytest.mark.parametrize("hint", sorted({LAST_VOWEL, OTHER_SYLLABLE, *CardPolicy().soft_kinds}))
def test_every_card_hint_has_a_learner_text(hint: str) -> None:
    """«Протяни последнюю гласную», мягкие шадда и мадд, «прочитан другой слог» (FR-70 п. 3, 5)."""
    line = texts.CARD_HINTS[hint]
    assert isinstance(line, str) and line.strip()


# ---------- освоение по вердикту ----------
def _attempt(c: Curriculum, n: int, item_id: str, verdict: Verdict, score: int) -> Attempt:
    text = c.item(item_id).text
    return Attempt(
        UUID(int=100 + n), LEARNER, item_id, "v", "m", Assessment(text, text, score, ()),
        verdict, None, 900, 10, FixedClock().now(),
    )  # fmt: skip


async def _progress(c: Curriculum, verdict: Verdict, score: int) -> tuple[int, LessonStatus]:
    attempts = InMemoryAttempts()
    lesson = next(les for les in c.lessons if les.number == 10)
    for n, item in enumerate(lesson.practice_items):
        attempts.items.append((_attempt(c, n, item.id, verdict, score), ()))
    from muallim.domain.learner import Learner  # noqa: PLC0415

    learner = Learner(LEARNER, 77, "L-00000007", "ru", FixedClock().now())
    progress = await GetProgress(c, attempts, GradingPolicy(), FixedClock()).execute(learner)
    lp = progress.of(lesson.id)
    return lp.mastered, lp.status


@pytest.mark.parametrize("verdict", [Verdict.FAILED, Verdict.AGAIN])
async def test_not_passed_with_a_high_score_is_not_mastered(
    curriculum: Curriculum, verdict: Verdict
) -> None:
    """«Ошибка» или «ещё раз» с баллом 85 (≥ порога 80) — карточка не освоена, урок не пройден."""
    mastered, status = await _progress(curriculum, verdict, 85)
    assert mastered == 0
    assert status is not LessonStatus.DONE


@pytest.mark.parametrize("verdict", [Verdict.EXCELLENT, Verdict.PASSED])
async def test_old_passing_attempts_are_mastered_as_before(
    curriculum: Curriculum, verdict: Verdict
) -> None:
    mastered, status = await _progress(curriculum, verdict, 85)
    assert mastered > 0
    assert status is LessonStatus.DONE


async def test_sura_is_not_studied_by_failed_cards_with_a_high_score(
    curriculum: Curriculum,
) -> None:
    """Сура «изучена по тексту» — по вердиктам её карточек, не по баллу (sura.py)."""
    from muallim.domain.sura import SuraMode  # noqa: PLC0415
    from tests.unit.test_sura_reading import DUHA, World  # noqa: PLC0415

    w = World(curriculum)
    sura = w.uc.sura(DUHA)
    for n, item in enumerate(i for les in sura.lessons for i in les.practice_items):
        w.attempts.items.append(
            (
                replace(
                    _attempt(curriculum, n, item.id, Verdict.FAILED, 85), learner_id=w.learner.id
                ),
                (),
            )
        )
    result = await w.uc.execute(w.learner, b"ogg", DUHA, SuraMode.MEMORY)
    assert not result.reading.studied_by_text


# ---------- «🔁 Повторение»: пройденные уроки — по вердикту (review.py) ----------
async def _frequent_letter_lessons(c: Curriculum, verdict: Verdict) -> set[str]:
    """Каждая строка урока 10 прочитана один раз с баллом 85 и ошибкой в букве ب; какие уроки
    дали строки «частая буква» (они берутся только из пройденных уроков)."""
    from muallim.application.use_cases.review import GetReview  # noqa: PLC0415
    from muallim.domain import review  # noqa: PLC0415
    from muallim.domain.assessment import ErrorKind, PronunciationError  # noqa: PLC0415
    from muallim.domain.learner import Learner  # noqa: PLC0415

    lesson = next(les for les in c.lessons if les.number == 10)
    attempts = InMemoryAttempts()
    error = PronunciationError(ErrorKind.LETTER_SUBSTITUTION, 0, None, "ب", "ت")
    for n, item in enumerate(lesson.practice_items):
        a = _attempt(c, n, item.id, verdict, 85)
        attempts.items.append(
            (replace(a, assessment=replace(a.assessment, errors=(error,))), ("msg",))
        )
    learner = Learner(LEARNER, 77, "L-00000007", "ru", FixedClock().now())
    entries = await GetReview(c, attempts, GradingPolicy(), FixedClock()).execute(learner)
    return {
        c.locate(e.item_id)[0].id
        for e in entries
        if e.reason is review.ReviewReason.FREQUENT_LETTER
    }


async def test_review_does_not_treat_a_failed_lesson_as_passed(curriculum: Curriculum) -> None:
    """«Ошибка» с баллом 85 — урок не пройден: его строки не идут в «частые буквы»."""
    assert "L010" not in await _frequent_letter_lessons(curriculum, Verdict.FAILED)


async def test_review_takes_lessons_passed_by_verdict(curriculum: Curriculum) -> None:
    assert "L010" in await _frequent_letter_lessons(curriculum, Verdict.PASSED)


# ---------- экран «ещё раз»: без разбора, балла и «услышано» (блокер ревью) ----------
def _again(c: Curriculum) -> RecitationResult:
    """«Ещё раз», как его отдаёт сценарий: балл 0, ошибок нет, услышанного нет; прошлая попытка
    была 100 — «было → стало» не к месту."""
    item = c.item("L010-04")
    a = Assessment(item.text, "", 0, ())
    attempt = Attempt(
        UUID(int=1), LEARNER, item.id, "v", "maroof", a, Verdict.AGAIN, None, 900, 10,
        FixedClock().now(),
    )  # fmt: skip
    return RecitationResult(item, attempt, (), "", None, previous_score=100)


@pytest.mark.parametrize("staff", [False, True])
def test_again_screen_has_no_breakdown_image_score_or_heard_line(
    curriculum: Curriculum, monkeypatch: pytest.MonkeyPatch, staff: bool
) -> None:
    """Экран «ещё раз» — только просьба прочитать снова: без картинки разбора, без «другая
    строка» (балл 0 — не чужая строка), без «было → стало» и без «Услышано» даже учителю."""
    from muallim.presentation.telegram import render  # noqa: PLC0415

    marks: list[str] = []

    def result_marks(*args: object, **kwargs: object) -> bytes:
        marks.append("called")
        return b"marks-png"

    monkeypatch.setattr(render, "available", lambda: True)
    monkeypatch.setattr(render, "result_marks", result_marks)
    shown = screens.result(curriculum, _again(curriculum), has_audio=True, staff=staff)
    text = shown.caption + "\n" + shown.details
    assert texts.VERDICT_AGAIN in text
    assert marks == [] and shown.image != b"marks-png"
    assert texts.RESULT_OTHER_LINE not in text
    assert texts.RESULT_PROGRESS.split("{trend}")[1].split("{")[0].strip() not in text  # «Было»
    assert texts.HEARD_LINE.split("«")[0] not in text  # «Услышано:»
