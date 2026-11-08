"""Учебная программа: уроки, карточки и ссылки на источник в книге.

Сам контент (буквы, подсказки, переводы) лежит в curriculum/*.yaml и меняется только человеком.
Каждая карточка хранит ``SourceRef`` — откуда она взята (книга, издание, страница, строка),
чтобы любую строку в боте можно было проследить до книги (NFR-TR-01).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from muallim.domain.arabic import HAMZA_FORMS


class ItemKind(StrEnum):
    LETTER = "letter"  # буква с огласовками — заголовок раздела книги
    SYLLABLE = "syllable"  # одна буква с одной огласовкой, отдельно (ADR-0032)
    WORD = "word"  # отдельное слово с переводом
    LINE = "line"  # печатная строка упражнения из книги (слоги и слова), как есть
    ALPHABET = "alphabet"  # строка таблицы алфавита (с. 10): знакомство, без проверки чтения
    RULE = "rule"  # правило своими словами перед разделом (name — заголовок, tip — объяснение)
    SAMPLE = "sample"  # образец написания без огласовок (с. 35, 37): только посмотреть


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Ссылка на источник. ``source_id`` — ключ из docs/research/sources.md (например SRC-001)."""

    source_id: str
    page: int | None = None
    line: int | None = None
    note: str = ""
    verified: bool = False  # сверено человеком с печатным изданием


# огласовки и танвин без сукуна: «مْ» само по себе не прочесть
_VOWEL_MARKS = frozenset("\u064b\u064c\u064d\u064e\u064f\u0650")


@dataclass(frozen=True, slots=True)
class LessonItem:
    id: str  # стабильный id, например "L01-05"; на него ссылаются попытки в БД
    text: str  # арабский текст с огласовками
    kind: ItemKind
    sound: str  # как читается (кириллицей); у строк из книги пусто — в книге транскрипции нет
    name: str = ""  # название буквы (для LETTER)
    tip: str = ""  # подсказка по произношению
    translation: str = ""  # перевод (для WORD)
    source: SourceRef | None = None
    note: str = ""  # пометка из книги, например «Обратите внимание: пары похожих слов»
    quran: str = ""  # «сура:аят», если строка из Корана: точный текст мусхафа и эталон чтения

    @property
    def is_practice(self) -> bool:
        """Карточку читают вслух и проверяют; таблицу алфавита — только смотрят."""
        return self.kind not in (ItemKind.ALPHABET, ItemKind.RULE, ItemKind.SAMPLE)

    @property
    def is_checkable(self) -> bool:
        """Голосовое проверяем: карточка чтения или правило, чей арабский текст огласован
        (автор 2026-11-08: прочитал правило — сразу проверь). В прогресс урока правило не входит."""
        if self.is_practice:
            return True
        words = [w for w in self.text.split() if any("\u0621" <= ch <= "\u064a" for ch in w)]
        return (
            self.kind is ItemKind.RULE
            and bool(words)
            and all(any(ch in _VOWEL_MARKS for ch in w) for w in words)
        )


@dataclass(frozen=True, slots=True)
class Lesson:
    id: str
    number: int
    title: str
    items: tuple[LessonItem, ...]
    source: SourceRef | None = None
    accent: frozenset[str] = frozenset()  # буквы урока — в книге выделены красным
    part: str = ""  # часть книги для меню, например «2. Буквы и огласовки»
    section: str = ""  # раздел книги: letter, madd, tashdid, … (см. оглавление книги)

    @property
    def practice_items(self) -> tuple[LessonItem, ...]:
        return tuple(item for item in self.items if item.is_practice)


@dataclass(frozen=True, slots=True)
class Lexicon:
    """Справочник для объяснения ошибок: названия звуков и подсказки по частым путаницам."""

    consonants: Mapping[str, tuple[str, str]]  # символ -> (название, транслитерация)
    vowels: Mapping[str, str]  # символ -> описание
    letter_tips: Mapping[str, str]  # согласная -> подсказка
    pair_tips: Mapping[frozenset[str], str]  # пара путаемых согласных -> подсказка
    transcription: Mapping[str, str] = field(default_factory=dict)  # фонема -> буквы языка ученика
    # значки через пробел -> пояснение
    transcription_legend: Mapping[str, str] = field(default_factory=dict)
    vowel_tips: Mapping[str, str] = field(default_factory=dict)  # гласный -> как держать рот
    # согласная -> (как сказать кириллицей, пометка): «ха» горлом / «ха» легко (FR-54)
    sounds: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    # согласная -> слоги (фатха, кясра, дамма) как в карточках курса: «со», «сы», «су»
    syllables: Mapping[str, tuple[str, str, str]] = field(default_factory=dict)
    missing: str = ""  # как назвать пропущенный звук в разборе («пропущено»)


@dataclass(frozen=True, slots=True)
class Page:
    """Страница книги — урок для ученика (автор 2026-11-08): карточки в порядке страницы.

    ``lessons`` — разделы программы, чьи карточки стоят на странице (прогресс и закрепление
    считаются по ним, как раньше). Страница только с правилом (с. 46, 50, 69) — без карточек."""

    number: int
    items: tuple[LessonItem, ...]
    lessons: tuple["Lesson", ...]


_TITLE_NUMBER = re.compile(r"^\d+\.\s*")
_TITLE_PART = re.compile(r"\s*\(\d+/\d+\)$")


def unit_title(lesson: "Lesson") -> str:
    """Название раздела без номера урока и «(1/4)»: «4. ر · Ра» → «ر · Ра»."""
    return _TITLE_PART.sub("", _TITLE_NUMBER.sub("", lesson.title))


def page_title(page: Page) -> str:
    """Что на странице: буквы — «ر ز م», иначе разделы через запятую."""
    if page.lessons and all(les.section == "letter" for les in page.lessons):
        return " ".join(unit_title(les).split(" · ")[0] for les in page.lessons)
    names = list(dict.fromkeys(unit_title(les) for les in page.lessons))
    return ", ".join(names)


@dataclass(frozen=True, slots=True)
class Curriculum:
    id: str
    version: str  # меняется при любой правке контента; пишется в каждую попытку
    title: str
    lessons: tuple[Lesson, ...]
    lexicon: Lexicon
    _items: dict[str, tuple[Lesson, int]] = field(init=False, repr=False, compare=False)
    _order: tuple[LessonItem, ...] = field(init=False, repr=False, compare=False)
    _pages: tuple[Page, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        index: dict[str, tuple[Lesson, int]] = {}
        for lesson in self.lessons:
            for i, item in enumerate(lesson.items):
                if item.id in index:
                    raise ValueError(f"Повторяющийся id карточки: {item.id}")
                index[item.id] = (lesson, i)
        object.__setattr__(self, "_items", index)
        object.__setattr__(self, "_order", tuple(i for les in self.lessons for i in les.items))
        object.__setattr__(self, "_pages", _build_pages(self.lessons, self._order))

    def pages(self) -> tuple[Page, ...]:
        """Страницы книги подряд, от первой до последней; страница без карточек — пустая."""
        return self._pages

    def page(self, number: int) -> Page:
        for page in self._pages:
            if page.number == number:
                return page
        raise KeyError(number)

    def page_of(self, item_id: str) -> tuple[Page, int]:
        """Страница карточки и её номер на странице (с 0)."""
        item = self.item(item_id)
        for page in self._pages:
            if item in page.items:
                return page, page.items.index(item)
        raise KeyError(item_id)

    def lesson(self, lesson_id: str) -> Lesson:
        for lesson in self.lessons:
            if lesson.id == lesson_id:
                return lesson
        raise KeyError(lesson_id)

    def item(self, item_id: str) -> LessonItem:
        lesson, i = self._items[item_id]
        return lesson.items[i]

    def locate(self, item_id: str) -> tuple[Lesson, int]:
        """Урок и порядковый номер карточки в нём."""
        return self._items[item_id]

    def first_item(self) -> LessonItem:
        return self.lessons[0].items[0]

    def parts(self) -> list[tuple[str, list[Lesson]]]:
        """Уроки, сгруппированные по частям книги, в её порядке."""
        out: list[tuple[str, list[Lesson]]] = []
        for lesson in self.lessons:
            if not out or out[-1][0] != lesson.part:
                out.append((lesson.part, []))
            out[-1][1].append(lesson)
        return out

    def next_item(self, item_id: str) -> LessonItem | None:
        """Следующая карточка в порядке книги; на последней карточке урока — первая следующего."""
        return self._step(item_id, 1)

    def previous_item(self, item_id: str) -> LessonItem | None:
        return self._step(item_id, -1)

    def next_lesson(self, lesson_id: str) -> Lesson | None:
        ids = [lesson.id for lesson in self.lessons]
        n = ids.index(lesson_id) + 1
        return self.lessons[n] if n < len(self.lessons) else None

    def previous_lesson(self, lesson_id: str) -> Lesson | None:
        ids = [lesson.id for lesson in self.lessons]
        n = ids.index(lesson_id) - 1
        return self.lessons[n] if n >= 0 else None

    def _step(self, item_id: str, step: int) -> LessonItem | None:
        n = self._order.index(self.item(item_id)) + step
        return self._order[n] if 0 <= n < len(self._order) else None


def letters_before(curriculum: Curriculum, lesson_id: str) -> tuple[LessonItem, ...]:
    """Буквы, пройденные по книге строго до урока (ADR-0062 п. 7): головные карточки ``LETTER``
    уроков букв (``section == "letter"``) в порядке книги; своя буква урока не входит."""
    curriculum.lesson(lesson_id)  # неизвестный урок — KeyError, как у остальных поисков
    out: list[LessonItem] = []
    for lesson in curriculum.lessons:
        if lesson.id == lesson_id:
            break
        if lesson.section == "letter":
            out.extend(i for i in lesson.items if i.kind is ItemKind.LETTER)
    return tuple(out)


def lesson_letter(lesson: Lesson) -> str | None:
    """Буква урока буквы (``section == "letter"``): первая буква головной карточки, опоры хамзы —
    ء (с. 10 книги). У уроков не про букву (мадд, ташдид…) — None. Одна функция для сценария и
    экрана (FR-54)."""
    if lesson.section != "letter":
        return None
    head = next((i.text[0] for i in lesson.items if i.kind is ItemKind.LETTER and i.text), "")
    if not head:
        return None
    return "ء" if head in HAMZA_FORMS else head


def _build_pages(lessons: tuple["Lesson", ...], order: tuple[LessonItem, ...]) -> tuple[Page, ...]:
    """Карточки по страницам книги (``source.page``); без страницы — на странице предыдущей."""
    owner = {item.id: les for les in lessons for item in les.items}
    by_page: dict[int, list[LessonItem]] = {}
    current: int | None = None
    for item in order:
        if item.source is not None and item.source.page is not None:
            current = item.source.page
        if current is not None:
            by_page.setdefault(current, []).append(item)
    if not by_page:
        return ()
    out = []
    for number in range(min(by_page), max(by_page) + 1):
        items = tuple(by_page.get(number, ()))
        units = tuple(dict.fromkeys(owner[i.id] for i in items))
        out.append(Page(number, items, units))
    return tuple(out)
