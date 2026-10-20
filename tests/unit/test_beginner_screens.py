"""Экраны для новичка: ответы не противоречат карточке, разбор без лишнего (FR-49, FR-50).

Автор одобрил 2026-10-20 (UX-обход). Проверяются экраны (подпись и кнопки) без Telegram.
"""

import re
from collections.abc import Set as AbstractSet
from dataclasses import replace
from html import escape
from typing import Any
from uuid import UUID

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.feedback import Explanation
from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson
from muallim.domain.policy import GradingPolicy, Verdict
from muallim.domain.quiz import QuizError, make_question
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts, views
from tests.fakes import FixedClock

_COUNTER = re.compile(r"^\d+/\d+$")
_FRACTION = re.compile(r"(\d+)/(\d+)$")
ATTEMPT_ID = UUID("a571a239-0c4e-4d1b-9f00-3b5e2a7c9d11")  # код попытки — A571A239


@pytest.fixture(autouse=True)
def _captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подписи и кнопки — без рисования картинок (и без libraqm)."""
    monkeypatch.setattr(render, "available", lambda: False)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def _letters(c: Curriculum) -> list[Lesson]:
    return [les for les in c.lessons if les.section == "letter"]


def _progress(
    c: Curriculum,
    done: AbstractSet[str] = frozenset(),
    attempts: int = 5,
    current: str | None = None,
) -> Progress:
    lessons = tuple(
        LessonProgress(les, len(les.practice_items) if les.id in done else 0, ())
        for les in c.lessons
    )
    item = c.item(current) if current else c.first_item()
    return Progress(lessons, attempts_total=attempts, continue_item=item)


def _result(
    c: Curriculum, item_id: str, heard: str, previous: int | None = None
) -> RecitationResult:
    item = c.item(item_id)
    a = assess(item.text, heard)
    attempt = Attempt(
        ATTEMPT_ID, UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    return RecitationResult(
        item, attempt, (Explanation("Ошибка"),) if a.errors else (), "а-‘уу-з̱у",
        c.next_item(item.id), previous_score=previous,
    )  # fmt: skip


# ---------- FR-49: первая кнопка, шаги, замок, счётчики ----------
def test_start_button_does_not_promise_the_alphabet() -> None:
    """Новичок начинает с истиазы и басмалы, а не с алфавита — кнопка называет урок."""
    assert "алфавит" not in texts.START_BUTTON.casefold()
    assert "урок" in texts.START_BUTTON.casefold()


def test_voice_on_rule_text_points_to_next_button() -> None:
    """После правила не всегда чтение (бывает ещё правило) — текст этого не обещает."""
    assert "правил" in texts.VOICE_ON_RULE.casefold()
    assert "▶️" in texts.VOICE_ON_RULE
    assert "чтени" not in texts.VOICE_ON_RULE.casefold()


# ---------- тексты не обещают лишнего (FR-49, FR-50, второй круг) ----------
def test_rule_card_does_not_promise_reading() -> None:
    assert "к чтению" not in texts.CARD_RULE


def test_wrong_quiz_answer_moves_on_to_next_question() -> None:
    """Ответ уже показан в цвете — «попробуй ещё» не к чему; дальше — «Ещё вопрос»."""
    assert "попробуй ещё" not in texts.QUIZ_WRONG.casefold()
    assert "ещё вопрос" in texts.QUIZ_WRONG.casefold()


def test_send_voice_hint_does_not_point_down() -> None:
    """Текст вместо голосового: главная больше не присылается — «👇» указывал бы в пустоту."""
    assert "👇" not in texts.SEND_VOICE


def test_card_head_does_not_use_no_voice_icon() -> None:
    """📖 в списке уроков значит «без голоса» — в заголовке карточки его быть не должно."""
    assert not texts.CARD_HEAD.startswith("📖")


def test_progress_repeat_lists_step_numbers() -> None:
    assert "шаги" in texts.PROGRESS_REPEAT
    assert texts.PROGRESS_ITEM == "{n}"


def test_syllable_and_word_counters_are_distinguishable() -> None:
    """В подписи считаются слоги, на картинке — слова: «11 из 12» и «5 из 6» не путаются."""
    assert "слог" in texts.RESULT_RIGHT
    assert "слов" in texts.RESULT_WORDS


def test_fresh_learner_start_button_opens_lesson_one(curriculum: Curriculum) -> None:
    s = screens.home(curriculum, _progress(curriculum, attempts=0))
    label, data = _buttons(s.keyboard)[0]
    assert label == texts.START_BUTTON
    assert data == cb.GoItem(item_id=curriculum.first_item().id).pack()
    assert curriculum.locate(curriculum.first_item().id)[0].number == 1


def test_card_head_counts_steps_not_lines(curriculum: Curriculum) -> None:
    """Карточка-правило — не «строка»: урок состоит из шагов."""
    assert "шаг" in texts.CARD_HEAD and "строка" not in texts.CARD_HEAD
    lesson = curriculum.lessons[0]
    for n, item in enumerate(lesson.items[:2], start=1):
        s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
        assert f"шаг {n} из {len(lesson.items)}" in s.caption, item.id


def _quiz_opens_at(c: Curriculum) -> Lesson:
    """Первый урок буквы, с которого make_question даёт вопрос (до него — QuizError)."""
    letters = _letters(c)
    for k, lesson in enumerate(letters):
        try:
            make_question(c, letters[: k + 1], seed=0)
        except QuizError:
            continue
        with pytest.raises(QuizError):
            make_question(c, letters[:k], seed=0)
        return lesson
    raise AssertionError("закрепление не открывается ни на одном уроке")


def test_quiz_lock_names_the_lesson_that_opens_it(curriculum: Curriculum) -> None:
    """Замок называет урок, на котором закрепление откроется, — по настоящему правилу вопроса."""
    opens = _quiz_opens_at(curriculum)
    assert "{lesson}" in texts.QUIZ_LOCKED
    s = screens.quiz_unavailable(curriculum, _progress(curriculum))
    assert escape(opens.title) in s.caption
    assert "урок 3" not in s.caption


@pytest.mark.parametrize("current", ["L004-02", "L010-03"])
def test_quiz_lock_does_not_send_learner_back(curriculum: Curriculum, current: str) -> None:
    """Ученик уже на уроке открытия или дальше, а букв начато мало — урок назад не называем."""
    opens = _quiz_opens_at(curriculum)
    assert curriculum.locate(current)[0].number >= opens.number
    s = screens.quiz_unavailable(curriculum, _progress(curriculum, current=current))
    assert s.caption == texts.QUIZ_LOCKED_MORE
    assert escape(opens.title) not in s.caption


def test_part_counters_count_only_lessons_with_reading(curriculum: Curriculum) -> None:
    """Главная, список частей и прогресс считают одни и те же уроки — с чтением вслух."""
    p = _progress(curriculum, done={curriculum.lessons[0].id})
    s = screens.lessons(curriculum, p, part=None)
    labels = [t for t, d in _buttons(s.keyboard) if d.startswith("lessons:")]
    fractions = [_FRACTION.search(t) for t in labels]
    assert all(fractions), labels
    totals = [int(m.group(2)) for m in fractions if m]
    with_reading = sum(1 for les in curriculum.lessons if les.practice_items)
    assert sum(totals) == with_reading == p.practice_lessons
    assert totals[0] == 1  # «Знакомство»: истиаза и басмала; алфавит только смотрят
    assert labels[0].startswith("✅") and labels[0].endswith("1/1")
    assert f"из {with_reading}" in screens.home(curriculum, p).caption
    assert f"из {with_reading}" in screens.progress(curriculum, p).caption


# ---------- FR-50: кнопки карточки ----------
def test_last_step_card_offers_next_lesson(curriculum: Curriculum) -> None:
    """Последний шаг урока: вперёд — «➡️ Следующий урок: …», в том числе у «Алфавита» (шаг 5)."""
    for lesson in (_letters(curriculum)[1], curriculum.lesson("L002")):
        nxt = curriculum.next_lesson(lesson.id)
        assert nxt is not None
        s = screens.card(curriculum, lesson.items[-1], has_audio=False, is_teacher=False)
        jump = (
            texts.NEXT_LESSON_BUTTON.format(title=nxt.title),
            cb.GoItem(item_id=nxt.items[0].id).pack(),
        )
        assert jump in _buttons(s.keyboard), lesson.id
        assert not any(t == texts.NEXT_BUTTON for t, _ in _buttons(s.keyboard)), lesson.id


def test_last_card_of_program_has_no_forward_button(curriculum: Curriculum) -> None:
    last = curriculum.lessons[-1].items[-1]
    s = screens.card(curriculum, last, has_audio=False, is_teacher=False)
    forward = (texts.NEXT_BUTTON, texts.NEXT_LESSON_BUTTON.split("{")[0])
    assert not [t for t, _ in _buttons(s.keyboard) if t.startswith(forward)]


def test_last_step_result_offers_next_lesson(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    nxt = curriculum.next_lesson(lesson.id)
    assert nxt is not None
    last = lesson.items[-1]
    s = screens.result(curriculum, _result(curriculum, last.id, last.text), has_audio=False)
    jump = (
        texts.NEXT_LESSON_BUTTON.format(title=nxt.title),
        cb.GoItem(item_id=nxt.items[0].id).pack(),
    )
    assert jump in _buttons(s.keyboard)
    assert not any(t == texts.NEXT_BUTTON for t, _ in _buttons(s.keyboard))


def test_last_result_of_program_says_it_is_the_last(curriculum: Curriculum) -> None:
    last = curriculum.lessons[-1].items[-1]
    s = screens.result(curriculum, _result(curriculum, last.id, last.text), has_audio=False)
    assert texts.LAST_ITEM in s.caption
    forward = (texts.NEXT_BUTTON, texts.NEXT_LESSON_BUTTON.split("{")[0])
    assert not [t for t, _ in _buttons(s.keyboard) if t.startswith(forward)]


def test_first_step_has_one_back_button_to_previous_lesson(curriculum: Curriculum) -> None:
    """На первом шаге назад ведёт одна кнопка — «⬅️ Предыдущий урок», без «◀️» на шаг."""
    lesson = _letters(curriculum)[1]
    prev = curriculum.previous_lesson(lesson.id)
    assert prev is not None
    s = screens.card(curriculum, lesson.items[0], has_audio=False, is_teacher=False)
    buttons = _buttons(s.keyboard)
    to_prev_step = cb.GoItem(item_id=prev.items[-1].id).pack()
    assert not [t for t, d in buttons if d == to_prev_step]
    assert not [t for t, _ in buttons if t.startswith("◀️")]
    assert [t for t, _ in buttons if t.startswith("⬅️")] == [
        texts.PREVIOUS_LESSON_BUTTON.format(title=prev.title)
    ]


def test_back_button_is_labelled_the_same_on_card_and_result(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    item = next(i for i in lesson.items[1:] if i.is_practice)
    prev = curriculum.previous_item(item.id)
    assert prev is not None
    back = (texts.BACK_BUTTON, cb.GoItem(item_id=prev.id).pack())
    card = screens.card(curriculum, item, has_audio=False, is_teacher=False)
    result = screens.result(curriculum, _result(curriculum, item.id, item.text), has_audio=False)
    assert back in _buttons(card.keyboard)
    assert back in _buttons(result.keyboard)


def test_card_forward_button_says_next(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    item = lesson.items[1]
    following = curriculum.next_item(item.id)
    assert following is not None
    s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
    buttons = _buttons(s.keyboard)
    assert (texts.NEXT_BUTTON, cb.GoItem(item_id=following.id).pack()) in buttons
    assert not any(t == "▶️" for t, _ in buttons)


def test_card_has_no_step_counter_button(curriculum: Curriculum) -> None:
    """Счёт шагов уже в заголовке («шаг N из M»), кнопка «1/3» ничего не делает."""
    for item in (curriculum.first_item(), _letters(curriculum)[1].items[2]):
        s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
        assert not [t for t, _ in _buttons(s.keyboard) if _COUNTER.match(t)], item.id


def test_card_has_no_dead_buttons(curriculum: Curriculum) -> None:
    """Ни одной кнопки-пустышки (Noop): ни счётчика, ни «·» на краях урока и книги."""
    lesson = _letters(curriculum)[1]
    for item in (curriculum.first_item(), *lesson.items, curriculum.lessons[-1].items[-1]):
        s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
        dead = [t for t, d in _buttons(s.keyboard) if d == cb.Noop().pack()]
        assert not dead, (item.id, dead)


def _to_lesson(s: screens.Screen, lesson: Lesson) -> list[str]:
    """Кнопки, которые ведут на любую карточку урока ``lesson``."""
    targets = {cb.GoItem(item_id=i.id).pack() for i in lesson.items}
    return [t for t, d in _buttons(s.keyboard) if d in targets]


def test_previous_lesson_button_only_on_first_step(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    prev = curriculum.previous_lesson(lesson.id)
    assert prev is not None
    first = screens.card(curriculum, lesson.items[0], has_audio=False, is_teacher=False)
    jump = (
        texts.PREVIOUS_LESSON_BUTTON.format(title=prev.title),
        cb.GoItem(item_id=prev.items[0].id).pack(),
    )
    assert jump in _buttons(first.keyboard)
    for item in lesson.items[1:]:
        s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
        assert _to_lesson(s, prev) == [], item.id


# ---------- FR-50: разбор попытки ----------
def _everything(s: screens.Screen) -> str:
    return s.caption + "\n" + s.details


RESEARCH_MARKS = ("Для исследования", "Услышано", "Попытка №", "Эталон:")


def _research_shown(s: screens.Screen) -> list[str]:
    shown = _everything(s)
    marks = [*RESEARCH_MARKS, views.attempt_code(ATTEMPT_ID)]
    return [m for m in marks if m in shown]


def _failed(c: Curriculum) -> RecitationResult:
    item = next(i for i in _letters(c)[1].items if i.kind is ItemKind.LETTER)
    r = _result(c, item.id, "سَ سِ سُ")
    assert r.verdict is Verdict.FAILED
    return r


def test_correct_result_hides_research_block_and_heard_line(curriculum: Curriculum) -> None:
    item = curriculum.item("L001-02")
    s = screens.result(curriculum, _result(curriculum, item.id, item.text), has_audio=True)
    assert _research_shown(s) == []


def test_result_with_errors_hides_research_block(curriculum: Curriculum) -> None:
    s = screens.result(curriculum, _failed(curriculum), has_audio=True)
    assert s.details  # разбор есть
    assert _research_shown(s) == []


def test_failed_result_lets_learner_go_on(curriculum: Curriculum) -> None:
    """Не получается — можно идти дальше: та же «▶️ Дальше» на следующий шаг, без «вернусь позже»."""
    r = _failed(curriculum)
    assert r.next_item is not None
    assert curriculum.locate(r.next_item.id)[0] == curriculum.locate(r.item.id)[0]
    s = screens.result(curriculum, r, has_audio=True)
    assert (texts.NEXT_BUTTON, cb.GoItem(item_id=r.next_item.id).pack()) in _buttons(s.keyboard)
    assert "вернусь позже" not in " ".join(t for t, _ in _buttons(s.keyboard))


@pytest.mark.parametrize("failed", [False, True], ids=["correct", "with_errors"])
def test_staff_sees_research_block(curriculum: Curriculum, failed: bool) -> None:
    """Учитель и разметчик видят «Для исследования» с номером попытки (FR-50)."""
    item = curriculum.item("L001-02")
    r = _failed(curriculum) if failed else _result(curriculum, item.id, item.text)
    s = screens.result(curriculum, r, has_audio=True, staff=True)
    shown = _everything(s)
    assert "Для исследования" in shown
    assert "Попытка №" in shown and views.attempt_code(ATTEMPT_ID) in shown


def test_result_still_offers_dispute_with_attempt(curriculum: Curriculum) -> None:
    """Номер попытки уходит в «🚩 Бот ошибся» — кнопка остаётся и ведёт к этой попытке."""
    item = curriculum.item("L001-02")
    r = _result(curriculum, item.id, item.text)
    s = screens.result(curriculum, r, has_audio=True)
    dispute = cb.Dispute(attempt=r.attempt.id.hex).pack()
    assert (texts.DISPUTE_BUTTON, dispute) in _buttons(s.keyboard)


def test_unchanged_score_has_no_before_after_line(curriculum: Curriculum) -> None:
    item = curriculum.item("L001-02")
    r = _result(curriculum, item.id, item.text)
    same = replace(r, previous_score=r.attempt.assessment.score)
    assert "Было" not in _everything(screens.result(curriculum, same, has_audio=True))


def test_changed_score_still_shows_before_after_line(curriculum: Curriculum) -> None:
    item = curriculum.item("L001-02")
    r = _result(curriculum, item.id, item.text, previous=40)
    score = r.attempt.assessment.score
    assert f"Было 40% → стало {score}%" in screens.result(curriculum, r, has_audio=True).caption
