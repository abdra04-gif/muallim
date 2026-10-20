"""Закрепление: «как читается этот слог?» — выбор из четырёх ответов (ADR-0025).

Вопрос строится из карточек-букв пройденных уроков (буква с фатхой, кясрой, даммой). Он
детерминирован: по (item_id, vowel, seed) его можно восстановить из кнопки Telegram.
Активное припоминание с немедленной проверкой помогает закрепить связь буква–звук
(docs/pedagogy/learning-science.md).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem

OPTIONS = 4


class QuizError(ValueError):
    """Недостаточно пройденных букв для вопроса."""


@dataclass(frozen=True, slots=True)
class Question:
    item_id: str  # карточка-буква, из которой вопрос
    vowel: int  # 0 — фатха, 1 — кясра, 2 — дамма
    seed: int
    prompt: str  # слог арабскими буквами
    options: tuple[str, ...]  # варианты чтения кириллицей
    answer: int  # индекс верного варианта
    # начатые уроки букв на момент вопроса (битовая маска, ``started_mask``); -1 — все. Идёт в
    # кнопку, чтобы ответ показал те же варианты, даже если с тех пор начат новый урок (TD-FN-90)
    started: int = field(default=-1, compare=False)

    @property
    def correct(self) -> str:
        return self.options[self.answer]


def make_question(curriculum: Curriculum, lessons: Sequence[Lesson], seed: int) -> Question:
    """Вопрос по одной из букв данных (пройденных) уроков."""
    heads = _heads(lessons)
    if len(heads) < 2:
        raise QuizError("Нужно пройти хотя бы две буквы")
    rng = random.Random(seed)  # noqa: S311 — не криптография
    item = rng.choice(heads)
    return question_from(curriculum, item.id, rng.randrange(3), seed, lessons)


def first_quiz_lesson(curriculum: Curriculum) -> Lesson | None:
    """Урок буквы, на котором закрепление откроется (если начаты все уроки букв до него).

    Первый урок, начиная с которого ``make_question`` строит вопрос; без уроков букв — None.
    """
    letters = [les for les in curriculum.lessons if les.section == "letter"]
    for k, lesson in enumerate(letters):
        if len(_heads(letters[: k + 1])) >= 2:  # то же условие, что в make_question
            return lesson
    return None


def question_from(
    curriculum: Curriculum,
    item_id: str,
    vowel: int,
    seed: int,
    started: Sequence[Lesson] | None = None,
) -> Question:
    """Тот же вопрос по данным кнопки: варианты зависят от программы, seed и начатых уроков.

    Отвлекающие (решение автора 2026-10-20): та же буква с другими огласовками, затем буквы
    начатых уроков (``started``; None — все), ближайшие к букве вопроса по книге (при равенстве —
    более ранняя), и только если не хватает — остальные буквы так же по близости. Без случайности
    в выборе, поэтому вопрос восстанавливается и без ``started``, если ближайшие буквы начаты.
    """
    item = curriculum.item(item_id)
    rng = random.Random(seed * 31 + vowel)  # noqa: S311
    right = _sounds(item)[vowel]
    heads = _heads(curriculum.lessons)
    known = {h.id for h in _heads(started)} if started is not None else {h.id for h in heads}
    at = next((k for k, h in enumerate(heads) if h.id == item.id), 0)

    def rank(k: int) -> tuple[bool, int, int]:
        return heads[k].id not in known, abs(k - at), k

    others = [heads[k] for k in sorted(range(len(heads)), key=rank) if heads[k].id != item.id]
    pool = [s for s in _sounds(item) if s != right] + [_sounds(h)[vowel] for h in others]
    options = [right]
    for sound in pool:
        if sound not in options:
            options.append(sound)
        if len(options) == OPTIONS:
            break
    rng.shuffle(options)
    mask = started_mask(curriculum, started) if started is not None else -1
    return Question(
        item.id, vowel, seed, item.text.split()[vowel], tuple(options), options.index(right), mask
    )


def started_mask(curriculum: Curriculum, lessons: Sequence[Lesson]) -> int:
    """Начатые уроки букв одним числом: бит k — k-й урок буквы программы (для кнопки ≤ 64 байт)."""
    ids = {les.id for les in lessons}
    return sum(1 << k for k, les in enumerate(_letter_lessons(curriculum)) if les.id in ids)


def started_lessons(curriculum: Curriculum, mask: int) -> list[Lesson]:
    """Обратно к ``started_mask``: уроки букв, чьи биты стоят в маске."""
    return [les for k, les in enumerate(_letter_lessons(curriculum)) if mask >> k & 1]


def _letter_lessons(curriculum: Curriculum) -> list[Lesson]:
    return [les for les in curriculum.lessons if les.section == "letter"]


def _heads(lessons: Sequence[Lesson]) -> list[LessonItem]:
    return [
        i
        for les in lessons
        if les.section == "letter"
        for i in les.items
        if i.kind is ItemKind.LETTER and i.sound
    ]


def _sounds(item: LessonItem) -> list[str]:
    return item.sound.split(" · ")
