"""Экраны «🧠 Закрепления» (FR-53, ADR-0066): шапка «k из 10 · ✅ n», три ступени, разбор
неверного ответа, итог раунда, «N ждут» на главной, «⭐ уверенно» в прогрессе.

Тексты — черновики автора в ``texts.py``; тест проверяет, что экран их использует, а не их слова.
"""

from html import escape
from typing import Any
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup

from muallim.application.use_cases.quiz import QuizOverview, QuizRest, QuizResult, QuizView
from muallim.domain import quiz
from muallim.domain.curriculum import Curriculum
from muallim.domain.quiz import PickReason, RoundSummary, build_question
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import screens, texts
from tests.unit.test_screens import _progress

T, R, Z, M = "L007-05", "L004-05", "L005-05", "L006-05"
STARTED = (R, Z, M, T)
ANSWER = UUID(int=77)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def _view(c: Curriculum, step: int, *, position: int = 3, correct: int = 2) -> QuizView:
    q = build_question(c, quiz.Pick(T, step, 1, PickReason.NEW), STARTED)
    return QuizView(ANSWER, q, round_no=1, position=position, correct_so_far=correct)


def _header(position: int = 3, correct: int = 2) -> str:
    return texts.QUIZ_HEADER.format(position=position, total=quiz.QUIZ_ROUND, correct=correct)


def test_recognize_screen_has_header_four_answers_and_home(curriculum: Curriculum) -> None:
    v = _view(curriculum, 1)
    s = screens.quiz(v)
    assert _header() in s.caption
    answers = [d for _, d in _buttons(s.keyboard) if d.startswith("qa:")]
    assert answers == [cb.QuizAnswer(a=ANSWER.hex, p=k).pack() for k in range(4)]
    assert cb.Home().pack() in [d for _, d in _buttons(s.keyboard)]


def test_hear_screen_plays_syllable_and_does_not_show_it(curriculum: Curriculum) -> None:
    v = _view(curriculum, 2)
    s = screens.quiz(v)
    assert texts.QUIZ_HEAR_ASK in s.caption
    assert cb.Listen(item_id=v.question.item_id).pack() in [d for _, d in _buttons(s.keyboard)]
    assert v.question.prompt not in s.caption  # ответ не подсказываем
    assert s.image is None
    labels = [t for t, d in _buttons(s.keyboard) if d.startswith("qa:")]
    assert labels == list(v.question.options)


def test_read_screen_asks_for_voice_without_answer_buttons(curriculum: Curriculum) -> None:
    v = _view(curriculum, 3)
    s = screens.quiz(v)
    assert texts.QUIZ_READ_ASK in s.caption and _header() in s.caption
    assert s.image is not None or v.question.prompt in s.caption  # строку видно
    assert not [d for _, d in _buttons(s.keyboard) if d.startswith("qa:")]


def test_wrong_answer_screen_colours_and_moves_on(curriculum: Curriculum) -> None:
    v = _view(curriculum, 1)
    picked = (v.question.answer + 1) % 4
    s = screens.quiz_answer(QuizResult(v, picked, correct=False, finished=False))
    styles = {b.text: b.style for row in s.keyboard.inline_keyboard for b in row}
    assert styles[v.question.options[v.question.answer]] == "success"
    assert styles[v.question.options[picked]] == "danger"
    data = [d for _, d in _buttons(s.keyboard)]
    assert cb.Quiz().pack() in data
    assert cb.Listen(item_id=v.question.item_id).pack() in data  # послушать верный слог
    assert v.question.options[v.question.answer] in s.caption
    wrong = texts.QUIZ_WRONG.format(
        prompt=escape(v.question.prompt),
        answer=escape(v.question.options[v.question.answer]),
        picked=escape(v.question.options[picked]),
    )
    assert wrong in s.caption  # подпись главнее цвета: старые клиенты цвет не покажут
    others = [o for k, o in enumerate(v.question.options) if k not in (v.question.answer, picked)]
    assert all(styles[o] is None for o in others)
    answered = [d for t, d in _buttons(s.keyboard) if t in v.question.options]
    assert answered and all(d == cb.Noop().pack() for d in answered)  # повторно не ответить
    assert styles[texts.QUIZ_NEXT] == "primary"


def test_summary_shows_score_letters_to_repeat_and_next_round(curriculum: Curriculum) -> None:
    s = screens.quiz_summary(curriculum, RoundSummary(8, 10, (R, Z), confident=2, letters=4))
    assert texts.QUIZ_SUMMARY.format(correct=8, total=10) in s.caption
    assert "ر" in s.caption and "ز" in s.caption
    assert texts.QUIZ_CONFIDENT.format(n=2, total=4) in s.caption
    data = [d for _, d in _buttons(s.keyboard)]
    assert cb.Listen(item_id=R).pack() in data and cb.Listen(item_id=Z).pack() in data
    assert (texts.QUIZ_AGAIN, cb.Quiz().pack()) in _buttons(s.keyboard)
    assert cb.Home().pack() in [d for _, d in _buttons(s.keyboard)]


def test_summary_without_mistakes_has_no_repeat_line(curriculum: Curriculum) -> None:
    s = screens.quiz_summary(curriculum, RoundSummary(10, 10, (), confident=0, letters=4))
    assert texts.QUIZ_SUMMARY_REPEAT.split("{")[0] not in s.caption


def test_home_quiz_button_says_how_many_letters_wait(curriculum: Curriculum) -> None:
    waiting = screens.home(curriculum, _progress(curriculum), quiz_waiting=2)
    calm = screens.home(curriculum, _progress(curriculum))
    assert (texts.QUIZ_BUTTON_WAITING.format(n=2), cb.Quiz().pack()) in _buttons(waiting.keyboard)
    assert (texts.QUIZ_BUTTON, cb.Quiz().pack()) in _buttons(calm.keyboard)


def test_progress_shows_confident_letters(curriculum: Curriculum) -> None:
    s = screens.progress(curriculum, _progress(curriculum), quiz=QuizOverview(3, 7, 0))
    assert texts.QUIZ_CONFIDENT.format(n=3, total=7) in s.caption


def test_answer_button_fits_telegram_limit() -> None:
    assert len(cb.QuizAnswer(a="f" * 32, p=3).pack().encode()) <= 64


def test_hear_screen_offers_cant_listen_now(curriculum: Curriculum) -> None:
    s = screens.quiz(_view(curriculum, 2))
    assert (texts.QUIZ_CANT_LISTEN, cb.QuizSkip(a=ANSWER.hex).pack()) in _buttons(s.keyboard)


def test_read_screen_offers_cant_speak_now(curriculum: Curriculum) -> None:
    s = screens.quiz(_view(curriculum, 3))
    assert (texts.QUIZ_CANT_SPEAK, cb.QuizSkip(a=ANSWER.hex).pack()) in _buttons(s.keyboard)


def test_recognize_screen_has_no_skip(curriculum: Curriculum) -> None:
    s = screens.quiz(_view(curriculum, 1))
    assert not [d for _, d in _buttons(s.keyboard) if d.startswith(cb.QuizSkip.__prefix__ + ":")]


def test_rest_screen_says_come_back_and_offers_lessons(curriculum: Curriculum) -> None:
    s = screens.quiz_rest(QuizRest(confident=2, letters=2))
    assert texts.QUIZ_REST in s.caption
    assert texts.QUIZ_CONFIDENT.format(n=2, total=2) in s.caption
    data = [d for _, d in _buttons(s.keyboard)]
    assert cb.Lessons(part=-1).pack() in data and cb.Home().pack() in data
