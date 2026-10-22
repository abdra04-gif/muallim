"""«🧠 Закрепление» по методике (FR-53, ADR-0066, M-19): чистые функции ``muallim.domain.quiz``.

Правила (автор 2026-10-22, по SRC-138…SRC-143):
- лестница по букве: ① узнаю (слог → кириллица) → ② слышу (🔊 → арабский слог) → ③ читаю голосом;
- ступень пройдена после 3 верных ответов на ней; верный ответ считается, только если с прошлого
  вопроса по этой букве прошло ≥ 2 других вопросов или наступил другой день;
- ошибка ступень не понижает и счёт не обнуляет;
- после первого подъёма буква — в повторении 1·3·7 дней (верно в срок или позже — дальше, после
  третьего — выходит; неверно — снова +1 день);
- раунд — 10 вопросов: возврат ошибки этого раунда → к сроку → ошибки (≤ 4 места) → новое (≤ 3)
  → старое; одна буква не идёт подряд;
- отвлекающие варианты: та же буква с другими огласовками, затем похожие начатые буквы, затем
  ближайшие по книге начатые.

Буква обозначается id её головной карточки (``ItemKind.LETTER``), например ``L004-05`` для ر.
"""

from collections.abc import Sequence
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from muallim.domain import quiz
from muallim.domain.curriculum import Curriculum, ItemKind
from muallim.domain.quiz import (
    NothingToday,
    PickReason,
    QuizError,
    QuizOutcome,
    Step,
    build_question,
    letter_states,
    letters_waiting,
    next_pick,
    round_summary,
)

settings.register_profile("project", max_examples=300, deadline=None)
settings.load_profile("project")

D0 = date(2026, 10, 22)
R, Z, M, T, N, Y, B, K, L, Q = (
    "L004-05", "L005-05", "L006-05", "L007-05", "L008-05",
    "L009-05", "L010-05", "L011-05", "L012-05", "L016-05",
)  # fmt: skip
FIRST_FOUR = (R, Z, M, T)  # ر ز م ت — начатые уроки по порядку книги


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def ok(letter: str, step: int = 1, d: int = 0, vowel: int = 0) -> QuizOutcome:
    return QuizOutcome(letter, step, vowel, True, day(d))


def bad(letter: str, step: int = 1, d: int = 0, vowel: int = 0) -> QuizOutcome:
    return QuizOutcome(letter, step, vowel, False, day(d))


F1, F2 = "L020-05", "L021-05"  # ص ط — «прокладки»: в тестах раунда не начаты


def spaced(letter: str, n: int, step: int = 1, d: int = 0) -> list[QuizOutcome]:
    """``n`` верных ответов по букве, между ними — по два вопроса о буквах-прокладках."""
    out: list[QuizOutcome] = []
    for _ in range(n):
        out += [ok(letter, step, d), ok(F1, 1, d), ok(F2, 1, d)]
    return out


# ---------- константы методики (M-19) ----------
def test_round_is_ten_questions() -> None:
    assert quiz.QUIZ_ROUND == 10


def test_step_needs_three_spaced_correct_answers() -> None:
    assert quiz.QUIZ_CRITERION == 3
    assert quiz.QUIZ_MIN_GAP == 2


def test_slots_and_intervals_are_as_agreed() -> None:
    assert quiz.QUIZ_ERROR_SLOTS == 4
    assert quiz.QUIZ_NEW_SLOTS == 3
    assert quiz.QUIZ_INTERVALS == (1, 3, 7)
    assert quiz.QUIZ_RULE == "v2"


def test_steps_are_recognize_hear_read() -> None:
    assert [s.value for s in Step] == [1, 2, 3]


def test_confusable_groups_are_the_agreed_lists() -> None:
    """Пары, которые путают (ADR-0066 п. 6, З3): на вид и на слух для русскоязычных."""
    assert quiz.CONFUSABLE_SHAPE == (
        "بتثني", "جحخ", "دذ", "رز", "سش", "صض", "طظ", "عغ", "فق",
    )  # fmt: skip
    assert quiz.CONFUSABLE_SOUND == ("سصث", "تط", "دض", "ذزظ", "هحعء", "كق")


# ---------- ступень буквы ----------
def test_new_letter_starts_at_step_one() -> None:
    s = letter_states([ok(R)])[R]
    assert s.step == 1 and not s.confident


def test_three_spaced_correct_answers_raise_the_step() -> None:
    assert letter_states(spaced(T, 3))[T].step == 2


def test_two_spaced_correct_answers_are_not_enough() -> None:
    assert letter_states(spaced(T, 2))[T].step == 1


def test_correct_answers_in_a_row_count_once() -> None:
    """Подряд на ту же букву — ответ ещё в рабочей памяти: засчитан только первый (SRC-140)."""
    s = letter_states([ok(T), ok(T), ok(T)])[T]
    assert s.step == 1 and s.counted == 1


def test_gap_of_two_other_questions_counts_and_gap_of_one_does_not() -> None:
    gap_one = letter_states([ok(T), ok(R), ok(T)])[T]
    gap_two = letter_states([ok(T), ok(R), ok(Z), ok(T)])[T]
    assert gap_one.counted == 1
    assert gap_two.counted == 2


def test_next_day_counts_without_gap() -> None:
    assert letter_states([ok(T, d=0), ok(T, d=1), ok(T, d=2)])[T].step == 2


def test_wrong_answer_neither_lowers_step_nor_resets_count() -> None:
    history = [*spaced(T, 3), *spaced(T, 2, step=2), bad(T, step=2)]
    s = letter_states(history)[T]
    assert s.step == 2 and s.counted == 2


def test_answer_at_another_step_does_not_count() -> None:
    s = letter_states([*spaced(T, 3), ok(R), ok(Z), ok(T, step=1)])[T]
    assert s.step == 2 and s.counted == 0


def test_passing_step_three_is_not_yet_confident() -> None:
    """⭐ — только когда буква вспомнилась в другой день (автор 2026-10-23, SRC-138)."""
    history = [*spaced(T, 3, 1), *spaced(T, 3, 2), *spaced(T, 3, 3)]
    s = letter_states(history)[T]
    assert s.step == 4 and not s.confident


def test_correct_answer_on_another_day_makes_letter_confident() -> None:
    history = [*spaced(T, 3, 1), *spaced(T, 3, 2), *spaced(T, 3, 3), ok(T, 3, d=1)]
    assert letter_states(history)[T].confident


def test_wrong_answer_next_day_does_not_make_letter_confident() -> None:
    history = [*spaced(T, 3, 1), *spaced(T, 3, 2), *spaced(T, 3, 3), bad(T, 3, d=1)]
    assert not letter_states(history)[T].confident


def test_same_day_answers_after_step_three_do_not_confirm() -> None:
    history = [*spaced(T, 3, 1), *spaced(T, 3, 2), *spaced(T, 3, 3), ok(R), ok(Z), ok(T, 3)]
    assert not letter_states(history)[T].confident


def test_letter_without_syllable_audio_skips_hearing() -> None:
    """Нет записей слогов буквы — ступени ② нет: после ① сразу ③ (ADR-0066 п. 2)."""
    assert letter_states(spaced(T, 3), skip_hear={T})[T].step == 3


# ---------- повторение 1·3·7 по буквам ----------
def test_letter_enters_relearning_next_day_after_step_up() -> None:
    s = letter_states(spaced(T, 3))[T]
    assert (s.stage, s.due) == (1, day(1))


def test_letter_not_stepped_up_is_not_scheduled() -> None:
    s = letter_states(spaced(T, 2))[T]
    assert s.due is None


def _confident(d: int = 0) -> list[QuizOutcome]:
    return [*spaced(T, 3, 1, d), *spaced(T, 3, 2, d), *spaced(T, 3, 3, d)]


def test_correct_on_due_day_moves_to_three_then_seven_days_then_out() -> None:
    """⭐ буква (ступеней выше нет): ответы в срок двигают 1 → 3 → 7, после третьего — выходит."""
    h = [*_confident(), ok(T, 3, d=1)]
    assert (letter_states(h)[T].stage, letter_states(h)[T].due) == (2, day(4))
    h.append(ok(T, 3, d=4))
    assert (letter_states(h)[T].stage, letter_states(h)[T].due) == (3, day(11))
    h.append(ok(T, 3, d=11))
    assert letter_states(h)[T].due is None and letter_states(h)[T].stage == 0


def test_every_step_up_restarts_relearning() -> None:
    """Новая ступень — новое умение: 1·3·7 заново, даже если буква ещё в повторении
    (ADR-0066, уточнения после ревью тестов)."""
    h = [*spaced(T, 3), ok(T, 2, d=1), ok(T, 2, d=4)]  # ② засчитано дважды, повторение — ступень 3
    assert letter_states(h)[T].stage == 3
    h.append(ok(T, 2, d=11))  # третий верный на ② — подъём на ③
    s = letter_states(h)[T]
    assert (s.step, s.stage, s.due) == (3, 1, day(12))


def test_wrong_before_due_in_relearning_starts_again() -> None:
    h = [*spaced(T, 3), ok(T, 2, d=1), bad(T, 2, d=2)]
    s = letter_states(h)[T]
    assert (s.stage, s.due) == (1, day(3))


def test_forgotten_letter_after_leaving_relearning_comes_back() -> None:
    h = [*_confident(), ok(T, 3, d=1), ok(T, 3, d=4), ok(T, 3, d=11), bad(T, 3, d=30)]
    s = letter_states(h)[T]
    assert (s.stage, s.due, s.step) == (1, day(31), 4)


def test_wrong_answer_between_counts_still_needs_a_gap() -> None:
    """Пауза считается от любого прошлого вопроса по букве — и неверного тоже."""
    s = letter_states([ok(T), ok(R), bad(T), ok(Z), ok(M), ok(T)])[T]
    assert s.counted == 2
    s = letter_states([ok(T), ok(R), ok(Z), bad(T), ok(T)])[T]
    assert s.counted == 1


def test_correct_before_due_does_not_move_the_schedule() -> None:
    h = [*spaced(T, 3), ok(R), ok(Z), ok(T, 2, d=0)]
    assert letter_states(h)[T].due == day(1)


def test_overdue_letter_is_not_punished() -> None:
    h = [*spaced(T, 3), ok(T, 2, d=9)]
    s = letter_states(h)[T]
    assert (s.stage, s.due) == (2, day(12))


def test_wrong_in_relearning_starts_again_next_day() -> None:
    h = [*spaced(T, 3), ok(T, 2, d=1), bad(T, 2, d=4)]
    s = letter_states(h)[T]
    assert (s.stage, s.due) == (1, day(5)) and s.step == 2


# ---------- следующий вопрос раунда ----------
def pick(
    curriculum: Curriculum,
    history: Sequence[QuizOutcome] = (),
    *,
    started: Sequence[str] = FIRST_FOUR,
    round_len: int = 0,
    today: int = 0,
    reading_errors: dict[str, int] | None = None,
    audio: set[str] | None = None,
) -> quiz.Pick:
    return next_pick(
        curriculum,
        started=started,
        history=history,
        round_len=round_len,
        today=day(today),
        reading_errors=reading_errors or {},
        has_audio=(lambda _: True) if audio is None else audio.__contains__,
    )


def test_needs_two_started_letters(curriculum: Curriculum) -> None:
    with pytest.raises(QuizError):
        pick(curriculum, started=(R,))


def test_fresh_learner_gets_newest_letter_first(curriculum: Curriculum) -> None:
    p = pick(curriculum)
    assert (p.letter_id, p.step, p.reason) == (T, 1, PickReason.NEW)


def test_same_letter_never_twice_in_a_row(curriculum: Curriculum) -> None:
    assert pick(curriculum, [ok(T)], round_len=1).letter_id != T


def test_letter_from_last_two_questions_is_avoided(curriculum: Curriculum) -> None:
    p = pick(curriculum, [ok(T), ok(M)], round_len=2)
    assert p.letter_id not in {T, M}


def test_two_letters_alternate(curriculum: Curriculum) -> None:
    assert pick(curriculum, [ok(R)], started=(R, Z), round_len=1).letter_id == Z


def test_wrong_answer_in_round_returns_after_two_other_questions(curriculum: Curriculum) -> None:
    h = [bad(Z, vowel=2), ok(R), ok(M)]
    p = pick(curriculum, h, round_len=3)
    assert (p.letter_id, p.step, p.vowel, p.reason) == (Z, 1, 2, PickReason.RETRY)


def test_wrong_answer_does_not_return_too_early(curriculum: Curriculum) -> None:
    p = pick(curriculum, [bad(Z), ok(R)], round_len=2)
    assert p.letter_id != Z


def test_wrong_answer_from_previous_round_is_a_mistake_not_retry(curriculum: Curriculum) -> None:
    p = pick(curriculum, [bad(Z), ok(R), ok(M)], round_len=0)
    assert (p.letter_id, p.reason) == (Z, PickReason.MISTAKE)


def test_fixed_mistake_is_no_longer_a_mistake(curriculum: Curriculum) -> None:
    h = [bad(Z), ok(R), ok(M), ok(Z), ok(R), ok(M)]
    assert pick(curriculum, h).reason is not PickReason.MISTAKE


def test_due_letter_comes_before_mistakes(curriculum: Curriculum) -> None:
    h = [*spaced(T, 3), bad(Z)]
    h += [ok(R), ok(M)]
    p = pick(curriculum, h, today=1)
    assert (p.letter_id, p.reason, p.step) == (T, PickReason.DUE, 2)


def test_reading_mistake_letter_is_asked(curriculum: Curriculum) -> None:
    """Ошибки чтения голосом (``review.error_letters``) ведут в закрепление."""
    p = pick(curriculum, reading_errors={"ز": 3})
    assert (p.letter_id, p.reason) == (Z, PickReason.MISTAKE)


def test_reading_mistake_in_letter_not_started_is_ignored(curriculum: Curriculum) -> None:
    p = pick(curriculum, reading_errors={"ب": 5})
    assert (p.letter_id, p.reason) == (T, PickReason.NEW)


def test_reading_mistake_stays_after_correct_quiz_answer(curriculum: Curriculum) -> None:
    """Ошибку чтения голосом снимает только чтение без неё, а не кнопка (ADR-0066, уточнения)."""
    h = [ok(Z), ok(R), ok(M)]
    p = pick(curriculum, h, reading_errors={"ز": 1})
    assert (p.letter_id, p.reason) == (Z, PickReason.MISTAKE)


def test_more_frequent_reading_mistake_first(curriculum: Curriculum) -> None:
    p = pick(curriculum, reading_errors={"ز": 1, "م": 4})
    assert (p.letter_id, p.reason) == (M, PickReason.MISTAKE)


def test_quiz_mistake_before_reading_mistake(curriculum: Curriculum) -> None:
    h = [bad(R), ok(T), ok(Z)]
    p = pick(curriculum, h, reading_errors={"م": 9})
    assert (p.letter_id, p.reason) == (R, PickReason.MISTAKE)


def test_hamza_reading_mistake_maps_to_hamza_letter(curriculum: Curriculum) -> None:
    hamza = "L003-10"
    p = pick(curriculum, started=(hamza, R, Z), reading_errors={"ء": 2})
    assert (p.letter_id, p.reason) == (hamza, PickReason.MISTAKE)


def test_mistakes_take_at_most_four_places_in_a_round(curriculum: Curriculum) -> None:
    round_ = [QuizOutcome(x, 1, 0, True, D0, PickReason.MISTAKE) for x in (R, Z, M, T)]
    p = pick(curriculum, round_, started=(*FIRST_FOUR, N), round_len=4, reading_errors={"ن": 9})
    assert p.reason is not PickReason.MISTAKE


def test_new_takes_at_most_three_places_in_a_round(curriculum: Curriculum) -> None:
    round_ = [QuizOutcome(x, 1, 0, True, D0, PickReason.NEW) for x in (T, M, Z)]
    p = pick(curriculum, round_, round_len=3)
    assert p.reason is PickReason.OLD


def test_old_letters_least_recently_asked_first(curriculum: Curriculum) -> None:
    """Все прошли ступень ①: «новых» нет; старое — давно не спрошенная буква."""
    h = [*spaced(R, 3), *spaced(Z, 3), *spaced(M, 3), *spaced(T, 3)]
    h += [ok(M, 2), ok(T, 2), ok(Z, 2)]
    p = pick(curriculum, h, round_len=0, today=0)
    assert (p.letter_id, p.reason) == (R, PickReason.OLD)


def test_retry_comes_before_due(curriculum: Curriculum) -> None:
    h = [*spaced(T, 3), bad(Z, vowel=1), ok(R), ok(M)]
    p = pick(curriculum, h, round_len=3, today=1)
    assert (p.letter_id, p.reason, p.vowel) == (Z, PickReason.RETRY, 1)


def test_most_overdue_letter_first(curriculum: Curriculum) -> None:
    h = [*spaced(Z, 3, d=0), *spaced(T, 3, d=2)]  # ز к сроку с дня 1, ت — с дня 3
    p = pick(curriculum, h, today=5)
    assert (p.letter_id, p.reason) == (Z, PickReason.DUE)


def test_retry_waits_until_letter_is_free(curriculum: Curriculum) -> None:
    """Ошибка раунда возвращается не раньше, чем через 2 вопроса, — и не позже, если её место
    свободно: через 2 вопроса она первая."""
    h = [bad(Z), ok(R)]
    assert pick(curriculum, h, round_len=2).reason is not PickReason.RETRY
    h.append(ok(M))
    assert pick(curriculum, h, round_len=3).reason is PickReason.RETRY


def test_vowel_least_asked_at_this_step(curriculum: Curriculum) -> None:
    h = [ok(T, vowel=0), ok(R), ok(M), ok(T, vowel=2), ok(R), ok(M)]
    assert pick(curriculum, h, started=(R, M, T, Z), round_len=0).vowel in {1}


def test_hearing_uses_only_syllables_with_audio(curriculum: Curriculum) -> None:
    h = [*spaced(T, 3)]
    p = pick(curriculum, h, started=(R, Z, M, T), round_len=0, today=1, audio={"L007-04"})
    assert (p.letter_id, p.step, p.vowel) == (T, 2, 2)


def test_confident_letter_due_is_asked_by_reading(curriculum: Curriculum) -> None:
    h = [*spaced(T, 3, 1), *spaced(T, 3, 2), *spaced(T, 3, 3)]
    p = pick(curriculum, h, today=1)
    assert (p.letter_id, p.step, p.reason) == (T, 3, PickReason.DUE)


@given(
    answers=st.lists(
        st.tuples(st.sampled_from(FIRST_FOUR), st.integers(1, 3), st.booleans()), max_size=40
    ),
    data=st.data(),
)
def test_pick_is_always_a_started_letter_and_keeps_a_gap(
    curriculum: Curriculum, answers: list[tuple[str, int, bool]], data: st.DataObject
) -> None:
    """Четыре начатые буквы: свободная всегда есть — буквы из двух последних вопросов не идут,
    в том числе на стыке раундов (``round_len`` = 0)."""
    h = [QuizOutcome(x, s, 0, c, D0) for x, s, c in answers]
    round_len = data.draw(st.integers(0, min(len(h), 9)))
    try:
        p = pick(curriculum, h, round_len=round_len)
    except NothingToday:  # все буквы на ⭐ и отдыхают до срока — вопроса нет, и это верно
        return
    assert p.letter_id in FIRST_FOUR
    assert 1 <= p.step <= 3 and 0 <= p.vowel <= 2
    assert p.letter_id not in {o.letter_id for o in h[-2:]}


@given(
    answers=st.lists(
        st.tuples(st.sampled_from(FIRST_FOUR), st.integers(1, 3), st.booleans(), st.integers(0, 3)),
        max_size=60,
    )
)
def test_step_never_goes_down(answers: list[tuple[str, int, bool, int]]) -> None:
    h = [QuizOutcome(x, s, 0, c, day(d)) for x, s, c, d in sorted(answers, key=lambda a: a[3])]
    before: dict[str, int] = {}
    for k in range(len(h) + 1):
        now = {x: s.step for x, s in letter_states(h[:k]).items()}
        assert all(now[x] >= step for x, step in before.items())
        before = now


# ---------- вопрос ----------
def _syllable(curriculum: Curriculum, letter: str, vowel: int) -> tuple[str, str, str]:
    lesson, _ = curriculum.locate(letter)
    s = [i for i in lesson.items if i.kind is ItemKind.SYLLABLE][vowel]
    return s.id, s.text, s.sound


def test_recognize_question_shows_syllable_and_four_cyrillic_options(
    curriculum: Curriculum,
) -> None:
    q = build_question(curriculum, quiz.Pick(T, 1, 2, PickReason.NEW), started=FIRST_FOUR)
    item_id, text, sound = _syllable(curriculum, T, 2)
    assert (q.item_id, q.prompt) == (item_id, text)
    assert len(q.options) == 4 and len(set(q.options)) == 4
    assert q.options[q.answer] == sound == "ту"
    assert {"та", "ти"} <= set(q.options)  # та же буква, другие огласовки


def test_confusable_started_letter_comes_before_nearest(curriculum: Curriculum) -> None:
    """ك и ق путают на слух: «ко» среди вариантов, хотя ب и ل ближе по книге."""
    q = build_question(curriculum, quiz.Pick(K, 1, 0, PickReason.OLD), started=(B, K, L, Q))
    assert "ко" in q.options


def test_without_confusable_started_nearest_started_letter_is_used(
    curriculum: Curriculum,
) -> None:
    q = build_question(curriculum, quiz.Pick(M, 1, 0, PickReason.OLD), started=(R, Z, M))
    assert set(q.options) == {"ма", "ми", "му", "за"}


SAD, TAA, DAD = "L020-05", "L021-05", "L028-05"  # ص ط ض


def test_recognize_uses_sound_pairs_not_shape_pairs(curriculum: Curriculum) -> None:
    """① — пары на слух: ض похожа на ص только на вид, поэтому берётся ближайшая ط."""
    q = build_question(curriculum, quiz.Pick(SAD, 1, 0, PickReason.OLD), (SAD, TAA, DAD))
    assert "то" in q.options and "до" not in q.options


def test_hear_uses_shape_pairs_too(curriculum: Curriculum) -> None:
    q = build_question(curriculum, quiz.Pick(SAD, 2, 0, PickReason.OLD), (SAD, TAA, DAD))
    assert "ضَ" in q.options


def test_hear_question_has_arabic_syllables_as_options(curriculum: Curriculum) -> None:
    q = build_question(curriculum, quiz.Pick(T, 2, 1, PickReason.OLD), started=FIRST_FOUR)
    item_id, text, _ = _syllable(curriculum, T, 1)
    assert q.item_id == item_id and q.step == 2
    assert q.options[q.answer] == text
    assert len(set(q.options)) == 4
    assert all(not any("а" <= ch <= "я" for ch in o) for o in q.options)  # без кириллицы


def test_read_question_is_the_letter_line_from_the_book(curriculum: Curriculum) -> None:
    q = build_question(curriculum, quiz.Pick(T, 3, 0, PickReason.OLD), started=FIRST_FOUR)
    assert q.item_id == T and q.prompt == curriculum.item(T).text
    assert q.options == () and q.answer == -1


def test_question_is_deterministic(curriculum: Curriculum) -> None:
    p = quiz.Pick(T, 1, 0, PickReason.NEW)
    assert build_question(curriculum, p, FIRST_FOUR) == build_question(curriculum, p, FIRST_FOUR)


# ---------- итог и «ждут» ----------
def test_round_summary_counts_and_lists_letters_to_repeat_in_book_order() -> None:
    round_ = [ok(T), bad(Z), ok(M), bad(R), bad(Z), ok(T)]
    s = round_summary(round_, letter_states(round_))
    assert (s.correct, s.total) == (3, 6)
    assert s.repeat == (R, Z)


def test_round_summary_counts_confident_letters() -> None:
    h = [*spaced(T, 3, 1), *spaced(T, 3, 2), *spaced(T, 3, 3), ok(T, 3, d=1)]
    assert round_summary(h[-1:], letter_states(h)).confident == 1


def test_letter_due_and_with_mistake_waits_once(curriculum: Curriculum) -> None:
    h = [*spaced(T, 3), ok(R), bad(T, 2), ok(Z), ok(M)]
    n = letters_waiting(
        curriculum, letter_states(h), h, started=FIRST_FOUR, today=day(1), reading_errors={"ت": 2}
    )
    assert n == 1


def test_reading_mistakes_wait(curriculum: Curriculum) -> None:
    n = letters_waiting(
        curriculum, {}, [], started=FIRST_FOUR, today=D0, reading_errors={"ر": 1, "ب": 3}
    )
    assert n == 1  # ب не начата


def test_letters_waiting_counts_due_and_mistakes(curriculum: Curriculum) -> None:
    h = [*spaced(T, 3), bad(Z), ok(R), ok(M)]
    n = letters_waiting(
        curriculum, letter_states(h), h, started=FIRST_FOUR, today=day(1), reading_errors={}
    )
    assert n == 2  # ت — к сроку, ز — ошибка


def test_nothing_waits_for_fresh_learner(curriculum: Curriculum) -> None:
    assert letters_waiting(curriculum, {}, [], started=FIRST_FOUR, today=D0, reading_errors={}) == 0


# ---------- «Не могу сейчас говорить / слушать» (как в Duolingo, автор 2026-10-23) ----------
def test_skip_pause_is_fifteen_minutes() -> None:
    assert quiz.QUIZ_SKIP_PAUSE_MIN == 15


def test_blocked_reading_asks_by_hearing_instead(curriculum: Curriculum) -> None:
    h = _confident()
    p = next_pick(
        curriculum, started=FIRST_FOUR, history=h, round_len=0, today=day(1),
        reading_errors={}, blocked_steps={Step.READ},
    )  # fmt: skip
    assert (p.letter_id, p.step, p.reason) == (T, Step.HEAR, PickReason.DUE)


def test_blocked_reading_and_hearing_asks_by_recognizing(curriculum: Curriculum) -> None:
    h = _confident()
    p = next_pick(
        curriculum, started=FIRST_FOUR, history=h, round_len=0, today=day(1),
        reading_errors={}, blocked_steps={Step.READ, Step.HEAR},
    )  # fmt: skip
    assert (p.letter_id, p.step) == (T, Step.RECOGNIZE)


def test_blocked_hearing_does_not_touch_other_steps(curriculum: Curriculum) -> None:
    p = next_pick(
        curriculum, started=FIRST_FOUR, history=(), round_len=0, today=D0,
        reading_errors={}, blocked_steps={Step.HEAR},
    )  # fmt: skip
    assert p.step == Step.RECOGNIZE


@given(blocked=st.sets(st.sampled_from([Step.HEAR, Step.READ])))
def test_blocked_step_is_never_asked(curriculum: Curriculum, blocked: set[Step]) -> None:
    h = [*_confident(), *spaced(R, 3)]
    for today in (0, 1, 5):
        p = next_pick(
            curriculum, started=FIRST_FOUR, history=h, round_len=0, today=day(today),
            reading_errors={}, blocked_steps=blocked,
        )  # fmt: skip
        assert p.step not in blocked


# ---------- «На сегодня всё» (автор 2026-10-23: вместо однообразных повторов) ----------
def _rested(letter: str) -> list[QuizOutcome]:
    """Буква прошла ③ в день 0 и подтвердила ⭐ в день 1: следующий срок — день 4."""
    return [*spaced(letter, 3, 1), *spaced(letter, 3, 2), *spaced(letter, 3, 3), ok(letter, 3, d=1)]


def test_nothing_today_when_all_letters_confident_and_not_due(curriculum: Curriculum) -> None:
    h = [*_rested(R), *_rested(Z)]
    with pytest.raises(NothingToday):
        pick(curriculum, h, started=(R, Z), today=2)


def test_confident_letter_comes_back_on_due_day(curriculum: Curriculum) -> None:
    h = [*_rested(R), *_rested(Z)]
    p = pick(curriculum, h, started=(R, Z), today=4)
    assert p.reason is PickReason.DUE


def test_letter_waiting_for_confirmation_rests_until_due(curriculum: Curriculum) -> None:
    """Прошла ③ сегодня — ⭐ ждёт завтрашнего ответа; сегодня её не гоняем по кругу."""
    h = [*_confident(), *spaced(M, 3, 1), *spaced(M, 3, 2), *spaced(M, 3, 3)]
    with pytest.raises(NothingToday):
        pick(curriculum, h, started=(M, T), today=0)


def test_reading_mistake_breaks_the_rest(curriculum: Curriculum) -> None:
    h = [*_rested(R), *_rested(Z)]
    p = pick(curriculum, h, started=(R, Z), today=2, reading_errors={"ز": 1})
    assert (p.letter_id, p.reason) == (Z, PickReason.MISTAKE)


# ---------- две начатые буквы: хватает паузы в один вопрос (автор 2026-10-23) ----------
def test_gap_for_two_letters_is_one_and_for_more_is_two() -> None:
    assert quiz.gap_for(2) == 1
    assert quiz.gap_for(3) == quiz.gap_for(28) == quiz.QUIZ_MIN_GAP


def test_two_letters_alternating_raise_the_step_in_one_day() -> None:
    """ر ز ر ز ر ز — все верно: с паузой 1 ступень растёт в первый же день."""
    h = [ok(R), ok(Z), ok(R), ok(Z), ok(R), ok(Z)]
    assert letter_states(h, min_gap=quiz.gap_for(2))[R].step == 2
    assert letter_states(h)[R].step == 1  # по общему правилу (пауза 2) — ещё нет


def test_two_started_letters_progress_in_quiz(curriculum: Curriculum) -> None:
    """``next_pick`` сам берёт паузу по числу начатых букв: после 6 верных ر уже на ②."""
    h = [ok(R), ok(Z), ok(R), ok(Z), ok(R), ok(Z)]
    p = pick(curriculum, h, started=(R, Z))
    assert (p.letter_id, p.step) == (R, Step.HEAR)
