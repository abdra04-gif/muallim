"""«🧠 Закрепление» по методике (FR-53, ADR-0066, M-19): лестница по букве, паузы, повторение.

Лестница: ① узнаю (слог → кириллица) → ② слышу (🔊 → арабский слог) → ③ читаю голосом. Ступень
пройдена после ``QUIZ_CRITERION`` верных ответов на ней, и верный ответ считается, только если с
прошлого вопроса по этой букве прошло ≥ ``QUIZ_MIN_GAP`` других вопросов или наступил другой день
(повторное припоминание с паузами, SRC-138…SRC-140). Ошибка ступень не понижает. Каждый подъём
на ступень запускает повторение 1·3·7 дней заново. Всё вычисляется из истории ответов, как
«🔁 Повторение» строк (ADR-0062): своего состояния нет.

Буква обозначается id головной карточки её урока (``ItemKind.LETTER``), например ``L004-05`` (ر).
"""

import random
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import IntEnum, StrEnum
from typing import Final
from uuid import UUID

from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem
from muallim.domain.policy import Verdict

# Параметры методики (M-19): меняет только автор (ADR-0066, решения автора 2026-10-22).
QUIZ_ROUND: Final = 10  # вопросов в раунде
QUIZ_CRITERION: Final = 3  # верных ответов на ступень (SRC-139)
QUIZ_MIN_GAP: Final = 2  # других вопросов между ответами по одной букве (SRC-140)
QUIZ_ERROR_SLOTS: Final = 4  # мест в раунде под ошибки
QUIZ_NEW_SLOTS: Final = 3  # мест в раунде под новые буквы
QUIZ_INTERVALS: Final[tuple[int, ...]] = (1, 3, 7)  # дней до следующего повторения (SRC-138)
QUIZ_RECENT: Final = 20  # по скольким последним ответам искать ошибки закрепления
QUIZ_SKIP_PAUSE_MIN: Final = 15  # «Не могу сейчас говорить/слушать» — минут без этой ступени
QUIZ_RULE: Final = "v2"  # версия правила отбора — пишется в каждую строку ``quiz_answers``
OPTIONS: Final = 4

# Буквы, которые путают (ADR-0066 п. 6, утверждено автором 2026-10-22): на вид и на слух для
# русскоязычных (SRC-034). ① — пары на слух; ② — и на вид, и на слух.
CONFUSABLE_SHAPE: Final[tuple[str, ...]] = (
    "بتثني", "جحخ", "دذ", "رز", "سش", "صض", "طظ", "عغ", "فق",
)  # fmt: skip
CONFUSABLE_SOUND: Final[tuple[str, ...]] = ("سصث", "تط", "دض", "ذزظ", "هحعء", "كق")

_HAMZA_FORMS: Final = "ءآأؤإئ"  # в фонемах Muaalem хамза — всегда «ء»


class QuizError(ValueError):
    """Недостаточно начатых букв для вопроса."""


class NothingToday(Exception):  # noqa: N818 — не ошибка, а ответ «на сегодня всё»
    """Все начатые буквы — ⭐ или ждут подтверждения, срок не наступил, ошибок нет."""


class Step(IntEnum):
    RECOGNIZE = 1  # слог → как читается (кириллица)
    HEAR = 2  # 🔊 слог → какой это слог (арабский)
    READ = 3  # прочитать строку буквы голосом


class PickReason(StrEnum):
    RETRY = "retry"  # ошибка этого раунда — через пару вопросов
    DUE = "due"  # срок повторения 1·3·7
    MISTAKE = "mistake"  # ошибка закрепления или чтения голосом
    NEW = "new"  # буква ещё на ступени ①
    OLD = "old"  # давно не спрашивали


@dataclass(frozen=True, slots=True)
class QuizOutcome:
    """Один отвеченный вопрос — в порядке ответов; ``day`` — местный день ученика."""

    letter_id: str
    step: int
    vowel: int
    correct: bool
    day: date
    reason: PickReason = PickReason.OLD


@dataclass(frozen=True, slots=True)
class LetterState:
    letter_id: str
    step: int = 1  # 1..3 — текущая ступень; 4 — все пройдены (⭐ уверенно)
    counted: int = 0  # засчитанных верных ответов на текущей ступени
    stage: int = 0  # ступень повторения 1..3; 0 — не в повторении
    due: date | None = None
    confirmed: bool = False  # после ③ буква вспомнилась верно в другой день

    @property
    def confident(self) -> bool:
        """⭐: пройдена ③ и подтверждена в другой день (автор 2026-10-23, SRC-138)."""
        return self.step > Step.READ and self.confirmed

    @property
    def resting(self) -> bool:
        """Прошла ③: до срока повторения в раунд не идёт (если нет ошибок)."""
        return self.step > Step.READ


@dataclass(frozen=True, slots=True)
class Pick:
    letter_id: str
    step: int
    vowel: int
    reason: PickReason


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    letter_id: str
    step: int
    vowel: int
    item_id: str  # слог (①②) или строка буквы (③)
    prompt: str  # арабский текст: слог или строка
    options: tuple[str, ...]  # ① — кириллица, ② — арабские слоги, ③ — пусто
    answer: int  # индекс верного варианта; ③ — -1

    @property
    def correct(self) -> str:
        """Верный вариант; на ступени ③ вариантов нет — пусто."""
        return self.options[self.answer] if self.options else ""


@dataclass(frozen=True, slots=True)
class QuizAnswer:
    """Строка ``quiz_answers``: пишется при показе, ответ дописывается один раз (ADR-0066 п. 7)."""

    id: UUID
    learner_id: UUID
    round_no: int
    position: int  # 1..QUIZ_ROUND
    step: int
    letter_id: str
    item_id: str
    vowel: int
    options: tuple[str, ...]
    answer: int
    shown_at: datetime
    curriculum_version: str
    rule: str
    picked: int | None = None
    correct: bool | None = None
    attempt_id: UUID | None = None
    answered_at: datetime | None = None
    reason: str = field(default="", compare=False)


@dataclass(frozen=True, slots=True)
class RoundSummary:
    correct: int
    total: int
    repeat: tuple[str, ...]  # буквы с ошибкой в раунде, по книге
    confident: int = 0
    letters: int = 0


# ---------- ступени и повторение ----------
def gap_for(letters: int) -> int:
    """Пауза между вопросами по одной букве: при двух начатых буквах (ر ز ر ز) больше одного
    вопроса не бывает — хватает одного (автор 2026-10-23), иначе ``QUIZ_MIN_GAP``."""
    return 1 if letters <= 2 else QUIZ_MIN_GAP


def letter_states(
    outcomes: Iterable[QuizOutcome],
    skip_hear: Collection[str] = (),
    min_gap: int = QUIZ_MIN_GAP,
) -> dict[str, LetterState]:
    """Ступень и срок каждой буквы по истории ответов. ``skip_hear`` — буквы без записей слогов:
    у них нет ступени ② (после ① сразу ③)."""
    states: dict[str, LetterState] = {}
    last: dict[str, tuple[int, date]] = {}
    top: dict[str, date] = {}  # день, когда буква прошла ③
    for k, o in enumerate(outcomes):
        s = states.get(o.letter_id) or LetterState(o.letter_id)
        step, counted, stage, due, confirmed = s.step, s.counted, s.stage, s.due, s.confirmed
        reached = top.get(o.letter_id)
        if o.correct and reached is not None and o.day > reached:
            confirmed = True
        prev = last.get(o.letter_id)
        spaced = prev is None or prev[1] != o.day or k - prev[0] - 1 >= min_gap
        stepped = False
        if o.correct and o.step == step <= Step.READ and spaced:
            counted += 1
            if counted >= QUIZ_CRITERION:
                step, counted, stepped = step + 1, 0, True
                if step == Step.HEAR and o.letter_id in skip_hear:
                    step = Step.READ
        stage, due = _reschedule(stage, due, o, step)
        if stepped:  # новая ступень — новое умение: 1·3·7 заново (ADR-0066, уточнения)
            stage, due = 1, o.day + timedelta(days=QUIZ_INTERVALS[0])
            if step > Step.READ:
                top[o.letter_id] = o.day
        states[o.letter_id] = LetterState(o.letter_id, step, counted, stage, due, confirmed)
        last[o.letter_id] = (k, o.day)
    return states


def _reschedule(stage: int, due: date | None, o: QuizOutcome, step: int) -> tuple[int, date | None]:
    """Повторение 1·3·7: ответ в срок — дальше, ошибка — снова через день (M-19)."""
    first = o.day + timedelta(days=QUIZ_INTERVALS[0])
    if stage:  # в повторении: срок двигает только ответ в срок или ошибка
        if not o.correct:
            return 1, first
        if due is not None and o.day >= due:
            if stage >= len(QUIZ_INTERVALS):
                return 0, None
            return stage + 1, o.day + timedelta(days=QUIZ_INTERVALS[stage])
        return stage, due
    if not o.correct and step > Step.RECOGNIZE:  # забыл уже поднятую букву
        return 1, first
    return stage, due


# ---------- следующий вопрос раунда ----------
def next_pick(
    curriculum: Curriculum,
    *,
    started: Sequence[str],
    history: Sequence[QuizOutcome],
    round_len: int,
    today: date,
    reading_errors: Mapping[str, int],
    has_audio: Callable[[str], bool] = lambda _: True,
    blocked_steps: Collection[int] = (),
) -> Pick:
    """Следующий вопрос: возврат ошибки раунда → к сроку → ошибки (≤ 4) → новое (≤ 3) → старое.

    ``history`` — все ответы ученика по порядку, последние ``round_len`` — этот раунд. Одна буква
    не идёт два вопроса подряд; буквы из последних ``QUIZ_MIN_GAP`` — только если других нет.
    ``NothingToday`` — все буквы отдыхают до срока, ошибок нет («на сегодня всё»).
    ``blocked_steps`` — ступени на паузе («Не могу сейчас говорить/слушать»): буква спрашивается
    ближайшей ступенью ниже; такой ответ её ступень не двигает (считаются ответы своей ступени).
    """
    book = _book_order(curriculum)
    letters = sorted({x for x in started if x in book}, key=book.__getitem__)
    if len(letters) < 2:
        raise QuizError("Нужно начать хотя бы две буквы")
    skip = without_hearing(curriculum, letters, has_audio)
    gap = gap_for(len(letters))
    states = letter_states(history, skip, gap)
    round_ = list(history[len(history) - round_len :]) if round_len else []
    groups = _groups(
        curriculum, letters, states, history=history, round_=round_, today=today,
        reading_errors=reading_errors, gap=gap,
    )  # fmt: skip
    recent = {o.letter_id for o in history[-gap:]}
    last = history[-1].letter_id if history else None
    for strictness in (2, 1, 0):  # пауза ≥ 2 → не подряд → хоть что-то (одна свободная буква)
        for reason, candidates in groups:
            for letter, step, vowel in candidates:
                if (strictness >= 1 and letter == last) or (strictness == 2 and letter in recent):
                    continue
                asked = _allowed_step(step, blocked_steps)
                chosen = (
                    vowel
                    if vowel >= 0 and asked == step
                    else _vowel(curriculum, letter, asked, history, has_audio)
                )
                return Pick(letter, asked, chosen, reason)
    raise NothingToday


Candidate = tuple[str, int, int]  # буква, ступень, огласовка (-1 — выбрать)


def _groups(
    curriculum: Curriculum,
    letters: Sequence[str],
    states: Mapping[str, LetterState],
    *,
    history: Sequence[QuizOutcome],
    round_: Sequence[QuizOutcome],
    today: date,
    reading_errors: Mapping[str, int],
    gap: int = QUIZ_MIN_GAP,
) -> list[tuple[PickReason, list[Candidate]]]:
    def step_of(x: str) -> int:
        return min(states[x].step, Step.READ) if x in states else Step.RECOGNIZE

    taken = Counter(o.reason for o in round_)
    retry: list[Candidate] = []
    for k, o in enumerate(round_):
        after = round_[k + 1 :]
        if (
            not o.correct
            and o.letter_id in letters
            and len(after) >= gap
            and all(a.letter_id != o.letter_id for a in after)
        ):
            retry.append((o.letter_id, o.step, o.vowel))
    book = _book_order(curriculum)
    due = sorted(
        (x for x in letters if x in states and states[x].due is not None),
        key=lambda x: (states[x].due, book[x]),
    )
    due_c: list[Candidate] = [
        (x, step_of(x), -1) for x in due if (d := states[x].due) is not None and d <= today
    ]
    mistakes: list[Candidate] = []
    if taken[PickReason.MISTAKE] < QUIZ_ERROR_SLOTS:
        mistakes = [
            (x, step_of(x), -1)
            for x in _mistake_letters(curriculum, letters, history, reading_errors)
        ]

    def free(x: str) -> bool:  # прошедшая ③ отдыхает до срока
        return x not in states or not states[x].resting

    new: list[Candidate] = []
    if taken[PickReason.NEW] < QUIZ_NEW_SLOTS:
        new = [(x, Step.RECOGNIZE, -1) for x in reversed(letters) if step_of(x) == Step.RECOGNIZE]
    asked = {o.letter_id: k for k, o in enumerate(history)}
    old = sorted(letters, key=lambda x: (asked.get(x, -1), book[x]))
    return [
        (PickReason.RETRY, retry),
        (PickReason.DUE, due_c),
        (PickReason.MISTAKE, mistakes),
        (PickReason.NEW, new),
        (PickReason.OLD, [(x, step_of(x), -1) for x in old if free(x)]),
    ]


def _mistake_letters(
    curriculum: Curriculum,
    letters: Sequence[str],
    history: Sequence[QuizOutcome],
    reading_errors: Mapping[str, int],
) -> list[str]:
    """Буквы, где последний ответ закрепления (из последних ``QUIZ_RECENT``) неверный, затем —
    буквы с ошибками чтения голосом, чаще — раньше."""
    found: list[str] = []
    recent = history[-QUIZ_RECENT:]
    for x in letters:
        mine = [o for o in recent if o.letter_id == x]
        if mine and not mine[-1].correct:
            found.append(x)
    by_char = {_letter_char(curriculum, x): x for x in letters}
    for char, n in sorted(reading_errors.items(), key=lambda kv: -kv[1]):
        hit = by_char.get(_norm(char))
        if n > 0 and hit is not None and hit not in found:
            found.append(hit)
    return found


def _allowed_step(step: int, blocked: Collection[int]) -> int:
    while step in blocked and step > Step.RECOGNIZE:
        step -= 1
    return step


def _vowel(
    curriculum: Curriculum,
    letter: str,
    step: int,
    history: Sequence[QuizOutcome],
    has_audio: Callable[[str], bool],
) -> int:
    """Огласовка, на которую на этой ступени отвечали реже всего (на ② — только с записью)."""
    vowels = [0, 1, 2]
    if step == Step.HEAR:
        syllables = _syllables(curriculum, letter)
        vowels = [v for v in vowels if v < len(syllables) and has_audio(syllables[v].id)] or vowels
    asked = Counter(o.vowel for o in history if o.letter_id == letter and o.step == step)
    return min(vowels, key=lambda v: (asked[v], v))


# ---------- вопрос ----------
def build_question(
    curriculum: Curriculum, pick: Pick, started: Sequence[str], shuffle: str = ""
) -> QuizQuestion:
    """Вопрос по выбору: ① варианты кириллицей, ② арабскими слогами, ③ строка буквы из книги.

    Отвлекающие (ADR-0058, ADR-0066): та же буква с другими огласовками, затем буквы — начатые
    раньше неначатых, похожие раньше непохожих, ближе по книге раньше дальних. Порядок вариантов
    перемешан, но детерминирован: тот же выбор и ``shuffle`` — тот же вопрос. Сценарий передаёт в
    ``shuffle`` раунд и место, чтобы верный ответ одного слога не стоял всегда на той же кнопке.
    """
    if pick.step == Step.READ:
        line = curriculum.item(pick.letter_id)
        return QuizQuestion(pick.letter_id, pick.step, pick.vowel, line.id, line.text, (), -1)
    syllable = _syllables(curriculum, pick.letter_id)[pick.vowel]

    def value(item: LessonItem) -> str:
        return item.sound if pick.step == Step.RECOGNIZE else item.text

    right = value(syllable)
    pool = [value(s) for s in _syllables(curriculum, pick.letter_id) if s.id != syllable.id]
    heads = list(_book_order(curriculum))
    at = heads.index(pick.letter_id)
    known = set(started)
    groups = (
        CONFUSABLE_SOUND if pick.step == Step.RECOGNIZE else CONFUSABLE_SHAPE + CONFUSABLE_SOUND
    )
    mine = _letter_char(curriculum, pick.letter_id)
    similar = {c for g in groups if mine in g for c in g}

    def rank(k: int) -> tuple[bool, bool, int, int]:
        x = heads[k]
        return x not in known, _letter_char(curriculum, x) not in similar, abs(k - at), k

    for k in sorted(range(len(heads)), key=rank):
        if heads[k] != pick.letter_id:
            others = _syllables(curriculum, heads[k])
            if pick.vowel < len(others):
                pool.append(value(others[pick.vowel]))
    options = [right]
    for v in pool:
        if v not in options:
            options.append(v)
        if len(options) == OPTIONS:
            break
    random.Random(f"{pick.letter_id}:{pick.step}:{pick.vowel}:{shuffle}").shuffle(options)  # noqa: S311
    return QuizQuestion(
        pick.letter_id, pick.step, pick.vowel, syllable.id, syllable.text,
        tuple(options), options.index(right),
    )  # fmt: skip


def read_passed(verdict: Verdict) -> bool:
    """Ступень ③ засчитана, если строка засчитана при чтении (M-01: вердикт не ``failed``)."""
    return verdict is not Verdict.FAILED


# ---------- итог и «ждут» ----------
def round_summary(round_: Sequence[QuizOutcome], states: Mapping[str, LetterState]) -> RoundSummary:
    wrong = sorted({o.letter_id for o in round_ if not o.correct})
    return RoundSummary(
        correct=sum(o.correct for o in round_),
        total=len(round_),
        repeat=tuple(wrong),  # id карточек идут по книге
        confident=sum(s.confident for s in states.values()),
        letters=len(states),
    )


def letters_waiting(
    curriculum: Curriculum,
    states: Mapping[str, LetterState],
    history: Sequence[QuizOutcome],
    *,
    started: Sequence[str],
    today: date,
    reading_errors: Mapping[str, int],
) -> int:
    """Сколько начатых букв ждут: к сроку повторения или с ошибкой (закрепления или чтения)."""
    letters = [x for x in started if x in _book_order(curriculum)]
    due = {x for x in letters if (d := states[x].due if x in states else None) and d <= today}
    mistakes = set(_mistake_letters(curriculum, letters, history, reading_errors))
    return len(due | mistakes)


def first_quiz_lesson(curriculum: Curriculum) -> Lesson | None:
    """Урок буквы, на котором закрепление откроется (если начаты все уроки букв до него)."""
    letters = [les for les in curriculum.lessons if les.section == "letter"]
    for k, lesson in enumerate(letters):
        if len(_heads(letters[: k + 1])) >= 2:  # то же условие, что в next_pick
            return lesson
    return None


# ---------- программа ----------
def letter_heads(lessons: Iterable[Lesson]) -> list[str]:
    """Буквы (id головных карточек) данных уроков — по книге."""
    return [i.id for i in _heads(lessons)]


def without_hearing(
    curriculum: Curriculum, letters: Iterable[str], has_audio: Callable[[str], bool]
) -> set[str]:
    """Буквы, у которых нет ни одной записи слога: ступени ② у них нет (ADR-0066 п. 2)."""
    return {x for x in letters if not any(has_audio(s.id) for s in _syllables(curriculum, x))}


def _heads(lessons: Iterable[Lesson]) -> list[LessonItem]:
    return [
        i
        for les in lessons
        if les.section == "letter"
        for i in les.items
        if i.kind is ItemKind.LETTER and i.sound
    ]


def _book_order(curriculum: Curriculum) -> dict[str, int]:
    return {item.id: n for n, item in enumerate(_heads(curriculum.lessons))}


def _syllables(curriculum: Curriculum, letter_id: str) -> list[LessonItem]:
    lesson, _ = curriculum.locate(letter_id)
    return [i for i in lesson.items if i.kind is ItemKind.SYLLABLE]


def _letter_char(curriculum: Curriculum, letter_id: str) -> str:
    """Буква урока одним символом (у хамзы — «ء», как в фонемах Muaalem)."""
    lesson, _ = curriculum.locate(letter_id)
    return _norm(min(lesson.accent)) if lesson.accent else ""


def _norm(char: str) -> str:
    return "ء" if char in _HAMZA_FORMS else char
