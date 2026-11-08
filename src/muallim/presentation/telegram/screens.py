"""Экраны бота: картинка + подпись + кнопки (ADR-0024). Без обращений к Telegram API.

Один экран — одно сообщение, которое меняется на месте (Display.show): чат не растёт и не
уезжает вниз. На каждом экране, кроме главного, есть кнопка 🏠.
"""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from html import escape
from typing import Final

from aiogram.enums import ButtonStyle
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from muallim.application.breakdown import VOWEL_KINDS, Breakdown, ErrorGroup, Place
from muallim.application.ports.reading import AyahSyllables
from muallim.application.ports.storage import ArticulationVideoLibrary
from muallim.application.transcription import as_text, plain
from muallim.application.use_cases.progress import LessonStatus, Progress
from muallim.application.use_cases.quiz import QuizOverview, QuizRest, QuizResult, QuizView
from muallim.application.use_cases.reading import CardReading
from muallim.application.use_cases.recitation import RecitationResult
from muallim.application.use_cases.sura import SuraReadingResult
from muallim.domain import arabic
from muallim.domain.assessment import ErrorKind
from muallim.domain.curriculum import (
    Curriculum,
    ItemKind,
    Lesson,
    LessonItem,
    Page,
    lesson_letter,
    letters_before,
    page_title,
    unit_title,
)
from muallim.domain.learner import Question
from muallim.domain.phonetics import Zone, articulation_zone
from muallim.domain.policy import Verdict
from muallim.domain.quiz import QUIZ_ROUND, RoundSummary, Step, first_quiz_lesson
from muallim.domain.settings import (
    ASK_OFFSET_HOURS,
    REMINDER_HOURS,
    HowToRead,
    LearnerSettings,
    local_minute,
)
from muallim.domain.sura import AyahOutcome, Sura, SuraMode, find_sura, suras
from muallim.domain.syllables import ayah_number
from muallim.presentation.telegram import keyboards, render, texts
from muallim.presentation.telegram import views as views  # noqa: PLC0414  (screens.views — для тестов)
from muallim.presentation.telegram.callbacks import (
    BookPage,
    ChangeSetting,
    Consent,
    Deep,
    DeleteData,
    Dispute,
    GoItem,
    Help,
    Home,
    Lessons,
    LettersSheet,
    Listen,
    More,
    Noop,
    Opening,
    PageOpen,
    Privacy,
    Quiz,
    QuizAnswer,
    QuizSkip,
    RecordReference,
    ShareLesson,
    ShowProgress,
    ShowSettings,
    Signs,
    SuraErrors,
    SuraList,
    SuraOpen,
    SuraReady,
    Watch,
)
from muallim.presentation.telegram.opening import OPENING_ITEMS

LESSONS_PER_PAGE = 10
CAPTION_LIMIT = 1024  # подпись к фото в Telegram
_ICON: Final = {LessonStatus.DONE: "✅", LessonStatus.STARTED: "🟡", LessonStatus.NEW: "⚪"}
_VERDICT: Final = {
    Verdict.EXCELLENT: texts.VERDICT_EXCELLENT,
    Verdict.PASSED: texts.VERDICT_PASSED,
    Verdict.FAILED: texts.VERDICT_FAILED,
}


@dataclass(frozen=True, slots=True)
class Screen:
    caption: str
    keyboard: InlineKeyboardMarkup
    image: bytes | None = None  # PNG; None — текстовый экран (нет libraqm или картинка не нужна)
    image_key: str = ""  # одинаковый ключ — та же картинка: Telegram file_id переиспользуется
    # Второе сообщение под картинкой (с кнопками): подпись к фото — не больше 1024 символов,
    # а подробный разбор ошибок длиннее (FR-43). Пусто — экран одним сообщением.
    details: str = ""


CAPTION_LIMIT = 1024  # Telegram: подпись к фото


# ---------- общие части ----------
def _home_row(kb: InlineKeyboardBuilder, *extra: tuple[str, object]) -> None:
    for text, data in extra:
        kb.button(text=text, callback_data=data)  # type: ignore[arg-type]
    kb.button(text=texts.HOME_BUTTON, callback_data=Home())


def _letter_of(lesson: Lesson) -> str:
    """Буква урока (одна функция домена, FR-54); не урок буквы — пусто."""
    return lesson_letter(lesson) or ""


def _letter_shown(lesson: Lesson) -> str:
    """Буква урока для ученика: у первого урока — элиф с хэмзэ «أ», как на с. 10 книги."""
    letter = _letter_of(lesson)
    return "أ" if letter == "ء" else letter


def _alphabet_map(curriculum: Curriculum, progress: Progress) -> tuple[bytes | None, str]:
    """Карта букв по таблице книги (урок 1), раскрашенная по статусу уроков букв."""
    if not render.available():
        return None, ""
    table = [
        i for les in curriculum.lessons if les.section == "alphabet" for i in les.items
        if i.kind is ItemKind.ALPHABET
    ]  # fmt: skip
    by_letter = {
        _letter_of(lp.lesson): lp for lp in progress.lessons if lp.lesson.section == "letter"
    }
    current = curriculum.locate(progress.continue_item.id)[0].id if progress.continue_item else ""
    rows, key = [], []
    for item in table:
        row = []
        for letter in item.text.split():
            lp = by_letter.get("ء" if letter == "ا" else letter)
            if lp is None:
                mark = render.Mark.NEW
            elif lp.lesson.id == current:
                mark = render.Mark.CURRENT
            else:
                mark = {
                    LessonStatus.DONE: render.Mark.DONE,
                    LessonStatus.STARTED: render.Mark.STARTED,
                    LessonStatus.NEW: render.Mark.NEW,
                }[lp.status]
            row.append((letter, mark))
            key.append(mark.value[0])
        rows.append(row)
    return render.alphabet(rows), "map:" + "".join(key)


# ---------- главная ----------
_PROFILE_TEXTS: Final = {
    Question.NAME: texts.PROFILE_NAME,
    Question.AGE: texts.PROFILE_AGE,
    Question.GENDER: texts.PROFILE_GENDER,
    Question.NATIVE: texts.PROFILE_NATIVE,
    Question.READING: texts.PROFILE_READING,
    Question.PRAYER: texts.PROFILE_PRAYER,
}


def profile_question(question: Question) -> Screen:
    """Один экран анкеты (FR-65); имя из Telegram предлагается кнопкой только на первом."""
    return Screen(_PROFILE_TEXTS[question], keyboards.profile_question(question))


def home(curriculum: Curriculum, progress: Progress, quiz_waiting: int = 0) -> Screen:
    item = progress.continue_item or curriculum.first_item()
    lesson, _ = curriculum.locate(item.id)
    fresh = progress.attempts_total == 0 and item == curriculum.first_item()
    counted = [pg for pg in curriculum.pages() if any(les.practice_items for les in pg.lessons)]
    caption = texts.HOME.format(
        streak=_days(progress.streak_days),
        done=sum(_page_icon(progress, pg) == "✅" for pg in counted),
        total=len(counted),
        next_title=escape(where(curriculum, item)),
    )
    kb = InlineKeyboardBuilder()
    label = (
        texts.START_BUTTON if fresh else texts.CONTINUE_BUTTON.format(title=where(curriculum, item))
    )
    kb.button(text=label, callback_data=GoItem(item_id=item.id))
    kb.button(text=texts.LESSONS_BUTTON, callback_data=_lessons_of(curriculum, lesson))
    quiz_label = (
        texts.QUIZ_BUTTON_WAITING.format(n=quiz_waiting) if quiz_waiting else texts.QUIZ_BUTTON
    )
    kb.button(text=quiz_label, callback_data=Quiz())
    kb.button(text=texts.MORE_BUTTON, callback_data=More())  # ADR-0082
    kb.adjust(1, 2, 1)
    image, key = _alphabet_map(curriculum, progress)
    return Screen(caption, kb.as_markup(), image, key)


def where(curriculum: Curriculum, item: LessonItem) -> str:
    """Где ученик: «Стр. 11 · ر · Ра» — страница книги и раздел."""
    page, _ = curriculum.page_of(item.id)
    unit = unit_title(curriculum.locate(item.id)[0])
    return texts.CARD_PLACE.format(page=page.number, unit=unit)


def voice_on_home(curriculum: Curriculum, progress: Progress) -> Screen:
    """Голосовое, когда урок не открыт: попытку не пишем, кнопка — на карточку курсора."""
    item = progress.continue_item or curriculum.first_item()
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.CONTINUE_BUTTON.format(title=where(curriculum, item)),
        callback_data=GoItem(item_id=item.id),
    )
    return Screen(texts.VOICE_ON_HOME, kb.as_markup())


def _days(n: int) -> str:
    return f"{n} {views.plural(n, texts.DAY_FORMS)}" if n else texts.STREAK_ZERO


# ---------- уроки: части книги → уроки части ----------
def lessons(curriculum: Curriculum, progress: Progress, part: int | None, page: int = 0) -> Screen:
    """part=None/-1 — список частей книги; part=k — уроки k-й части по страницам."""
    parts = curriculum.parts()
    image, key = _alphabet_map(curriculum, progress)
    kb = InlineKeyboardBuilder()
    if part is None or part < 0 or part >= len(parts):
        for k, (name, items) in enumerate(parts):
            # как на главной и в прогрессе: считаются уроки с чтением вслух (FR-49)
            counted = [les for les in items if les.practice_items]
            done = sum(1 for les in counted if progress.of(les.id).status is LessonStatus.DONE)
            full = bool(counted) and done == len(counted)
            icon = "✅" if full else "🟡" if _started(progress, items) else "⚪"
            kb.button(text=f"{icon} {name} · {done}/{len(counted)}", callback_data=Lessons(part=k))
        _home_row(kb)
        kb.adjust(1)
        return Screen(texts.PARTS, kb.as_markup(), image, key)

    name, _ = parts[part]
    chunk_all = _pages_of_part(curriculum, part)
    pages = max(1, -(-len(chunk_all) // LESSONS_PER_PAGE))
    page = min(max(page, 0), pages - 1)
    chunk = chunk_all[page * LESSONS_PER_PAGE : (page + 1) * LESSONS_PER_PAGE]
    current = (
        curriculum.page_of(progress.continue_item.id)[0].number if progress.continue_item else 0
    )
    for pg in chunk:
        icon = _page_icon(progress, pg) + ("👉" if pg.number == current else "")
        title = page_title(pg) or texts.PAGE_RULE_TITLE
        kb.button(
            text=texts.PAGE_BUTTON.format(icon=icon, page=pg.number, title=title)[:60],
            callback_data=PageOpen(n=pg.number),
        )
    nav = 0
    if page > 0:
        kb.button(text="◀️", callback_data=Lessons(part=part, page=page - 1))
        nav += 1
    if pages > 1:
        kb.button(text=f"{page + 1}/{pages}", callback_data=Noop())
        nav += 1
    if page < pages - 1:
        kb.button(text="▶️", callback_data=Lessons(part=part, page=page + 1))
        nav += 1
    kb.button(text=texts.PARTS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb)
    kb.adjust(*([1] * len(chunk)), *([nav] if nav else []), 2)
    caption = texts.LESSONS.format(part=escape(name), page=page + 1, pages=pages)
    return Screen(caption, kb.as_markup(), image, key)


def _started(progress: Progress, lessons_: list[Lesson]) -> bool:
    return any(progress.of(les.id).status is not LessonStatus.NEW for les in lessons_)


# ---------- карточка ----------
def card(
    curriculum: Curriculum,
    item: LessonItem,
    has_audio: bool,
    is_teacher: bool,
    reading: CardReading | None = None,  # не используется: транскрипция — plain на картинке
    *,
    view: LearnerSettings | None = None,
    videos: ArticulationVideoLibrary | None = None,
    syllables: AyahSyllables | None = None,
    sura_errors: int | None = None,
) -> Screen:
    """``sura_errors`` — аят из списка ошибок суры: «📋 К ошибкам суры» (автор 2026-11-08).

    ``view`` — настройки ученика: «Как читается» и крупный шрифт (FR-51).

    ``videos`` — ролики «🎬 Как произносить» (FR-56, ADR-0074): есть ролик для текста карточки —
    кнопка ролика вместо 🔊 (решение автора: где есть ролик — только ролик).
    ``syllables`` — аяты по слогам (FR-61, ADR-0077): аят урока «Суры» рисуется клетками-слогами."""
    view = view or LearnerSettings()
    lesson, i = curriculum.locate(item.id)
    page, k = curriculum.page_of(item.id)
    place = texts.CARD_PLACE.format(page=page.number, unit=unit_title(lesson))
    parts = [texts.CARD_HEAD.format(lesson=escape(place), n=k + 1, total=len(page.items))]
    known = letters_before(curriculum, lesson.id)
    if i == 0 and lesson.section == "letter":
        parts.append(_new_letter(curriculum, lesson, known))
    # простой кириллицей по словам, как в разборе (audience.md: значков х̣ с̣ новичок не читает)
    shown = (
        " ".join(plain(word, curriculum.lexicon) for word in item.text.split())
        if item.is_checkable and view.how_to_read is not HowToRead.HIDDEN
        else ""
    )
    image = _card_image(lesson, item, (k, len(page.items)), view.large_font, syllables, shown=shown)
    if image is None:
        parts.append(f"<b>{escape(item.text)}</b>")
    if item.kind is ItemKind.RULE:  # первый абзац; целиком — в «📖 Подробнее»
        first, *rest = item.tip.split("\n", maxsplit=1)
        parts.append(texts.CARD_RULE.format(title=escape(item.name), body=escape(first)))
        parts += [texts.CARD_RULE_MORE] * bool(rest)
        parts += [texts.CARD_READ] * item.is_checkable  # прочитал правило — сразу проверь
    elif item.kind is ItemKind.SAMPLE:
        parts.append(texts.CARD_SAMPLE)
    elif item.kind is ItemKind.ALPHABET:
        names = "\n".join(  # LRM: строка слева направо, буква не уезжает вправо (bidi)
            f"\u200e{letter} — {escape(name)}"
            for letter, name in zip(item.text.split(), item.name.split(" · "), strict=False)
        )
        parts.append(texts.CARD_ALPHABET.format(names=names))
    else:
        if item.kind in (ItemKind.LETTER, ItemKind.SYLLABLE):
            info = (
                texts.CARD_SYLLABLE_INFO
                if item.kind is ItemKind.SYLLABLE
                else texts.CARD_LETTER_INFO
            )
            parts.append(info.format(name=escape(item.name), sound=escape(item.sound)))
        if item.note and not item.note.startswith(("фраза", "сура", "басмала", "слог")):
            parts.append(texts.CARD_NOTE.format(note=escape(item.note)))
        parts.append(
            texts.CARD_READ_SYLLABLE if item.kind is ItemKind.SYLLABLE else texts.CARD_READ
        )
    if item.quran:  # подсказка, «Как читается» и книга — в «📖 Углублённо» (ADR-0082)
        parts.append("<i>" + texts.CARD_QURAN.format(ref=item.quran) + "</i>")

    video = card_video(videos, item)
    kb = _card_keyboard(curriculum, item, has_audio, is_teacher, video=video)
    if sura_errors is not None:
        kb = _with_sura_errors(kb, sura_errors)
    key = f"card:{item.id}:{curriculum.version}" + (":large" if view.large_font else "")
    key += ":r" if shown else ""
    return Screen("\n\n".join(parts), kb, image, key)


def _with_sura_errors(kb: InlineKeyboardMarkup, sura: int) -> InlineKeyboardMarkup:
    """Первым рядом — «📋 К ошибкам суры»: разобрал аят — назад к списку."""
    back = InlineKeyboardButton(
        text=texts.SURA_ERRORS_BUTTON, callback_data=SuraErrors(n=sura).pack()
    )
    return InlineKeyboardMarkup(inline_keyboard=[[back], *kb.inline_keyboard])


def card_video(videos: ArticulationVideoLibrary | None, item: LessonItem) -> str | None:
    """Ключ ролика «🎬 Как произносить» для текста карточки (ADR-0074); None — ролика нет."""
    return videos.for_text(item.text) if videos is not None else None


def _card_keyboard(
    curriculum: Curriculum,
    item: LessonItem,
    has_audio: bool,
    is_teacher: bool,
    *,
    video: str | None = None,
) -> InlineKeyboardMarkup:
    """Кнопки карточки (ADR-0082): «🔊 или 🎬» + «📖 Углублённо», навигация с 🏠.

    ``video`` — ключ ролика «🎬» рядом с 🔊 (FR-56, ADR-0074)."""
    lesson, _ = curriculum.locate(item.id)
    kb = InlineKeyboardBuilder()
    if has_audio:  # 🔊 и 🎬 — оба, если есть (автор 2026-11-08: везде одинаково)
        kb.button(text=texts.LISTEN_BUTTON, callback_data=Listen(item_id=item.id))
    if video is not None:
        kb.button(
            text=texts.VIDEO_BUTTON, callback_data=Watch(v=video, src="card", item_id=item.id)
        )
    kb.button(text=texts.DEEP_BUTTON, callback_data=Deep(item_id=item.id))
    rows: list[int] = [1 + has_audio + (video is not None)]
    if is_teacher and item.kind is not ItemKind.ALPHABET:  # учитель озвучивает и правило
        kb.button(text=texts.RECORD_BUTTON, callback_data=RecordReference(item_id=item.id))
        rows.append(1)
    sura = find_sura(curriculum, lesson.id) if lesson.section == "sura" else None
    if sura is not None:  # сура целиком и наизусть (FR-57, FR-59)
        kb.button(text=texts.WHOLE_SURA_BUTTON, callback_data=SuraOpen(n=sura.number, m="t"))
        kb.button(text=texts.MEMORY_BUTTON, callback_data=SuraOpen(n=sura.number, m="m"))
        rows.append(2)
    rows += _nav(kb, curriculum, item)
    kb.adjust(*rows)
    return kb.as_markup()


def deep(
    curriculum: Curriculum,
    item: LessonItem,
    reading: CardReading | None = None,
    *,
    view: LearnerSettings | None = None,
    video_url: str | None = None,
    book_page: bool = False,
) -> Screen:
    """``book_page`` — есть картинка страницы книги: кнопка «📄 Страница книги».

    «📖 Подробнее» (ADR-0082): подсказка, «Как читается» (по настройке), страница книги,
    видеоурок (URL-кнопка), шпаргалка букв; «◀️ К уроку» — на карточку. Текст без картинки."""
    view = view or LearnerSettings()
    lesson, _ = curriculum.locate(item.id)
    parts = [texts.DEEP_HEAD.format(lesson=escape(lesson.title))]
    if item.tip:
        parts.append(texts.DEEP_TIP.format(tip=escape(item.tip)))
    if reading is not None and reading.reading and view.how_to_read is not HowToRead.HIDDEN:
        legend = "".join(f"\n<i>{escape(line)}</i>" for line in reading.legend)
        line = (
            texts.CARD_HOW_TO_READ_SHOWN
            if view.how_to_read is HowToRead.SHOWN
            else texts.CARD_HOW_TO_READ
        )
        parts.append(line.format(reading=escape(as_text(reading.reading)), legend=legend))
    if item.source is not None and item.source.page is not None:
        parts.append("<i>" + texts.CARD_BOOK.format(page=item.source.page) + "</i>")
    kb = InlineKeyboardBuilder()
    page = item.source.page if item.source is not None else None
    if book_page and page is not None:
        kb.button(text=texts.BOOK_PAGE_BUTTON, callback_data=BookPage(page=page, item_id=item.id))
    if video_url:
        kb.button(text=texts.DEEP_VIDEO_BUTTON, url=video_url)
    if letters_before(curriculum, lesson.id):  # шпаргалка букв, пройденных до урока (FR-52)
        kb.button(
            text=texts.SHEET_BUTTON,
            callback_data=LettersSheet(lesson_id=lesson.id, item_id=item.id),
        )
    kb.button(text=texts.DEEP_BACK_BUTTON, callback_data=GoItem(item_id=item.id))
    kb.button(text=texts.HOME_BUTTON, callback_data=Home())
    kb.adjust(*[1] * (len(list(kb.buttons)) - 2), 2)  # «◀️ К уроку · 🏠» — последним рядом
    return Screen("\n\n".join(parts), kb.as_markup())


def book_page(item: LessonItem, page: int, image: bytes) -> Screen:
    """Картинка страницы книги; «◀️ К уроку» — на ту же карточку."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.DEEP_BACK_BUTTON, callback_data=GoItem(item_id=item.id))
    kb.button(text=texts.HOME_BUTTON, callback_data=Home())
    kb.adjust(2)
    return Screen(texts.BOOK_PAGE_CAPTION.format(page=page), kb.as_markup(), image)


def more() -> Screen:
    """«⋯ Ещё» (ADR-0082): то, что ушло с главной."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.PROGRESS_BUTTON, callback_data=ShowProgress())
    kb.button(text=texts.SIGNS_BUTTON, callback_data=Signs())
    kb.button(text=texts.MEMORY_BUTTON, callback_data=SuraList())  # FR-59
    kb.button(text=texts.SETTINGS_BUTTON, callback_data=ShowSettings())  # FR-51
    kb.button(text=texts.HELP_BUTTON, callback_data=Help())
    _home_row(kb)
    kb.adjust(2, 2, 1, 1)
    return Screen(texts.MORE_TITLE, kb.as_markup())


def _new_letter(curriculum: Curriculum, lesson: Lesson, known: Sequence[LessonItem]) -> str:
    """«Новая буква: X · уже знаешь: …» на первом шаге урока буквы (ADR-0062 п. 7)."""
    head = next((it for it in lesson.items if it.kind is ItemKind.LETTER), None)
    line = texts.NEW_LETTER.format(
        letter=_letter_shown(lesson), name=escape(head.name if head else "")
    )
    if known:
        letters = " ".join(_letter_shown(curriculum.locate(it.id)[0]) for it in known)
        line += "\n" + texts.ALREADY_KNOW.format(letters=letters)
    return line


_WHOLE_PICTURE = (ItemKind.LETTER, ItemKind.ALPHABET)  # своя картинка: формы буквы, таблица


def _card_image(
    lesson: Lesson,
    item: LessonItem,
    position: tuple[int, int],
    large: bool = False,
    syllables: AyahSyllables | None = None,
    *,
    shown: str = "",
) -> bytes | None:
    """``large`` — «Крупный шрифт»: крупнее строка карточки и правила (ADR-0061).

    Аят урока «Суры» с разбором на слоги — клетками-слогами (ADR-0077); остальные строки — тоже
    клетками с подписью, если транскрипция не выключена; иначе — строка целиком."""
    if not render.available():
        return None
    scale = render.LARGE_SCALE if large else 1.0
    cells = syllables.for_text(item.text) if syllables is not None else None
    ayah = lesson.section == "sura" and bool(item.quran)
    # под каждым слогом — как он читается (автор 2026-11-08), буква урока красная; аят суры —
    # клетками всегда (ADR-0077), остальное — если транскрипция не выключена
    if cells is not None and (ayah or (shown and item.kind not in _WHOLE_PICTURE)):
        number = ayah_number(lesson, item) if ayah else None  # номер в кружке — только в сурах
        return render.ayah(cells, number, position, scale, () if ayah else lesson.accent)
    if item.kind is ItemKind.ALPHABET:
        return render.letters(item.text)
    if item.kind in (ItemKind.RULE, ItemKind.SAMPLE):
        return render.rule(item.text, scale, shown)
    if item.kind is ItemKind.LETTER and (letter := _letter_shown(lesson)):
        zone = articulation_zone(letter)
        zones = [(texts.ZONES[z.value], z is zone) for z in Zone] if zone else []
        return render.letter_forms(letter, item.text, texts.LETTER_FORMS, zones)
    return render.card(item.text, lesson.accent, position, scale, shown)


def _nav(kb: InlineKeyboardBuilder, curriculum: Curriculum, item: LessonItem) -> list[int]:
    """Один ряд «◀️ Назад · 🏠 · ▶️ Дальше» на любом шаге (автор 2026-11-08): назад и вперёд
    переходят и через границу урока, коротко, без названия урока; счёт шагов — в заголовке."""
    previous = curriculum.previous_item(item.id)
    following = curriculum.next_item(item.id)
    if previous is not None:
        kb.button(text=texts.BACK_BUTTON, callback_data=GoItem(item_id=previous.id))
    kb.button(text=texts.HOME_BUTTON, callback_data=Home())
    if following is not None:
        kb.button(text=texts.NEXT_BUTTON, callback_data=_forward(curriculum, item, following))
    return [1 + (previous is not None) + (following is not None)]


def _forward(curriculum: Curriculum, item: LessonItem, following: LessonItem) -> CallbackData:
    """«▶️ Дальше»: на той же странице — следующий шаг; на новой — её начало со сканом."""
    here, _ = curriculum.page_of(item.id)
    there, _ = curriculum.page_of(following.id)
    if there.number == here.number:
        return GoItem(item_id=following.id)
    return PageOpen(n=here.number + 1)


def learner_part(curriculum: Curriculum, progress: Progress) -> Lessons:
    """«Уроки» с главной и /lessons — страница части, где занимается ученик (ADR-0082)."""
    item = progress.continue_item or curriculum.first_item()
    return _lessons_of(curriculum, curriculum.locate(item.id)[0])


def _lessons_of(curriculum: Curriculum, lesson: Lesson) -> Lessons:
    """Кнопка «Уроки» — сразу на экран части, где страница с началом раздела."""
    number = curriculum.page_of(lesson.items[0].id)[0].number
    for k in range(len(curriculum.parts())):
        found = [pg.number for pg in _pages_of_part(curriculum, k)]
        if number in found:
            return Lessons(part=k, page=found.index(number) // LESSONS_PER_PAGE)
    return Lessons(part=-1)


def _pages_of_part(curriculum: Curriculum, part: int) -> list[Page]:
    """Страницы части книги: по первому разделу страницы; пустая — с предыдущей."""
    names = [name for name, _ in curriculum.parts()]
    out: list[Page] = []
    owner = names[0] if names else ""
    for pg in curriculum.pages():
        if pg.lessons:
            owner = pg.lessons[0].part
        if 0 <= part < len(names) and owner == names[part]:
            out.append(pg)
    return out


def _page_icon(progress: Progress, page: Page) -> str:
    statuses = [
        lp for lp in progress.lessons if lp.lesson in page.lessons and lp.lesson.practice_items
    ]
    if statuses and all(lp.status is LessonStatus.DONE for lp in statuses):
        return "✅"
    if any(lp.status is not LessonStatus.NEW for lp in statuses):
        return "🟡"
    return "⚪"


def page_intro(curriculum: Curriculum, page: Page, image: bytes | None) -> Screen:
    """Начало урока-страницы: скан (всегда, автор 2026-11-08), что на ней, «▶️ Начать»."""
    pages = curriculum.pages()
    n = pages.index(page) + 1
    title = page_title(page)
    lines = [texts.PAGE_HEAD.format(n=n, page=page.number, title=escape(title))]
    lines.append(texts.PAGE_STEPS.format(n=len(page.items)) if page.items else texts.PAGE_RULE_ONLY)
    kb = InlineKeyboardBuilder()
    if page.items:
        kb.button(text=texts.PAGE_START, callback_data=GoItem(item_id=page.items[0].id))
    back = n > 1
    if back:
        kb.button(text=texts.BACK_BUTTON, callback_data=PageOpen(n=page.number - 1))
    kb.button(text=texts.HOME_BUTTON, callback_data=Home())
    ahead = n < len(pages)
    if ahead:
        kb.button(text=texts.NEXT_BUTTON, callback_data=PageOpen(n=page.number + 1))
    kb.adjust(*((1,) if page.items else ()), 1 + back + ahead)
    return Screen("\n\n".join(lines), kb.as_markup(), image, f"page:{page.number}")


# ---------- результат ----------
def result(
    curriculum: Curriculum,
    r: RecitationResult,
    has_audio: bool,
    resume: LessonItem | None = None,
    staff: bool = False,
    *,
    sura_errors: int | None = None,
    videos: ArticulationVideoLibrary | None = None,
) -> Screen:
    """Итог попытки. ``resume`` — идёт начало занятия: после басмалы — «Продолжить занятие».

    Разбор группами (FR-54, ADR-0070): в тексте — не больше ``views.MAX_ERRORS_SHOWN`` пунктов
    (буква урока первой), остальные — на картинке; без картинки — все пункты текстом. Не влезает в
    подпись — хвост уходит вторым сообщением, ничего не обрезая. Разбор строит сценарий; нет его
    (``breakdown is None``) — экран без разбора.

    «Услышано» видят только учитель и разметчик; блока «Для исследования» нет (автор 2026-11-08)
    (``staff``): новичку они мешают, номер попытки ученик получает в «🚩 Бот ошибся» (FR-50).

    ``videos`` — ролики (FR-56, ADR-0074): ролик карточки вместо 🔊; к ошибкам разбора роликов нет.
    """
    a = r.attempt.assessment
    lesson, _ = curriculum.locate(r.item.id)
    breakdown = r.breakdown or Breakdown((), 0, 0)
    groups = breakdown.groups
    unread = _unread_line(curriculum, r.item.text, breakdown)
    counter = ""
    if breakdown.words_total > 1 and breakdown.words_ok and (groups or breakdown.unread):
        words = views.plural(breakdown.words_ok, texts.WORD_FORMS)
        counter = texts.RESULT_WORDS.format(
            ok=breakdown.words_ok, words=words, total=breakdown.words_total
        )
    image = None
    if render.available() and r.lesson_completed and not a.errors:  # с ошибками — сначала разбор
        image = _postcard_image(lesson)
    elif render.available():
        image = render.result_marks(text=r.item.text, breakdown=breakdown, score_label=counter)
    blocks = ["\n".join(x for x in (_VERDICT[r.verdict], counter) if x)]  # «Верно 2 слова из 5»
    other = r.attempt.policy.is_other_line(a)  # совпало очень мало — разбор всё равно ниже
    blocks += [texts.RESULT_OTHER_LINE] * other
    if image is None:
        blocks.append(f"<b>{escape(r.item.text)}</b>")
    blocks += _progress(r)
    if r.lesson_completed:
        blocks.append(texts.LESSON_DONE.format(lesson=escape(lesson.title)))
    if r.next_item is None:
        blocks.append(texts.LAST_ITEM)
    if staff and not r.feedback:
        blocks.append(escape(texts.HEARD_LINE.format(text=r.heard_transcription)))
    shown = len(groups) if image is None else views.MAX_ERRORS_SHOWN
    blocks += [_group_point(curriculum, n, g) for n, g in enumerate(groups[:shown])]
    if image is not None:  # «ещё K — на картинке» — только те, кто правда в легенде (Н1)
        legend = min(len(groups), render.LEGEND_MAX_ROWS)
        if (on_image := legend - shown) > 0:
            blocks.append(texts.MORE_ON_IMAGE.format(n=on_image))
        if (hidden := len(groups) - max(legend, shown)) > 0:
            blocks.append(texts.MORE_NOT_SHOWN.format(n=hidden))
    blocks.append(unread)
    after = card_video(videos, r.item)
    listen = has_audio  # 🔊 есть и рядом с роликом (автор 2026-11-08)
    if groups or unread:
        blocks.append(texts.PLAN_LISTEN if listen else texts.PLAN_READ)
    caption, details = _split_caption([b for b in blocks if b])
    keyboard = _result_keyboard(
        curriculum, r, lesson, has_audio, resume, after=after, sura_errors=sura_errors
    )
    return Screen(caption, keyboard, image, details=details)


_WORDS_SHOWN: Final = 3  # слов в пункте; дальше — texts.WORDS_MORE
_UNDER: Final = frozenset("ٍِ")  # кясра и танвин кясра — под буквой
_MADD_POINTS: Final = {
    ErrorKind.MADD_TOO_SHORT: texts.POINT_MADD_SHORT,
    ErrorKind.MADD_TOO_LONG: texts.POINT_MADD_LONG,
}


def _letter_head(curriculum: Curriculum, letter: str, *, lesson_letter: bool = False) -> str:
    name = curriculum.lexicon.consonants.get(arabic.phoneme_of(letter), ("", ""))[0] or letter
    template = texts.HEAD_LESSON_LETTER if lesson_letter else texts.HEAD_LETTER
    return template.format(letter=letter, name=name)


def _group_text(curriculum: Curriculum, g: ErrorGroup) -> str:
    """Первая строка пункта — по-русски (Р6): «Буква урока ح (Хэ): нужно …, у тебя …»."""
    need, heard = escape(g.need_label), escape(g.heard_label)
    if g.kind is ErrorKind.EXTRA_SOUND:
        return texts.POINT_EXTRA.format(heard=heard)
    if g.kind in _MADD_POINTS:
        head = _letter_head(curriculum, g.carrier) if g.carrier else texts.HEAD_LONG
        return _MADD_POINTS[g.kind].format(head=head, need=need, heard=heard)
    if g.kind in VOWEL_KINDS:
        sign = g.expected or g.heard
        name = curriculum.lexicon.vowels.get(sign, sign).split(" (", maxsplit=1)[0]
        if not g.carrier:
            head = texts.HEAD_SIGN.format(vowel_name=name)
        else:
            under = sign in _UNDER
            template = texts.HEAD_SIGN_UNDER if under else texts.HEAD_SIGN_OVER
            head = template.format(letter=g.carrier, vowel_name=name)
        return texts.POINT.format(head=head, need=need, heard=heard)
    head = (
        _letter_head(curriculum, g.letter, lesson_letter=g.lesson_letter)
        if g.letter
        else texts.HEAD_SOUND
    )
    template = texts.POINT_SHADDA if g.kind is ErrorKind.SHADDA_MISSING else texts.POINT
    return template.format(head=head, need=need, heard=heard)


def _group_point(curriculum: Curriculum, n: int, g: ErrorGroup) -> str:
    """Пункт разбора (вид одобрен автором 2026-10-23/24, Р6):
    «1️⃣ Буква урока ح (Хэ): нужно «ха» горлом, у тебя «ха» легко (2 раза)»
    «В словах: مُحْسِنُ «мух-си-ну» · مِنْحَرُ «мин-ха-ру»»."""
    numbers = texts.ERROR_NUMBERS
    number = numbers[n] if n < len(numbers) else f"{n + 1}."
    line = " ".join(x for x in (number, _group_text(curriculum, g), views.times(g.times)) if x)
    places = list({p.word_index: p for p in g.places if p.word_text}.values())
    if not places:
        return line
    shown = _words(places[:_WORDS_SHOWN])
    if len(places) > _WORDS_SHOWN:
        shown += texts.WORDS_MORE
    template = texts.WORDS_ONE if len(places) == 1 else texts.WORDS_MANY
    return f"{line}\n{template.format(words=shown)}"


def _words(places: Sequence[Place]) -> str:
    return texts.WORDS_SEPARATOR.join(
        texts.POINT_WORD.format(word=escape(p.word_text), reading=escape(p.word_reading))
        for p in places
    )


def _unread_line(curriculum: Curriculum, text: str, breakdown: Breakdown) -> str:
    """«⏹ Запись закончилась на слове …» — первое не дочитанное слово с простым чтением."""
    words = text.split()
    if not breakdown.unread or breakdown.unread[0] >= len(words):
        return ""
    word = words[breakdown.unread[0]]
    reading = plain(word, curriculum.lexicon)
    return texts.RESULT_UNREAD.format(
        word=texts.POINT_WORD.format(word=escape(word), reading=escape(reading))
    )


def _split_caption(blocks: Sequence[str]) -> tuple[str, str]:
    """Подпись к фото — не больше ``CAPTION_LIMIT``: блоки по порядку, пока влезают; остальное
    — вторым сообщением целиком (ничего не теряется)."""
    caption: list[str] = []
    for k, block in enumerate(blocks):
        if len("\n\n".join([*caption, block])) > CAPTION_LIMIT and caption:
            return "\n\n".join(caption), "\n\n".join(blocks[k:])
        caption.append(block)
    return "\n\n".join(caption), ""


def _progress(r: RecitationResult) -> list[str]:
    """«Было → стало» (только если балл изменился, FR-50) и что исправлено — подписями групп."""
    if r.previous_score is None:
        return []
    now = r.attempt.assessment.score
    lines = []
    if now != r.previous_score:
        trend = texts.TREND_UP if now > r.previous_score else texts.TREND_DOWN
        lines.append(texts.RESULT_PROGRESS.format(trend=trend, before=r.previous_score, now=now))
    if r.fixed:
        lines.append(texts.RESULT_FIXED.format(sounds=", ".join(escape(s) for s in r.fixed)))
    return ["\n".join(lines)] if lines else []


def _result_keyboard(
    curriculum: Curriculum,
    r: RecitationResult,
    lesson: Lesson,
    has_audio: bool,
    resume: LessonItem | None = None,
    *,
    after: str | None = None,
    sura_errors: int | None = None,
) -> InlineKeyboardMarkup:
    """``after`` — ролик карточки (вместо 🔊). Роликов к ошибкам разбора нет: ролики — только
    на карточках алфавита (решение автора 2026-10-25, ADR-0074)."""
    kb = InlineKeyboardBuilder()
    item_id = r.item.id
    top = 0  # 🔊, 🎬 и при ошибках «📖 Подробнее» — один ряд (ADR-0082)
    if has_audio:
        kb.button(text=texts.LISTEN_BUTTON, callback_data=Listen(item_id=item_id))
        top += 1
    if after is not None:
        kb.button(
            text=texts.VIDEO_BUTTON, callback_data=Watch(v=after, src="after", item_id=item_id)
        )
        top += 1
    if r.attempt.assessment.errors:
        kb.button(text=texts.DEEP_BUTTON, callback_data=Deep(item_id=item_id))
        top += 1
    # «◀️ Назад · 🏠 · ▶️ Дальше» — как на карточке (автор 2026-11-08: 🏠 по центру)
    nav = 1
    if previous := curriculum.previous_item(item_id):
        kb.button(text=texts.BACK_BUTTON, callback_data=GoItem(item_id=previous.id))
        nav += 1
    kb.button(text=texts.HOME_BUTTON, callback_data=Home())
    if resume is None and r.next_item is not None:
        forward = _forward(curriculum, r.item, r.next_item)
        kb.button(text=texts.NEXT_BUTTON, callback_data=forward)
        nav += 1
    if resume is not None:  # начало занятия прочитано — туда, где ученик остановился
        title = curriculum.locate(resume.id)[0].title
        kb.button(
            text=texts.RESUME_BUTTON.format(title=title), callback_data=GoItem(item_id=resume.id)
        )
    kb.button(text=texts.AGAIN_BUTTON, callback_data=GoItem(item_id=item_id))
    kb.button(text=texts.DISPUTE_BUTTON, callback_data=Dispute(attempt=r.attempt.id.hex))
    if r.lesson_completed:
        kb.button(text=texts.SHARE_BUTTON, callback_data=ShareLesson(lesson=lesson.id))
    rows: Sequence[int] = (
        *((top,) if top else ()),
        nav,
        *((1,) if resume is not None else ()),
        2,
        *((1,) if r.lesson_completed else ()),
    )
    kb.adjust(*rows)
    markup = kb.as_markup()
    return markup if sura_errors is None else _with_sura_errors(markup, sura_errors)


# ---------- прогресс, помощь, данные ----------
def progress(curriculum: Curriculum, p: Progress, quiz: QuizOverview | None = None) -> Screen:
    lines = [
        texts.PROGRESS_HEAD.format(
            done=p.done_lessons,
            total=p.practice_lessons,
            streak=_days(p.streak_days),
            attempts=p.attempts_total,
        )
    ]
    if quiz is not None and quiz.letters:  # ⭐ по буквам — сразу под шапкой (ADR-0066)
        lines.append(texts.QUIZ_CONFIDENT.format(n=quiz.confident, total=quiz.letters) + "\n")
    shown = [lp for lp in p.lessons if lp.total and lp.status is not LessonStatus.NEW]
    for lp in shown:
        line = (
            f"{_ICON[lp.status]} {escape(lp.lesson.title)} "
            f"{views.bar(lp.percent)} {lp.mastered}/{lp.total}"
        )
        if lp.weak:
            line += "\n    " + texts.PROGRESS_REPEAT.format(
                items=", ".join(
                    texts.PROGRESS_ITEM.format(n=lp.lesson.items.index(i) + 1) for i in lp.weak[:5]
                )
            )
        lines.append(line)
    if not shown:
        lines.append(texts.PROGRESS_NOTHING)
    kb = InlineKeyboardBuilder()
    item = p.continue_item or curriculum.first_item()
    kb.button(
        text=texts.CONTINUE_BUTTON.format(title=where(curriculum, item)),
        callback_data=GoItem(item_id=item.id),
    )
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb, (texts.BACK_TO_MORE, More()))  # открыт из «⋯ Ещё» — туда и назад
    kb.adjust(1, 3)
    image, key = _book_progress(curriculum, p)
    return Screen("\n".join(lines)[:1000], kb.as_markup(), image, key)


def _book_progress(curriculum: Curriculum, p: Progress) -> tuple[bytes | None, str]:
    """Вся книга по частям и неделя занятий (ADR-0050); карта алфавита осталась на главной."""
    if not render.available():
        return None, ""
    parts = []
    for name, lessons_ in curriculum.parts():
        counted = [p.of(les.id) for les in lessons_ if les.practice_items]
        done = sum(1 for lp in counted if lp.status is LessonStatus.DONE)
        parts.append((plain_title(name), done, len(counted)))
    week = p.week
    labels: tuple[str, ...] = ()
    if week and p.today is not None:
        start = p.today.weekday() - len(week) + 1
        labels = tuple(texts.WEEKDAYS[(start + k) % 7] for k in range(len(week)))
    image = render.book_progress(parts, week if labels else (), labels)
    key = (
        "book:"
        + ",".join(f"{d}" for _, d, _ in parts)
        + ":"
        + "".join("1" if x else "0" for x in week)
    )
    return image, key


# ---------- открытка «урок пройден» и начало занятия (ADR-0050) ----------
_ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f]+")


def plain_title(title: str) -> str:
    """Название без арабских букв — для картинок (в PT Sans нет арабского).

    «6. م · Мим» → «6. Мим».
    """
    clean = _ARABIC.sub("", title)
    clean = re.sub(r"\s+([:,.])", r"\1", clean)
    clean = re.sub(r"(\.)\s*·\s*", r"\1 ", clean)
    clean = re.sub(r"\s*·\s*(·\s*)+", " · ", clean)
    return re.sub(r"\s{2,}", " ", clean).strip(" ·")


def _postcard_image(lesson: Lesson, p: Progress | None = None) -> bytes:
    letter = _letter_shown(lesson) if lesson.section == "letter" else ""
    page = lesson.source.page if lesson.source is not None else None
    subtitle = texts.POSTCARD_SUBTITLE.format(lesson=plain_title(lesson.title), page=page or "—")
    streak = texts.POSTCARD_STREAK.format(days=_days(p.streak_days)) if p and p.streak_days else ""
    return render.postcard(
        letter or str(lesson.number), texts.POSTCARD_TITLE, subtitle, p.week if p else (), streak
    )


def postcard(curriculum: Curriculum, lesson: Lesson, p: Progress, bot_username: str) -> Screen:
    """Открытка для пересылки: картинка и приглашение в бот, без имени и псевдонима."""
    caption = texts.SHARE_CAPTION.format(lesson=escape(plain_title(lesson.title)), bot=bot_username)
    kb = InlineKeyboardBuilder()
    image = _postcard_image(lesson, p) if render.available() else None
    return Screen(caption, kb.as_markup(), image)


def opening(curriculum: Curriculum) -> Screen:
    lines = [curriculum.item(i).text for i in OPENING_ITEMS]
    caption = f"{texts.OPENING_TITLE}\n\n{texts.OPENING_TEXT}"
    image = render.opening(lines) if render.available() else None
    if image is None:
        caption += "\n\n" + "\n".join(f"<b>{escape(line)}</b>" for line in lines)
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.OPENING_START, callback_data=Opening(act="start"))
    kb.button(text=texts.OPENING_SKIP, callback_data=Opening(act="skip"))
    kb.adjust(1, 1)
    return Screen(caption, kb.as_markup(), image, f"opening:{curriculum.version}")


def _clock(minute: int) -> str:
    """Минута суток → «7:00», «19:05»."""
    return f"{minute // 60}:{minute % 60:02d}"


def _back_to_settings(kb: InlineKeyboardBuilder) -> None:
    kb.button(text=texts.BACK_TO_SETTINGS, callback_data=ShowSettings())


def settings(s: LearnerSettings) -> Screen:
    """⚙️ Настройки (FR-51): одно окно, нажатие ставит значение и перерисовывает экран."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.SETTING_HOW_TO_READ, callback_data=ShowSettings(page="hint"))
    for option in HowToRead:
        label = texts.HOW_TO_READ_OPTIONS[option.value]
        chosen = option is s.how_to_read
        kb.button(
            text=texts.SETTING_CHOSEN.format(label=label) if chosen else label,
            callback_data=ChangeSetting(name="how_to_read", value=option.value),
        )
    toggles = (
        ("daily_opening", texts.SETTING_DAILY_OPENING, s.daily_opening),
        ("large_font", texts.SETTING_LARGE_FONT, s.large_font),
    )
    for name, label, on in toggles:
        kb.button(
            text=(texts.SETTING_ON if on else texts.SETTING_OFF).format(label=label),
            callback_data=ChangeSetting(name=name, value=str(not on).lower()),
        )
    reminder = (
        texts.SETTING_REMINDER_OFF
        if s.reminder_minute is None
        else texts.SETTING_REMINDER_AT.format(time=_clock(s.reminder_minute))
    )
    kb.button(text=reminder, callback_data=ShowSettings(page="reminder"))
    kb.button(text=texts.PRIVACY_BUTTON, callback_data=Privacy())  # «Мой ID» — внутри (ADR-0082)
    _home_row(kb, (texts.BACK_TO_MORE, More()))
    kb.adjust(1, 3, 1, 1, 1, 1, 2)
    return Screen(texts.SETTINGS, kb.as_markup())


def reminder_hours(s: LearnerSettings) -> Screen:
    """🔔 Во сколько напоминать: целые часы местного времени (ADR-0061, В2)."""
    kb = InlineKeyboardBuilder()
    for hour in REMINDER_HOURS:
        kb.button(
            text=_clock(hour * 60),
            callback_data=ChangeSetting(name="reminder_minute", value=str(hour * 60)),
        )
    rows = [4] * (len(REMINDER_HOURS) // 4)
    if s.reminder_minute is not None:
        kb.button(
            text=texts.REMINDER_OFF_BUTTON,
            callback_data=ChangeSetting(name="reminder_minute", value="off"),
        )
        rows.append(1)
    _back_to_settings(kb)
    kb.adjust(*rows, 1)
    return Screen(texts.REMINDER_HOURS, kb.as_markup())


def reminder_ask_time(now: datetime) -> Screen:
    """«Который у тебя час?» — кнопка с текущим временем для каждого смещения (ADR-0061, В3)."""
    kb = InlineKeyboardBuilder()
    for hours in ASK_OFFSET_HOURS:
        kb.button(
            text=_clock(local_minute(now, hours * 60)),
            callback_data=ChangeSetting(name="utc_offset_min", value=str(hours * 60)),
        )
    _back_to_settings(kb)
    kb.adjust(3, 3, 3, 2, 1)
    return Screen(texts.REMINDER_ASK_TIME, kb.as_markup())


def reminder(curriculum: Curriculum, progress: Progress) -> Screen:
    """Напоминание о занятии: кнопка — на карточку, где ученик остановился."""
    item = progress.continue_item or curriculum.first_item()
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.CONTINUE_BUTTON.format(title=where(curriculum, item)),
        callback_data=GoItem(item_id=item.id),
    )
    return Screen(texts.REMINDER, kb.as_markup())


def me(pseudonym: str) -> Screen:
    """«🪪 Мой ID» на месте экрана настроек (TD-FN-93 п. 4)."""
    kb = InlineKeyboardBuilder()
    _back_to_settings(kb)
    _home_row(kb)
    kb.adjust(2)
    return Screen(views.me(pseudonym), kb.as_markup())


def help_screen() -> Screen:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb, (texts.BACK_TO_MORE, More()))
    kb.adjust(1, 2)
    return Screen(texts.HELP, kb.as_markup())


def privacy(research_consent: bool, pseudonym: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    if research_consent:
        kb.button(
            text=texts.PRIVACY_DENY_BUTTON, callback_data=Consent(granted=False, then="privacy")
        )
    else:
        kb.button(
            text=texts.PRIVACY_ALLOW_BUTTON, callback_data=Consent(granted=True, then="privacy")
        )
    kb.button(
        text=texts.PRIVACY_DELETE_BUTTON,
        callback_data=DeleteData(confirmed=False),
        style=ButtonStyle.DANGER,
    )
    _back_to_settings(kb)
    _home_row(kb)
    kb.adjust(1, 1, 2)
    return Screen(views.privacy(research_consent, pseudonym), kb.as_markup())


# ---------- знаки, шпаргалка букв и закрепление ----------
def signs(curriculum: Curriculum | None = None, progress: Progress | None = None) -> Screen:
    """Что значат значки над буквой и под ней — по номерам на картинке.

    С программой и прогрессом — ещё кнопка шпаргалки букв до урока, где ученик остановился
    (FR-52); без них — как раньше.
    """
    kb = InlineKeyboardBuilder()
    sheet = False
    if curriculum is not None and progress is not None:
        item = progress.continue_item or curriculum.first_item()
        lesson = curriculum.locate(item.id)[0]
        if sheet := bool(letters_before(curriculum, lesson.id)):
            kb.button(text=texts.SHEET_BUTTON, callback_data=LettersSheet(lesson_id=lesson.id))
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb, (texts.BACK_TO_MORE, More()))
    kb.adjust(*((1,) if sheet else ()), 3)
    image = render.signs() if render.available() else None
    return Screen(texts.SIGNS, kb.as_markup(), image, "signs:v1")


SHEET_LISTEN_PER_ROW = 4


def letters_sheet(
    curriculum: Curriculum,
    lesson_id: str,
    audio: Collection[str],
    back_item: str = "",
    *,
    videos: ArticulationVideoLibrary | None = None,
) -> Screen:
    """Шпаргалка «буква → название → звук → 🔊» по книге строго до урока (FR-52, ADR-0062 п. 7).

    ``audio`` — id головных карточек, у которых есть эталон: 🔊 — существующий ``Listen``.
    ``back_item`` — карточка, с которой открыли («◀️ Назад» на неё); пусто — назад на «Знаки».
    ``videos`` — не используется: роликов в шпаргалке нет (решение автора 2026-10-25, ADR-0074).
    """
    known = letters_before(curriculum, lesson_id)
    lines = []
    kb = InlineKeyboardBuilder()
    listen = 0
    for head in known:
        letter = _letter_shown(curriculum.locate(head.id)[0])
        lines.append(
            texts.SHEET_LINE.format(letter=letter, name=escape(head.name), sound=escape(head.sound))
        )
        if head.id in audio:
            kb.button(text=f"🔊 {letter}", callback_data=Listen(item_id=head.id))
            listen += 1
    back = GoItem(item_id=back_item) if back_item else Signs()
    kb.button(text=texts.BACK_BUTTON, callback_data=back)
    _home_row(kb)
    full, rest = divmod(listen, SHEET_LISTEN_PER_ROW)
    kb.adjust(*([SHEET_LISTEN_PER_ROW] * full), *((rest,) if rest else ()), 2)
    caption = texts.LETTERS_SHEET + "\n" + "\n".join(lines)
    return Screen(caption, kb.as_markup())


def quiz(view: QuizView) -> Screen:
    """Вопрос закрепления (ADR-0066): ① картинка слога и варианты кириллицей; ② 🔊 и арабские
    слоги, сам слог не показан; ③ строка буквы — прочитать голосом."""
    q = view.question
    header = texts.QUIZ_HEADER.format(
        position=view.position, total=QUIZ_ROUND, correct=view.correct_so_far
    )
    kb = InlineKeyboardBuilder()
    if q.step == Step.HEAR:
        kb.button(text=texts.QUIZ_LISTEN, callback_data=Listen(item_id=q.item_id))
    for k, option in enumerate(q.options):
        kb.button(text=option, callback_data=QuizAnswer(a=view.answer_id.hex, p=k))
    skip = {Step.HEAR: texts.QUIZ_CANT_LISTEN, Step.READ: texts.QUIZ_CANT_SPEAK}.get(Step(q.step))
    if skip:  # как в Duolingo: пропустить без ошибки, ступень — на паузе (ADR-0066)
        kb.button(text=skip, callback_data=QuizSkip(a=view.answer_id.hex))
    _home_row(kb)
    if q.step == Step.HEAR:
        kb.adjust(1, 2, 2, 1, 1)
        return Screen(f"{header}\n\n{texts.QUIZ_HEAR_ASK}", kb.as_markup())
    ask = texts.QUIZ_ASK if q.step == Step.RECOGNIZE else texts.QUIZ_READ_ASK
    kb.adjust(*((2, 2) if q.options else ()), *((1,) if skip else ()), 1)
    image = render.card(q.prompt, set(), (0, 1)) if render.available() else None
    body = ask if image else f"<b>{escape(q.prompt)}</b>\n\n{ask}"
    return Screen(f"{header}\n\n{body}", kb.as_markup(), image, f"quiz:{q.item_id}")


def quiz_right(result: QuizResult) -> InlineKeyboardMarkup:
    """Верный ответ на миг: выбранный вариант — «✅» зелёным, нажать ничего нельзя; потом
    обработчик сам показывает следующий вопрос (автор 2026-11-08)."""
    q = result.view.question
    kb = InlineKeyboardBuilder()
    for k, option in enumerate(q.options):
        right = k == q.answer
        kb.button(
            text=f"✅ {option}" if right else option,
            callback_data=Noop(),
            style=ButtonStyle.SUCCESS if right else None,
        )
    kb.adjust(2)
    return kb.as_markup()


def quiz_answer(result: QuizResult) -> Screen:
    """Разбор неверного ответа (верный — сразу следующий вопрос): верный вариант — зелёный,
    выбранный — красный (ADR-0043); 🔊 и «▶️ Дальше». Нажать варианты снова нельзя (Noop);
    подпись главнее цвета для старых клиентов."""
    q = result.view.question
    picked = result.picked if result.picked is not None else -1
    right = q.options[q.answer] if q.options else ""
    shown = q.options[picked] if 0 <= picked < len(q.options) else ""
    template = texts.QUIZ_WRONG_HEAR if q.step == Step.HEAR else texts.QUIZ_WRONG
    caption = template.format(prompt=escape(q.prompt), answer=escape(right), picked=escape(shown))
    kb = InlineKeyboardBuilder()
    for k, option in enumerate(q.options):
        style = (
            ButtonStyle.SUCCESS if k == q.answer else ButtonStyle.DANGER if k == picked else None
        )
        kb.button(text=option, callback_data=Noop(), style=style)
    kb.button(text=texts.QUIZ_LISTEN, callback_data=Listen(item_id=q.item_id))
    if not result.finished:  # после 10-го — итог отдельным сообщением ниже
        kb.button(text=texts.QUIZ_NEXT, callback_data=Quiz(), style=ButtonStyle.PRIMARY)
    _home_row(kb)
    kb.adjust(*((2, 2) if q.options else ()), 1, 1, 1)
    image = None
    if q.step == Step.RECOGNIZE and render.available():
        image = render.card(q.prompt, set(), (0, 1))
    return Screen(caption, kb.as_markup(), image, f"quiz:{q.item_id}" if image else "")


def quiz_summary(curriculum: Curriculum, summary: RoundSummary) -> Screen:
    """Итог раунда: счёт, буквы с ошибками (🔊 каждой), сколько букв уже «⭐ уверенно»."""
    lines = [texts.QUIZ_SUMMARY.format(correct=summary.correct, total=summary.total)]
    kb = InlineKeyboardBuilder()
    repeat = [x for x in summary.repeat if _in_program(curriculum, x)]
    if repeat:
        letters = [_letter_shown(curriculum.locate(x)[0]) for x in repeat]
        lines.append(texts.QUIZ_SUMMARY_REPEAT.format(letters=" ".join(letters)))
        for x, letter in zip(repeat, letters, strict=True):
            kb.button(text=f"🔊 {letter}", callback_data=Listen(item_id=x))
    else:
        lines.append(texts.QUIZ_SUMMARY_ALL)
    if summary.letters:
        lines.append(texts.QUIZ_CONFIDENT.format(n=summary.confident, total=summary.letters))
    kb.button(text=texts.QUIZ_AGAIN, callback_data=Quiz(), style=ButtonStyle.PRIMARY)
    _home_row(kb)
    full, rest = divmod(len(repeat), SHEET_LISTEN_PER_ROW)
    kb.adjust(*([SHEET_LISTEN_PER_ROW] * full), *((rest,) if rest else ()), 1, 1)
    return Screen("\n\n".join(lines), kb.as_markup())


def quiz_rest(rest: QuizRest) -> Screen:
    """«На сегодня всё»: буквы ждут срока повторения (ADR-0066) — вместо однообразных кругов."""
    lines = [texts.QUIZ_REST]
    if rest.letters:
        lines.append(texts.QUIZ_CONFIDENT.format(n=rest.confident, total=rest.letters))
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb)
    kb.adjust(2)
    return Screen("\n\n".join(lines), kb.as_markup())


def _in_program(curriculum: Curriculum, item_id: str) -> bool:
    try:
        curriculum.item(item_id)
    except KeyError:  # карточку убрали при пересборке книги
        return False
    return True


def with_quiz_next(screen: Screen) -> Screen:
    """Разбор голосового на ступени ③: вместо кнопок урока («▶️ Дальше», «◀️ Назад», «🔁 Ещё
    раз» увели бы из раунда) — «🧠 Дальше по закреплению»; 🔊 эталона (и 🎬 ролики, ADR-0074) и
    «🚩 Бот ошибся» остаются."""
    keep = (Listen.__prefix__ + ":", Watch.__prefix__ + ":", Dispute.__prefix__ + ":")
    kept = [
        [b for b in row if isinstance(b.callback_data, str) and b.callback_data.startswith(keep)]
        for row in screen.keyboard.inline_keyboard
    ]
    rows = [
        [InlineKeyboardButton(text=texts.QUIZ_READ_NEXT, callback_data=Quiz().pack())],
        *[row for row in kept if row],
        [InlineKeyboardButton(text=texts.HOME_BUTTON, callback_data=Home().pack())],
    ]
    return replace(screen, keyboard=InlineKeyboardMarkup(inline_keyboard=rows))


def quiz_unavailable(curriculum: Curriculum, progress: Progress) -> Screen:
    """Замок «Закрепления» (FR-49): до урока открытия — называет его; на нём и дальше урок назад
    не называем — нужно начать больше уроков букв."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb)
    kb.adjust(2)
    opens = first_quiz_lesson(curriculum)
    item = progress.continue_item or curriculum.first_item()
    here = curriculum.locate(item.id)[0]
    if opens is None or here.number >= opens.number:
        return Screen(texts.QUIZ_LOCKED_MORE, kb.as_markup())
    return Screen(texts.QUIZ_LOCKED.format(lesson=escape(opens.title)), kb.as_markup())


# ---------- сура целиком и наизусть (FR-57, FR-59, ADR-0076) ----------
def _sura_block(sura: Sura) -> str:
    """Текст суры: басмала перед сурой и аяты, у каждого — знак конца аята с номером."""
    lines = [f"<b>{escape(sura.opening.text)}</b>"] if sura.opening else []
    lines += [f"{escape(a.text)} ۝{a.quran.split(':')[1]}" for a in sura.ayahs]
    return "\n".join(lines)


def _sura_back(kb: InlineKeyboardBuilder, sura: Sura, mode: SuraMode) -> None:
    """Назад: наизусть — к списку сур, по тексту — к первой карточке аята; и 🏠."""
    if mode is SuraMode.MEMORY:
        _home_row(kb, (texts.SURA_BACK_TO_LIST_BUTTON, SuraList()))
    else:
        _home_row(kb, (texts.SURA_BACK_TO_LESSON_BUTTON, GoItem(item_id=sura.ayahs[0].id)))


def sura_list(curriculum: Curriculum, memorized: Collection[int]) -> Screen:
    kb = InlineKeyboardBuilder()
    found = suras(curriculum)
    for sura in found:
        mark = "✅ " if sura.number in memorized else ""
        kb.button(text=f"{mark}{sura.name}", callback_data=SuraOpen(n=sura.number, m="m"))
    _home_row(kb, (texts.BACK_TO_MORE, More()))
    kb.adjust(*([2] * (len(found) // 2)), *([1] * (len(found) % 2)), 2)
    return Screen(texts.SURA_LIST, kb.as_markup())


def sura_text(sura: Sura) -> Screen:
    """«📖 Вся сура»: текст всех аятов, голосовое — целиком (текстом: подпись к фото короче)."""
    caption = "\n\n".join(
        (
            texts.SURA_TEXT_HEAD.format(name=escape(sura.name)),
            _sura_block(sura),
            texts.SURA_TEXT_HINT,
        )
    )
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.MEMORY_BUTTON, callback_data=SuraOpen(n=sura.number, m="m"))
    _sura_back(kb, sura, SuraMode.TEXT)
    kb.adjust(1, 2)
    return Screen(caption, kb.as_markup())


def sura_memory(sura: Sura) -> Screen:
    """Наизусть, шаг 1: текст виден, пока ученик не нажмёт «Готов»."""
    caption = "\n\n".join(
        (
            texts.SURA_MEMORY_HEAD.format(name=escape(sura.name)),
            _sura_block(sura),
            texts.SURA_MEMORY_HINT,
        )
    )
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.SURA_READY_BUTTON, callback_data=SuraReady(n=sura.number))
    _sura_back(kb, sura, SuraMode.MEMORY)
    kb.adjust(1, 2)
    return Screen(caption, kb.as_markup())


def sura_memory_ready(sura: Sura) -> Screen:
    """Наизусть, шаг 2: текста нет — только название; ждём голосовое."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.SURA_SHOW_TEXT_BUTTON, callback_data=SuraOpen(n=sura.number, m="m"))
    _sura_back(kb, sura, SuraMode.MEMORY)
    kb.adjust(1, 2)
    return Screen(texts.SURA_MEMORY_READY.format(name=escape(sura.name)), kb.as_markup())


SURA_BAD_SHOWN: Final = 8  # строк про аяты с ошибками в разборе
SURA_BAD_BUTTONS: Final = 8  # кнопок «🔁 Аят N»


@dataclass(frozen=True, slots=True)
class SuraErrorList:
    """Что осталось от чтения суры для разбора: аяты с ошибками, исправленные — ✅.

    Хранится у ученика (FSM), пока он разбирает аяты (автор 2026-11-08: список не пропадает)."""

    sura: int
    mode: str  # «t» по тексту, «m» наизусть
    clean: int
    total: int
    bad: tuple[tuple[int, str, str], ...]  # (номер аята, карточка, AyahOutcome)
    fixed: frozenset[str] = frozenset()

    @classmethod
    def of(cls, result: SuraReadingResult) -> "SuraErrorList":
        reading = result.reading
        return cls(
            result.sura.number,
            "t" if reading.mode is SuraMode.TEXT else "m",
            reading.assessment.clean_count,
            len(reading.assessment.ayahs),
            tuple(
                (x.number, x.item_id, x.outcome.value)
                for x in reading.assessment.ayahs
                if x.outcome is not AyahOutcome.CLEAN
            ),
        )


def sura_result(result: SuraReadingResult) -> Screen:
    """Разбор чтения суры по аятам: итог, аяты с ошибками, переход к их карточкам."""
    reading, sura = result.reading, result.sura
    head = texts.SURA_RESULT_HEAD[reading.mode.value].format(name=escape(sura.name))
    if reading.passed:
        passed = (
            texts.SURA_PASSED_TEXT if reading.mode is SuraMode.TEXT else texts.SURA_PASSED_MEMORY
        )
        a = reading.assessment
        summary = texts.SURA_SUMMARY.format(clean=a.clean_count, total=len(a.ayahs))
        kb = InlineKeyboardBuilder()
        mode = "t" if reading.mode is SuraMode.TEXT else "m"
        kb.button(text=texts.SURA_AGAIN_BUTTON, callback_data=SuraOpen(n=sura.number, m=mode))
        _sura_back(kb, sura, reading.mode)
        kb.adjust(1, 2)
        return Screen("\n\n".join((head, summary, passed)), kb.as_markup())
    return sura_errors(sura, SuraErrorList.of(result), head)


def sura_errors(sura: Sura, errors: SuraErrorList, head: str = "") -> Screen:
    """Аяты с ошибками; исправленные после чтения — ✅. Кнопка аята — его карточка, оттуда
    «📋 К ошибкам суры» — снова сюда."""
    head = head or texts.SURA_RESULT_HEAD[
        SuraMode.TEXT.value if errors.mode == "t" else SuraMode.MEMORY.value
    ].format(name=escape(sura.name))
    lines = [
        texts.SURA_FIXED_LINE.format(n=n)
        if item_id in errors.fixed
        else texts.SURA_AYAH_LINE.format(n=n, outcome=texts.SURA_OUTCOME[outcome])
        for n, item_id, outcome in errors.bad[:SURA_BAD_SHOWN]
    ]
    if len(errors.bad) > SURA_BAD_SHOWN:
        lines.append(texts.SURA_MORE.format(n=len(errors.bad) - SURA_BAD_SHOWN))
    summary = texts.SURA_SUMMARY.format(clean=errors.clean, total=errors.total)
    parts = [head, summary, "\n".join(lines), texts.SURA_NOT_PASSED]
    kb = InlineKeyboardBuilder()
    shown = errors.bad[:SURA_BAD_BUTTONS]
    for n, item_id, _ in shown:
        label = texts.SURA_AYAH_FIXED_BUTTON if item_id in errors.fixed else texts.SURA_AYAH_BUTTON
        kb.button(text=label.format(n=n), callback_data=GoItem(item_id=item_id))
    kb.button(text=texts.SURA_AGAIN_BUTTON, callback_data=SuraOpen(n=sura.number, m=errors.mode))
    _sura_back(kb, sura, SuraMode.TEXT if errors.mode == "t" else SuraMode.MEMORY)
    kb.adjust(*([2] * (len(shown) // 2)), *([1] * (len(shown) % 2)), 1, 2)
    return Screen("\n\n".join(parts), kb.as_markup())
