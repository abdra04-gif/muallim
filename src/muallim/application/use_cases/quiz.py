"""«🧠 Закрепление» (FR-53, ADR-0066): раунд из 10 вопросов, лестница по букве, повторение.

Каждый показанный вопрос — строка ``quiz_answers`` (с вариантами, как показаны); ответ кнопкой или
голосовым (ступень ③) дописывается в неё же один раз. Начатые буквы — из попыток (как FR-39),
ошибки чтения — из последних попыток (как «🔁 Повторение», ADR-0062). Своего состояния нет:
ступени и сроки каждый раз проигрываются из истории (``domain.quiz``).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID

from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerSettingsRepository,
    QuizAnswerRepository,
    UnitOfWork,
)
from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.ports.system import Clock, EventLog, IdGenerator
from muallim.domain import review
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.quiz import (
    QUIZ_ROUND,
    QUIZ_RULE,
    QUIZ_SKIP_PAUSE_MIN,
    NothingToday,
    PickReason,
    QuizAnswer,
    QuizError,
    QuizOutcome,
    QuizQuestion,
    RoundSummary,
    Step,
    build_question,
    gap_for,
    letter_heads,
    letter_states,
    letters_waiting,
    next_pick,
    round_summary,
    without_hearing,
)
from muallim.domain.settings import DEFAULT_UTC_OFFSET_MIN, local_date


class QuizStale(LookupError):  # noqa: N818 — имя из тестов: «кнопка устарела»
    """Кнопка устарела, чужая или подделана: ответ не пишется."""


@dataclass(frozen=True, slots=True)
class QuizView:
    answer_id: UUID
    question: QuizQuestion
    round_no: int
    position: int  # 1..QUIZ_ROUND
    correct_so_far: int  # верных в раунде до этого вопроса


@dataclass(frozen=True, slots=True)
class QuizResult:
    view: QuizView
    picked: int | None
    correct: bool
    finished: bool  # это был последний вопрос раунда
    summary: RoundSummary | None = None


@dataclass(frozen=True, slots=True)
class QuizRest:
    """«На сегодня всё»: буквы отдыхают до срока повторения, ошибок нет."""

    confident: int
    letters: int


@dataclass(frozen=True, slots=True)
class QuizOverview:
    confident: int  # букв «⭐ уверенно»
    letters: int  # начатых букв
    waiting: int  # к сроку или с ошибкой


@dataclass(frozen=True, slots=True)
class PracticeQuiz:
    curriculum: Curriculum
    attempts: AttemptRepository
    answers: QuizAnswerRepository
    audio: ReferenceAudioLibrary
    events: EventLog
    uow: UnitOfWork
    clock: Clock
    ids: IdGenerator
    settings: LearnerSettingsRepository | None = None  # нет — «сегодня» по UTC+3

    async def current(self, learner: Learner) -> QuizView | None:
        """Открытый вопрос (если не отвечен) или новый; None — начато меньше двух букв."""
        started = await self._started(learner)
        if len(started) < 2:
            return None
        rows = await self.answers.history(learner.id)
        if rows and rows[-1].answered_at is None and self._known(rows[-1]):
            return self._view(rows[-1], rows)
        round_no, position = _next_place(rows)  # строку убранной карточки — бросаем
        offset = await self._offset(learner)
        history = _outcomes(rows, offset)
        try:
            pick = next_pick(
                self.curriculum,
                started=started,
                history=history,
                round_len=position - 1,
                today=local_date(self.clock.now(), offset),
                reading_errors=await self._reading_errors(learner),
                has_audio=self.audio.has,
                blocked_steps=self._paused(rows),
            )
        except (QuizError, NothingToday):
            return None  # закрыто (меньше двух букв) или на сегодня всё — см. ``rest``
        q = build_question(self.curriculum, pick, started, shuffle=f"{round_no}:{position}")
        row = QuizAnswer(
            id=self.ids.new_id(),
            learner_id=learner.id,
            round_no=round_no,
            position=position,
            step=q.step,
            letter_id=q.letter_id,
            item_id=q.item_id,
            vowel=q.vowel,
            options=q.options,
            answer=q.answer,
            shown_at=self.clock.now(),
            curriculum_version=self.curriculum.version,
            rule=QUIZ_RULE,
            reason=str(pick.reason),
        )
        if not await self.answers.add(row):  # место заняло соседнее нажатие — покажем его
            rows = await self.answers.history(learner.id)
            same = [r for r in rows if (r.round_no, r.position) == (round_no, position)]
            return self._view(same[0], rows) if same else None
        await self.uow.commit()
        return self._view(row, [*rows, row])

    async def rest(self, learner: Learner) -> QuizRest | None:
        """«На сегодня всё», если вопросов нет потому, что буквы отдыхают (не замок, не ошибка)."""
        started = await self._started(learner)
        if len(started) < 2:
            return None
        offset = await self._offset(learner)
        rows = await self.answers.history(learner.id)
        history = _outcomes(rows, offset)
        try:
            next_pick(
                self.curriculum,
                started=started,
                history=history,
                round_len=_next_place(rows)[1] - 1,
                today=local_date(self.clock.now(), offset),
                reading_errors=await self._reading_errors(learner),
                has_audio=self.audio.has,
                blocked_steps=self._paused(rows),
            )
        except NothingToday:
            states = letter_states(
                history,
                without_hearing(self.curriculum, started, self.audio.has),
                gap_for(len(started)),
            )
            confident = sum(states[x].confident for x in started if x in states)
            return QuizRest(confident, len(started))
        except QuizError:
            return None
        return None

    async def skip(self, learner: Learner, answer_id: UUID) -> QuizView | None:
        """«Не могу сейчас слушать / говорить» (②③, как в Duolingo): вопрос закрыт без ответа —
        не ошибка; ступень на ``QUIZ_SKIP_PAUSE_MIN`` минут не спрашивается. Дальше — следующий."""
        row = await self.answers.get(answer_id)
        if (
            row is None
            or row.learner_id != learner.id
            or row.answered_at is not None
            or row.step == Step.RECOGNIZE
        ):
            raise QuizStale(answer_id)
        saved = await self.answers.record(
            row.id, picked=None, correct=None, answered_at=self.clock.now()
        )
        if not saved:
            raise QuizStale(answer_id)
        await self.events.record(
            "quiz_skipped",
            learner.id,
            {
                "letter_id": row.letter_id,
                "item_id": row.item_id,
                "step": row.step,
                "position": row.position,
            },
        )
        await self.uow.commit()
        return await self.current(learner)

    async def answer(self, learner: Learner, answer_id: UUID, picked: int) -> QuizResult:
        """Ответ кнопкой на ступенях ①②."""
        row = await self.answers.get(answer_id)
        if (
            row is None
            or row.learner_id != learner.id
            or row.answered_at is not None
            or row.step == Step.READ
            or picked not in range(len(row.options))
        ):
            raise QuizStale(answer_id)
        return await self._record(learner, row, picked, picked == row.answer, None)

    async def attach_attempt(
        self, learner: Learner, item_id: str, attempt_id: UUID, *, passed: bool
    ) -> QuizResult | None:
        """Голосовое на ступени ③: связать попытку с открытым вопросом этой строки."""
        rows = await self.answers.history(learner.id)
        if not rows:
            return None
        row = rows[-1]
        if row.answered_at is not None or row.step != Step.READ or row.item_id != item_id:
            return None
        return await self._record(learner, row, None, passed, attempt_id)

    async def overview(self, learner: Learner) -> QuizOverview:
        started = await self._started(learner)
        offset = await self._offset(learner)
        history = _outcomes(await self.answers.history(learner.id), offset)
        states = letter_states(
            history,
            without_hearing(self.curriculum, started, self.audio.has),
            gap_for(len(started)),
        )
        waiting = letters_waiting(
            self.curriculum,
            states,
            history,
            started=started,
            today=local_date(self.clock.now(), offset),
            reading_errors=await self._reading_errors(learner),
        )
        confident = sum(states[x].confident for x in started if x in states)
        return QuizOverview(confident, len(started), waiting)

    async def _record(
        self,
        learner: Learner,
        row: QuizAnswer,
        picked: int | None,
        correct: bool,
        attempt_id: UUID | None,
    ) -> QuizResult:
        now = self.clock.now()
        saved = await self.answers.record(
            row.id, picked=picked, correct=correct, answered_at=now, attempt_id=attempt_id
        )
        if not saved:  # ответили в соседнем запросе
            raise QuizStale(row.id)
        await self.events.record(
            "quiz_answered",
            learner.id,
            {
                "letter_id": row.letter_id,
                "item_id": row.item_id,
                "step": row.step,
                "vowel": row.vowel,
                "position": row.position,
                "correct": correct,
            },
        )
        await self.uow.commit()
        done = replace(row, picked=picked, correct=correct, answered_at=now, attempt_id=attempt_id)
        rows = [r if r.id != row.id else done for r in await self.answers.history(learner.id)]
        view = self._view(row, rows)
        finished = row.position >= QUIZ_ROUND
        summary = None
        if finished:
            offset = await self._offset(learner)
            started = await self._started(learner)
            history = _outcomes(rows, offset)
            this_round = _outcomes([r for r in rows if r.round_no == row.round_no], offset)
            states = letter_states(
                history,
                without_hearing(self.curriculum, started, self.audio.has),
                gap_for(len(started)),
            )
            summary = replace(
                round_summary(this_round, {x: s for x, s in states.items() if x in started}),
                letters=len(started),
            )
        return QuizResult(view, picked, correct, finished, summary)

    def _paused(self, rows: Sequence[QuizAnswer]) -> set[int]:
        """Ступени, пропущенные кнопкой «Не могу сейчас…» за последние ``QUIZ_SKIP_PAUSE_MIN``."""
        since = self.clock.now() - timedelta(minutes=QUIZ_SKIP_PAUSE_MIN)
        return {
            r.step
            for r in rows
            if r.answered_at is not None and r.answered_at >= since and _skipped(r)
        }

    def _known(self, row: QuizAnswer) -> bool:
        """Карточка строки ещё есть в программе (её могли убрать при пересборке книги)."""
        try:
            self.curriculum.item(row.item_id)
        except KeyError:
            return False
        return True

    def _view(self, row: QuizAnswer, rows: Sequence[QuizAnswer]) -> QuizView:
        same = [r for r in rows if r.round_no == row.round_no and r.position < row.position]
        prompt = self.curriculum.item(row.item_id).text if self._known(row) else ""
        question = QuizQuestion(
            row.letter_id,
            row.step,
            row.vowel,
            row.item_id,
            prompt,
            row.options,
            row.answer,
        )
        return QuizView(
            row.id, question, row.round_no, row.position, sum(bool(r.correct) for r in same)
        )

    async def _started(self, learner: Learner) -> list[str]:
        """Буквы уроков, которые ученик читал (или открыл): из них вопросы и варианты."""
        tried = set(await self.attempts.best_scores(learner.id))
        lessons = [
            les
            for les in self.curriculum.lessons
            if les.section == "letter"
            and any(i.id in tried or i.id == learner.current_item_id for i in les.items)
        ]
        return letter_heads(lessons)

    async def _reading_errors(self, learner: Learner) -> dict[str, int]:
        errors = await self.attempts.recent_errors(learner.id, review.RECENT_ATTEMPTS_FOR_LETTERS)
        return review.error_letters(errors)

    async def _offset(self, learner: Learner) -> int:
        if self.settings is None:
            return DEFAULT_UTC_OFFSET_MIN
        return (await self.settings.get(learner.id)).utc_offset_min


def _next_place(rows: Sequence[QuizAnswer]) -> tuple[int, int]:
    """(раунд, место) следующего вопроса."""
    if not rows:
        return 1, 1
    last = rows[-1]
    if last.position >= QUIZ_ROUND:
        return last.round_no + 1, 1
    return last.round_no, last.position + 1


def _outcomes(rows: Sequence[QuizAnswer], offset: int) -> list[QuizOutcome]:
    reasons = {str(r) for r in PickReason}
    return [
        QuizOutcome(
            r.letter_id,
            r.step,
            r.vowel,
            bool(r.correct),
            local_date(r.answered_at, offset),
            PickReason(r.reason) if r.reason in reasons else PickReason.OLD,
        )
        for r in rows
        if r.answered_at is not None and not _skipped(r)
    ]


def _skipped(row: QuizAnswer) -> bool:
    """Закрыт кнопкой «Не могу сейчас…»: ни ответа, ни попытки."""
    return row.correct is None and row.picked is None and row.attempt_id is None
