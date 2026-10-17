"""Закрепление: «как читается этот слог?» — выбор из четырёх ответов (ADR-0025).

Вопрос строится из карточек-букв пройденных уроков (буква с фатхой, кясрой, даммой). Он
детерминирован: по (item_id, vowel, seed) его можно восстановить из кнопки Telegram.
Активное припоминание с немедленной проверкой помогает закрепить связь буква–звук
(docs/pedagogy/learning-science.md).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass

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
    return question_from(curriculum, item.id, rng.randrange(3), seed)


def question_from(curriculum: Curriculum, item_id: str, vowel: int, seed: int) -> Question:
    """Тот же вопрос по данным кнопки: варианты зависят только от программы и seed."""
    item = curriculum.item(item_id)
    rng = random.Random(seed * 31 + vowel)  # noqa: S311
    right = _sounds(item)[vowel]
    others = [h for h in _heads(curriculum.lessons) if h.id != item.id]
    rng.shuffle(others)
    # отвлекающие: та же буква с другой огласовкой и другие буквы с той же огласовкой
    pool = [s for s in _sounds(item) if s != right] + [_sounds(h)[vowel] for h in others]
    options = [right]
    for sound in pool:
        if sound not in options:
            options.append(sound)
        if len(options) == OPTIONS:
            break
    rng.shuffle(options)
    return Question(
        item.id, vowel, seed, item.text.split()[vowel], tuple(options), options.index(right)
    )


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
