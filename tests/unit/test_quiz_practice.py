"""Сценарий «🧠 Закрепления» (FR-53, ADR-0066): раунд из 10 вопросов, строка ``quiz_answers``
при показе, ответ — в неё же; устаревшие и чужие кнопки не пишутся; ступень ③ — голосовым.

``PracticeQuiz`` собирает историю из хранилища ответов, начатые буквы — из попыток (как FR-39),
ошибки чтения — из ``AttemptRepository.recent_errors``.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from muallim.application.use_cases.learners import EnsureLearner
from muallim.application.use_cases.quiz import PracticeQuiz, QuizRest, QuizStale, QuizView
from muallim.domain import quiz
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from tests.fakes import (
    FixedClock,
    InMemoryAttempts,
    InMemoryLearners,
    InMemoryQuizAnswers,
    InMemoryReferenceAudio,
    ListEventLog,
    SequentialIds,
    SpyUoW,
)


class World:
    def __init__(self, curriculum: Curriculum) -> None:
        self.curriculum = curriculum
        self.attempts = InMemoryAttempts()
        self.answers = InMemoryQuizAnswers()
        self.audio = InMemoryReferenceAudio()
        self.events = ListEventLog()
        self.uow = SpyUoW()
        self.clock = FixedClock()
        self.ids = SequentialIds()

    def quiz(self) -> PracticeQuiz:
        return PracticeQuiz(
            curriculum=self.curriculum,
            attempts=self.attempts,
            answers=self.answers,
            audio=self.audio,
            events=self.events,
            uow=self.uow,
            clock=self.clock,
            ids=self.ids,
        )

    async def learner(self, tg: int = 1) -> Learner:
        learner, _ = await EnsureLearner(
            InMemoryLearners(), self.uow, self.clock, self.ids, self.events
        ).execute(tg, "ru")
        return learner

    async def start_letters(self, learner: Learner, n: int) -> None:
        """Ученик читал по строке в первых ``n`` уроках букв."""
        letters = [les for les in self.curriculum.lessons if les.section == "letter"][:n]
        for les in letters:
            await self.attempts.add(self._attempt(learner, les.items[0].id), ())

    def _attempt(self, learner: Learner, item_id: str) -> Attempt:
        return Attempt(
            self.ids.new_id(), learner.id, item_id, "v", "m", assess("بَ", "بَ"),
            Verdict.EXCELLENT, None, None, 1, self.clock.now(),
        )  # fmt: skip


@pytest.fixture
def w(curriculum: Curriculum) -> World:
    return World(curriculum)


async def test_quiz_is_locked_until_two_letters_started(w: World) -> None:
    learner = await w.learner()
    assert await w.quiz().current(learner) is None
    assert w.answers.rows == {}


async def test_first_question_opens_round_one_position_one(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    assert (view.round_no, view.position, view.correct_so_far) == (1, 1, 0)
    row = w.answers.rows[view.answer_id]
    assert row.learner_id == learner.id and row.answered_at is None
    assert row.options == view.question.options and row.answer == view.question.answer
    assert row.curriculum_version == w.curriculum.version and row.rule == quiz.QUIZ_RULE
    assert w.uow.commits >= 1


async def test_unanswered_question_is_shown_again_not_duplicated(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    first = await w.quiz().current(learner)
    again = await w.quiz().current(learner)
    assert first is not None and again is not None
    assert again.answer_id == first.answer_id
    assert len(w.answers.rows) == 1


async def test_correct_answer_is_saved_and_logged(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    result = await w.quiz().answer(learner, view.answer_id, view.question.answer)
    assert result.correct and not result.finished
    row = w.answers.rows[view.answer_id]
    assert row.picked == view.question.answer and row.correct is True
    assert row.answered_at is not None and row.answered_at > row.shown_at
    event, who, payload = w.events.events[-1]
    assert (event, who) == ("quiz_answered", learner.id)
    assert payload["correct"] is True and payload["step"] == view.question.step


async def test_next_question_follows_answer_with_position_and_score(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    q = w.quiz()
    view = await q.current(learner)
    assert view is not None
    await q.answer(learner, view.answer_id, view.question.answer)
    nxt = await q.current(learner)
    assert nxt is not None
    assert (nxt.round_no, nxt.position, nxt.correct_so_far) == (1, 2, 1)
    assert nxt.question.letter_id != view.question.letter_id  # не подряд


async def test_answering_twice_is_stale(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    await w.quiz().answer(learner, view.answer_id, 0)
    n = len(w.events.events)
    with pytest.raises(QuizStale):
        await w.quiz().answer(learner, view.answer_id, 1)
    assert len(w.events.events) == n
    assert w.answers.rows[view.answer_id].picked == 0


async def test_other_learners_button_is_stale(w: World) -> None:
    ali = await w.learner(1)
    bob = await w.learner(2)
    await w.start_letters(ali, 3)
    view = await w.quiz().current(ali)
    assert view is not None
    with pytest.raises(QuizStale):
        await w.quiz().answer(bob, view.answer_id, 0)
    assert w.answers.rows[view.answer_id].answered_at is None


@pytest.mark.parametrize("picked", [-1, 4])
async def test_forged_option_is_stale_and_not_saved(w: World, picked: int) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    with pytest.raises(QuizStale):
        await w.quiz().answer(learner, view.answer_id, picked)
    assert w.answers.rows[view.answer_id].answered_at is None


async def test_unknown_answer_id_is_stale(w: World) -> None:
    learner = await w.learner()
    with pytest.raises(QuizStale):
        await w.quiz().answer(learner, UUID(int=999_999), 0)


async def test_tenth_answer_finishes_round_with_summary(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 4)
    q = w.quiz()
    result = None
    right = 0
    for k in range(quiz.QUIZ_ROUND):
        view = await q.current(learner)
        assert view is not None and view.position == k + 1
        if view.question.step == quiz.Step.READ:  # на ③ кнопок нет — голосовое
            result = await q.attach_attempt(
                learner, view.question.item_id, UUID(int=k), passed=True
            )
            right += 1
        else:
            picked = view.question.answer if k % 2 == 0 else (view.question.answer + 1) % 4
            result = await q.answer(learner, view.answer_id, picked)
            right += picked == view.question.answer
        assert result is not None
        assert result.finished == (k == quiz.QUIZ_ROUND - 1)
    assert result is not None and result.summary is not None
    assert result.summary.total == quiz.QUIZ_ROUND
    assert result.summary.correct == right
    assert result.summary.letters == 4
    nxt = await q.current(learner)
    assert nxt is not None and (nxt.round_no, nxt.position) == (2, 1)


async def test_read_step_cannot_be_answered_by_button(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    row = w.answers.rows[view.answer_id]
    w.answers.rows[view.answer_id] = replace(row, step=3, options=(), answer=-1)
    with pytest.raises(QuizStale):
        await w.quiz().answer(learner, view.answer_id, 0)


async def test_voice_on_read_step_is_linked_to_the_attempt(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    row = w.answers.rows[view.answer_id]
    w.answers.rows[view.answer_id] = replace(
        row, step=3, item_id=row.letter_id, options=(), answer=-1
    )
    attempt = UUID(int=4242)
    result = await w.quiz().attach_attempt(learner, row.letter_id, attempt, passed=False)
    assert result is not None and result.correct is False
    saved = w.answers.rows[view.answer_id]
    assert (saved.attempt_id, saved.correct, saved.picked) == (attempt, False, None)


async def test_voice_on_another_card_is_not_linked(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    row = w.answers.rows[view.answer_id]
    w.answers.rows[view.answer_id] = replace(
        row, step=3, item_id=row.letter_id, options=(), answer=-1
    )
    assert await w.quiz().attach_attempt(learner, "L001-01", UUID(int=1), passed=True) is None
    assert w.answers.rows[view.answer_id].answered_at is None


async def test_second_voice_does_not_overwrite_read_answer(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None
    row = w.answers.rows[view.answer_id]
    w.answers.rows[view.answer_id] = replace(
        row, step=3, item_id=row.letter_id, options=(), answer=-1
    )
    first = UUID(int=11)
    assert await w.quiz().attach_attempt(learner, row.letter_id, first, passed=True) is not None
    await w.quiz().attach_attempt(learner, row.letter_id, UUID(int=12), passed=False)
    saved = w.answers.rows[view.answer_id]
    assert (saved.attempt_id, saved.correct) == (first, True)


async def test_reading_mistake_leads_the_round(w: World) -> None:
    """Ошибка чтения голосом в букве ز — первый вопрос раунда о ней, причина «ошибка»."""
    learner = await w.learner()
    await w.start_letters(learner, 3)
    zay = next(les for les in w.curriculum.lessons if les.id == "L005")
    a = assess("زَ", "سَ")
    assert a.errors
    await w.attempts.add(
        Attempt(
            w.ids.new_id(), learner.id, zay.practice_items[0].id, "v", "m", a,
            Verdict.FAILED, None, None, 1, w.clock.now(),
        ),
        tuple("x" for _ in a.errors),
    )  # fmt: skip
    view = await w.quiz().current(learner)
    assert view is not None
    row = w.answers.rows[view.answer_id]
    assert (row.letter_id, row.reason) == ("L005-05", quiz.PickReason.MISTAKE)


async def test_voice_without_open_read_question_is_not_linked(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    view = await w.quiz().current(learner)
    assert view is not None and view.question.step != quiz.Step.READ
    assert (
        await w.quiz().attach_attempt(learner, view.question.item_id, UUID(int=1), passed=True)
        is None
    )
    assert w.answers.rows[view.answer_id].answered_at is None


async def test_hear_step_is_skipped_for_letters_without_syllable_audio(w: World) -> None:
    """Нет ни одной записи слога — ступени ② нет (ADR-0066 п. 2); с записями — есть."""
    learner = await w.learner()
    await w.start_letters(learner, 4)
    q = w.quiz()
    steps = set()
    for _ in range(40):
        view = await q.current(learner)
        if view is None:  # все буквы прошли ③ и отдыхают до завтра (автор 2026-10-23)
            assert await q.rest(learner) is not None
            break
        steps.add(view.question.step)
        if view.question.step == quiz.Step.READ:
            await q.attach_attempt(learner, view.question.item_id, UUID(int=7), passed=True)
        else:
            await q.answer(learner, view.answer_id, view.question.answer)
    assert quiz.Step.HEAR not in steps
    assert quiz.Step.READ in steps  # буквы поднимаются — ② именно пропущена


async def test_hear_step_appears_when_syllables_have_audio(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 4)
    for les in w.curriculum.lessons:
        for item in les.items:
            w.audio.files[item.id] = b"ogg"
    q = w.quiz()
    steps = set()
    for _ in range(40):
        view = await q.current(learner)
        if view is None:  # все буквы прошли ③ и отдыхают до завтра (автор 2026-10-23)
            assert await q.rest(learner) is not None
            break
        steps.add(view.question.step)
        if view.question.step == quiz.Step.HEAR:
            assert w.audio.has(view.question.item_id)
        if view.question.step == quiz.Step.READ:
            await q.attach_attempt(learner, view.question.item_id, UUID(int=7), passed=True)
        else:
            await q.answer(learner, view.answer_id, view.question.answer)
    assert quiz.Step.HEAR in steps


async def test_overview_counts_confident_letters_and_waiting(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    o = await w.quiz().overview(learner)
    assert (o.confident, o.letters, o.waiting) == (0, 3, 0)


# ---------- «Не могу сейчас говорить / слушать» (автор 2026-10-23, как в Duolingo) ----------
async def _open_at_step(w: World, learner: Learner, step: int) -> UUID:
    view = await w.quiz().current(learner)
    assert view is not None
    row = w.answers.rows[view.answer_id]
    if step == quiz.Step.READ:
        row = replace(row, step=3, item_id=row.letter_id, options=(), answer=-1)
    else:
        row = replace(row, step=step)
    w.answers.rows[view.answer_id] = row
    return view.answer_id


@pytest.mark.parametrize("step", [quiz.Step.HEAR, quiz.Step.READ])
async def test_skip_is_not_a_mistake_and_shows_next_question(w: World, step: int) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 4)
    answer_id = await _open_at_step(w, learner, step)
    nxt = await w.quiz().skip(learner, answer_id)
    row = w.answers.rows[answer_id]
    assert row.answered_at is not None and row.correct is None and row.picked is None
    assert nxt is not None and nxt.answer_id != answer_id and nxt.position == 2
    assert nxt.correct_so_far == 0
    assert nxt.question.step != step
    event, _, payload = w.events.events[-1]
    assert event == "quiz_skipped" and payload["step"] == step


async def test_recognize_step_cannot_be_skipped(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    answer_id = await _open_at_step(w, learner, quiz.Step.RECOGNIZE)
    with pytest.raises(QuizStale):
        await w.quiz().skip(learner, answer_id)


async def test_skip_twice_or_other_learner_is_stale(w: World) -> None:
    ali = await w.learner(1)
    bob = await w.learner(2)
    await w.start_letters(ali, 3)
    answer_id = await _open_at_step(w, ali, quiz.Step.READ)
    with pytest.raises(QuizStale):
        await w.quiz().skip(bob, answer_id)
    await w.quiz().skip(ali, answer_id)
    with pytest.raises(QuizStale):
        await w.quiz().skip(ali, answer_id)


async def test_skipped_step_comes_back_after_pause(w: World) -> None:
    """15 минут ступень не спрашивается, потом — снова (как «Не могу сейчас говорить»)."""
    learner = await w.learner()
    await w.start_letters(learner, 4)
    answer_id = await _open_at_step(w, learner, quiz.Step.READ)
    await w.quiz().skip(learner, answer_id)
    q = w.quiz()
    seen: set[int] = set()
    for _ in range(25):  # все ответы верные — буквы доходят до ③, но ③ на паузе
        view = await q.current(learner)
        assert view is not None
        seen.add(view.question.step)
        await q.answer(learner, view.answer_id, view.question.answer)
    assert quiz.Step.READ not in seen
    w.clock.current += timedelta(minutes=quiz.QUIZ_SKIP_PAUSE_MIN + 1)
    later: set[int] = set()
    for _ in range(10):
        view = await q.current(learner)
        assert view is not None
        later.add(view.question.step)
        if view.question.step == quiz.Step.READ:
            break
        await q.answer(learner, view.answer_id, view.question.answer)
    assert quiz.Step.READ in later


async def test_skipped_question_is_not_counted_in_summary(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 4)
    answer_id = await _open_at_step(w, learner, quiz.Step.READ)
    q = w.quiz()
    await q.skip(learner, answer_id)
    result = None
    for _ in range(quiz.QUIZ_ROUND - 1):
        view = await q.current(learner)
        assert view is not None
        if view.question.step == quiz.Step.READ:
            result = await q.attach_attempt(
                learner, view.question.item_id, UUID(int=3), passed=True
            )
        else:
            result = await q.answer(learner, view.answer_id, view.question.answer)
    assert result is not None and result.summary is not None
    assert (result.summary.correct, result.summary.total) == (9, 9)


# ---------- «На сегодня всё» и одно место — один вопрос (автор 2026-10-23) ----------
async def test_rest_when_all_letters_confident_and_not_due(w: World) -> None:
    """Обе буквы прошли ③ и подтвердили ⭐ на следующий день; срок — через 3 дня: вопросов нет,
    бот говорит «на сегодня всё», а не гоняет те же буквы по кругу."""
    learner = await w.learner()
    await w.start_letters(learner, 2)  # ء и ر
    letters = ["L003-10", "L004-05"]
    today = w.clock.current
    base = today - timedelta(days=10)
    n = 0
    for d in range(9):  # по одному верному ответу в день: ступени 1, 2, 3 по три дня
        for x in letters:
            n += 1
            at = base + timedelta(days=d, minutes=n)
            w.answers.rows[UUID(int=10_000 + n)] = _done_row(learner, x, d // 3 + 1, at, n)
    for x in letters:  # подтверждение ⭐ на 9-й день
        n += 1
        at = base + timedelta(days=9, minutes=n)
        w.answers.rows[UUID(int=10_000 + n)] = _done_row(learner, x, 3, at, n)
    assert await w.quiz().current(learner) is None  # вопроса нет
    assert await w.quiz().rest(learner) == QuizRest(confident=2, letters=2)
    assert w.answers.rows.keys() >= set() and all(r.answered_at for r in w.answers.rows.values())
    o = await w.quiz().overview(learner)
    assert (o.confident, o.waiting) == (2, 0)


def _done_row(learner: Learner, letter: str, step: int, at: datetime, n: int) -> quiz.QuizAnswer:
    return quiz.QuizAnswer(
        id=UUID(int=10_000 + n), learner_id=learner.id, round_no=1 + (n - 1) // 10,
        position=1 + (n - 1) % 10, step=step, letter_id=letter, item_id=letter, vowel=0,
        options=(), answer=-1, shown_at=at, curriculum_version="v", rule=quiz.QUIZ_RULE,
        picked=None, correct=True, attempt_id=UUID(int=n), answered_at=at,
    )  # fmt: skip


async def test_place_already_taken_shows_that_question(w: World) -> None:
    """Двойное нажатие: второй запрос не создаёт второй вопрос на то же место."""
    learner = await w.learner()
    await w.start_letters(learner, 3)
    first = await w.quiz().current(learner)
    assert isinstance(first, QuizView)
    row = w.answers.rows[first.answer_id]
    taken = replace(row, id=UUID(int=55_555))
    assert not await w.answers.add(taken)  # то же место — не вставлено
    assert len(w.answers.rows) == 1


async def test_no_rest_while_there_is_work(w: World) -> None:
    learner = await w.learner()
    await w.start_letters(learner, 3)
    assert await w.quiz().rest(learner) is None


async def test_no_rest_when_quiz_is_locked(w: World) -> None:
    learner = await w.learner()
    assert await w.quiz().rest(learner) is None


async def test_two_letters_show_progress_on_first_day(w: World) -> None:
    """Начаты две буквы, все ответы верные: за первый раунд буквы поднимаются со ступени ①."""
    learner = await w.learner()
    await w.start_letters(learner, 2)
    q = w.quiz()
    steps: list[int] = []
    for _ in range(quiz.QUIZ_ROUND):
        view = await q.current(learner)
        assert view is not None
        steps.append(view.question.step)
        if view.question.step == quiz.Step.READ:
            await q.attach_attempt(learner, view.question.item_id, UUID(int=9), passed=True)
        else:
            await q.answer(learner, view.answer_id, view.question.answer)
    assert max(steps) > quiz.Step.RECOGNIZE
