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
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from muallim.application.transcription import as_text
from muallim.application.use_cases.progress import LessonStatus, Progress
from muallim.application.use_cases.quiz import QuizOverview, QuizRest, QuizResult, QuizView
from muallim.application.use_cases.reading import CardReading
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import Assessment, ErrorKind
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem, letters_before
from muallim.domain.phonetics import CONSONANTS, Zone, articulation_zone, count_syllables, syllables
from muallim.domain.policy import Verdict
from muallim.domain.quiz import QUIZ_ROUND, RoundSummary, Step, first_quiz_lesson
from muallim.domain.settings import (
    ASK_OFFSET_HOURS,
    REMINDER_HOURS,
    HowToRead,
    LearnerSettings,
    local_minute,
)
from muallim.presentation.telegram import render, texts, views
from muallim.presentation.telegram.callbacks import (
    ChangeSetting,
    Consent,
    DeleteData,
    Dispute,
    GoItem,
    Help,
    Home,
    Lessons,
    LettersSheet,
    Listen,
    Me,
    Noop,
    Opening,
    Privacy,
    Quiz,
    QuizAnswer,
    QuizSkip,
    RecordReference,
    ShareLesson,
    ShowProgress,
    ShowSettings,
    Signs,
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
    head = next((i.text[0] for i in lesson.items if i.kind is ItemKind.LETTER), "")
    return "ء" if head in "أإؤئآ" else head


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


def _bar(done: int, total: int) -> str:
    return views.bar(round(100 * done / total) if total else 0)


# ---------- главная ----------
def home(curriculum: Curriculum, progress: Progress, quiz_waiting: int = 0) -> Screen:
    item = progress.continue_item or curriculum.first_item()
    lesson, _ = curriculum.locate(item.id)
    fresh = progress.attempts_total == 0 and item == curriculum.first_item()
    caption = texts.HOME.format(
        streak=_days(progress.streak_days),
        today=progress.today_attempts,
        done=progress.done_lessons,
        total=progress.practice_lessons,
        bar=_bar(progress.done_lessons, progress.practice_lessons),
        next_title=escape(lesson.title),
    )
    kb = InlineKeyboardBuilder()
    label = texts.START_BUTTON if fresh else texts.CONTINUE_BUTTON.format(title=lesson.title)
    kb.button(text=label, callback_data=GoItem(item_id=item.id))
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    quiz_label = (
        texts.QUIZ_BUTTON_WAITING.format(n=quiz_waiting) if quiz_waiting else texts.QUIZ_BUTTON
    )
    kb.button(text=quiz_label, callback_data=Quiz())
    kb.button(text=texts.SIGNS_BUTTON, callback_data=Signs())
    kb.button(text=texts.PROGRESS_BUTTON, callback_data=ShowProgress())
    kb.button(text=texts.SETTINGS_BUTTON, callback_data=ShowSettings())  # FR-51
    kb.adjust(1, 2, 2, 1)
    image, key = _alphabet_map(curriculum, progress)
    return Screen(caption, kb.as_markup(), image, key)


def voice_on_home(curriculum: Curriculum, progress: Progress) -> Screen:
    """Голосовое, когда урок не открыт: попытку не пишем, кнопка — на карточку курсора."""
    item = progress.continue_item or curriculum.first_item()
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.CONTINUE_BUTTON.format(title=curriculum.locate(item.id)[0].title),
        callback_data=GoItem(item_id=item.id),
    )
    return Screen(texts.VOICE_ON_HOME, kb.as_markup())


def _days(n: int) -> str:
    one, few, many = texts.DAY_FORMS
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}" if n else texts.STREAK_ZERO


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

    name, chunk_all = parts[part]
    pages = max(1, -(-len(chunk_all) // LESSONS_PER_PAGE))
    page = min(max(page, 0), pages - 1)
    chunk = chunk_all[page * LESSONS_PER_PAGE : (page + 1) * LESSONS_PER_PAGE]
    current = curriculum.locate(progress.continue_item.id)[0].id if progress.continue_item else ""
    for lesson in chunk:
        lp = progress.of(lesson.id)
        icon = "📖" if not lp.total else _ICON[lp.status]
        pointer = "👉" if lesson.id == current else ""
        count = f" {lp.mastered}/{lp.total}" if lp.status is LessonStatus.STARTED else ""
        kb.button(
            text=f"{icon}{pointer} {lesson.title}{count}",
            callback_data=GoItem(item_id=lesson.items[0].id),
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
    reading: CardReading | None = None,
    *,
    view: LearnerSettings | None = None,
) -> Screen:
    """``view`` — настройки ученика: «Как читается» и крупный шрифт (FR-51)."""
    view = view or LearnerSettings()
    lesson, i = curriculum.locate(item.id)
    parts = [texts.CARD_HEAD.format(lesson=escape(lesson.title), n=i + 1, total=len(lesson.items))]
    known = letters_before(curriculum, lesson.id)
    if i == 0 and lesson.section == "letter":
        parts.append(_new_letter(curriculum, lesson, known))
    image = _card_image(lesson, item, i, view.large_font)
    if image is None:
        parts.append(f"<b>{escape(item.text)}</b>")
    if item.kind is ItemKind.RULE:
        parts.append(texts.CARD_RULE.format(title=escape(item.name), body=escape(item.tip)))
    elif item.kind is ItemKind.ALPHABET:
        names = "\n".join(
            f"{letter} — {escape(name)}"
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
            parts.append(
                info.format(name=escape(item.name), sound=escape(item.sound), tip=escape(item.tip))
            )
        if item.note and not item.note.startswith(("фраза", "сура", "басмала", "слог")):
            parts.append(texts.CARD_NOTE.format(note=escape(item.note)))
        parts.append(
            texts.CARD_READ_SYLLABLE if item.kind is ItemKind.SYLLABLE else texts.CARD_READ
        )
        if reading is not None and reading.reading and view.how_to_read is not HowToRead.HIDDEN:
            legend = "".join(f"\n<i>{escape(line)}</i>" for line in reading.legend)
            line = (
                texts.CARD_HOW_TO_READ_SHOWN
                if view.how_to_read is HowToRead.SHOWN
                else texts.CARD_HOW_TO_READ
            )
            parts.append(line.format(reading=escape(as_text(reading.reading)), legend=legend))
    ref = []
    if item.source is not None and item.source.page is not None:
        ref.append(texts.CARD_BOOK.format(page=item.source.page))
    if item.quran:
        ref.append(texts.CARD_QURAN.format(ref=item.quran))
    if ref:
        parts.append("<i>" + " · ".join(ref) + "</i>")

    kb = _card_keyboard(curriculum, item, has_audio, is_teacher, bool(known))
    key = f"card:{item.id}:{curriculum.version}" + (":large" if view.large_font else "")
    return Screen("\n\n".join(parts), kb, image, key)


def _card_keyboard(
    curriculum: Curriculum, item: LessonItem, has_audio: bool, is_teacher: bool, sheet: bool
) -> InlineKeyboardMarkup:
    """Кнопки карточки; ``sheet`` — есть буквы до урока, кнопка шпаргалки (FR-52)."""
    lesson, i = curriculum.locate(item.id)
    kb = InlineKeyboardBuilder()
    top = 0
    if has_audio:  # послушать можно везде, где есть звук: и в правиле, и в слоге (ADR-0032)
        kb.button(text=texts.LISTEN_BUTTON, callback_data=Listen(item_id=item.id))
        top += 1
    if is_teacher and item.kind is not ItemKind.ALPHABET:  # учитель озвучивает и правило
        kb.button(text=texts.RECORD_BUTTON, callback_data=RecordReference(item_id=item.id))
        top += 1
    if sheet:  # шпаргалка букв, пройденных до урока (FR-52)
        kb.button(
            text=texts.SHEET_BUTTON,
            callback_data=LettersSheet(lesson_id=lesson.id, item_id=item.id),
        )
        top += 1
    nav = _nav(kb, curriculum, item)
    # первый шаг: назад — только «⬅️ Предыдущий урок», без «◀️ Назад» на шаг (FR-50)
    prev = i == 0 and _previous_lesson_button(kb, curriculum, lesson)
    kb.button(text=texts.LESSONS_BUTTON, callback_data=_lessons_of(curriculum, lesson))
    _home_row(kb)
    kb.adjust(*([1] * top), *nav, *((1,) if prev else ()), 2)
    return kb.as_markup()


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


def _card_image(lesson: Lesson, item: LessonItem, i: int, large: bool = False) -> bytes | None:
    """``large`` — «Крупный шрифт»: крупнее строка карточки и правила (ADR-0061)."""
    if not render.available():
        return None
    scale = render.LARGE_SCALE if large else 1.0
    if item.kind is ItemKind.ALPHABET:
        return render.letters(item.text)
    if item.kind is ItemKind.RULE:
        return render.rule(item.text, scale)
    if item.kind is ItemKind.LETTER and (letter := _letter_shown(lesson)):
        zone = articulation_zone(letter)
        zones = [(texts.ZONES[z.value], z is zone) for z in Zone] if zone else []
        return render.letter_forms(letter, item.text, texts.LETTER_FORMS, zones)
    return render.card(item.text, lesson.accent, (i, len(lesson.items)), scale)


def _nav(kb: InlineKeyboardBuilder, curriculum: Curriculum, item: LessonItem) -> list[int]:
    """Кнопки «◀️ Назад» и «▶️ Дальше» без пустышек: счёт шагов — в заголовке (FR-50).

    На первом шаге урока «Назад» нет (там «⬅️ Предыдущий урок»); на последнем вперёд ведёт
    «➡️ Следующий урок: …» отдельной строкой. Возвращает раскладку рядов.
    """
    lesson, i = curriculum.locate(item.id)
    rows: list[int] = []
    previous = curriculum.previous_item(item.id) if i > 0 else None
    if previous:
        kb.button(text=texts.BACK_BUTTON, callback_data=GoItem(item_id=previous.id))
    following = curriculum.next_item(item.id)
    if following is None:
        return [1] if previous else []
    next_lesson, _ = curriculum.locate(following.id)
    if next_lesson != lesson:
        if previous:
            rows.append(1)
        kb.button(
            text=texts.NEXT_LESSON_BUTTON.format(title=next_lesson.title),
            callback_data=GoItem(item_id=following.id),
        )
        return [*rows, 1]
    kb.button(text=texts.NEXT_BUTTON, callback_data=GoItem(item_id=following.id))
    return [2 if previous else 1]


def _previous_lesson_button(
    kb: InlineKeyboardBuilder, curriculum: Curriculum, lesson: Lesson
) -> bool:
    """Кнопка «Предыдущий урок» — на его первую карточку; на первом уроке книги её нет."""
    prev = curriculum.previous_lesson(lesson.id)
    if prev is None:
        return False
    kb.button(
        text=texts.PREVIOUS_LESSON_BUTTON.format(title=prev.title),
        callback_data=GoItem(item_id=prev.items[0].id),
    )
    return True


def _lessons_of(curriculum: Curriculum, lesson: Lesson) -> Lessons:
    """Кнопка «Уроки» с карточки — сразу на страницу её части."""
    for k, (_, items) in enumerate(curriculum.parts()):
        if lesson in items:
            return Lessons(part=k, page=items.index(lesson) // LESSONS_PER_PAGE)
    return Lessons(part=-1)


# ---------- результат ----------
def result(
    curriculum: Curriculum,
    r: RecitationResult,
    has_audio: bool,
    resume: LessonItem | None = None,
    staff: bool = False,
) -> Screen:
    """Итог попытки. ``resume`` — идёт начало занятия: после басмалы — «Продолжить занятие».

    «Услышано» и блок «Для исследования» с номером попытки видят только учитель и разметчик
    (``staff``): новичку они мешают, номер попытки ученик получает в «🚩 Бот ошибся» (FR-50).
    """
    a = r.attempt.assessment
    lesson, _ = curriculum.locate(r.item.id)
    head = [_VERDICT[r.verdict], texts.RESULT_SCORE.format(bar=views.bar(a.score), score=a.score)]
    image = None
    if render.available() and r.lesson_completed and not a.errors:  # с ошибками — сначала разбор
        image = _postcard_image(lesson)
    elif render.available():
        wrong = render.error_clusters(r.item.text, [e.syllable or 1 for e in a.errors], a.reference)
        unread = set()
        if r.unread_from is not None:
            first = _first_unread_consonant(a.reference, r.unread_from)
            unread = render.unread_clusters(r.item.text, a.reference, first)
        states = render.word_states(r.item.text, wrong, unread)
        ok = sum(1 for s in states if s is render.WordState.OK)
        label = texts.RESULT_WORDS.format(ok=ok, total=len(states))
        image = render.result_words(r.item.text, states, a.score, label, _swap(a))
    else:
        head.insert(1, f"<b>{escape(r.item.text)}</b>")
    head += [*_progress(r), *_praise(r)]
    parts: list[str] = []
    if staff and not r.feedback:
        parts.append(escape(texts.HEARD_LINE.format(text=r.heard_transcription)))
    if r.lesson_completed:
        parts.append(texts.LESSON_DONE.format(lesson=escape(lesson.title)))
    if r.next_item is None:
        parts.append(texts.LAST_ITEM)
    research = (
        texts.RESEARCH_BLOCK.format(
            code=texts.ATTEMPT_CODE.format(code=views.attempt_code(r.attempt.id)),
            reference=escape(a.reference),
            heard=escape(a.heard),
        )
        if staff
        else ""
    )
    details = ""
    if r.feedback:
        letter_line = _lesson_letter_line(lesson, r)  # буква урока — первой строкой (ADR-0062, В3)
        details = "\n\n".join(p for p in [letter_line, *_explanations(r, has_audio), research] if p)
    else:
        parts.append(research)
    if r.feedback and r.expected_reading:  # «Нужно / У тебя» — сразу под вердиктом
        rest = len("\n\n".join(head + parts)) + 2
        head.append(_comparison(r, CAPTION_LIMIT - rest))
    keyboard = _result_keyboard(curriculum, r, lesson, has_audio, resume)
    return Screen("\n\n".join(p for p in head + parts if p), keyboard, image, details=details)


_LETTER_SWAPS: Final = frozenset(
    {ErrorKind.LETTER_SUBSTITUTION, ErrorKind.SOUND_SUBSTITUTION, ErrorKind.FRAGMENT_SUBSTITUTION}
)


def _lesson_letter_line(lesson: Lesson, r: RecitationResult) -> str:
    """В уроке буквы: вместо неё прозвучала другая или её нет — строка для начала разбора.

    Только прочитанная часть строки (непрочитанный конец — не ошибки, как в разборе); огласовки
    и удвоение — не «другая буква» (ADR-0062, В3 (а)). Вердикт и балл не меняются (OQ-14).
    """
    if lesson.section != "letter" or not (letter := _letter_of(lesson)):
        return ""
    a = r.attempt.assessment
    cut = None
    spans = syllables(a.reference) if r.unread_from is not None else []
    if r.unread_from is not None and 0 < r.unread_from < len(spans):
        cut = spans[r.unread_from][0]
    for e in a.errors:
        if letter not in e.expected or (cut is not None and e.position >= cut):
            continue
        if e.kind is ErrorKind.SOUND_MISSING:
            return texts.LESSON_LETTER_MISSING.format(letter=letter)
        if e.kind in _LETTER_SWAPS:
            heard = [c for c in e.heard if c in CONSONANTS]
            if letter in heard:  # согласная та же — ошибка в огласовке
                continue
            if not heard:
                return texts.LESSON_LETTER_MISSING.format(letter=letter)
            return texts.LESSON_LETTER_WRONG.format(letter=letter, heard=heard[0])
    return ""


def _swap(a: Assessment) -> tuple[str, str, str, str, str] | None:
    """Первая замена одной буквы другой — «нужна ص вместо прозвучала س» на картинке."""
    for e in a.errors:
        if e.expected in CONSONANTS and e.heard in CONSONANTS and e.expected != e.heard:
            return e.expected, e.heard, texts.SWAP_NEED, texts.SWAP_INSTEAD, texts.SWAP_HEARD
    return None


def _progress(r: RecitationResult) -> list[str]:
    """«Было → стало» (только если балл изменился, FR-50) и исправленные слоги."""
    if r.previous_score is None:
        return []
    now = r.attempt.assessment.score
    lines = []
    if now != r.previous_score:
        trend = texts.TREND_UP if now > r.previous_score else texts.TREND_DOWN
        lines.append(texts.RESULT_PROGRESS.format(trend=trend, before=r.previous_score, now=now))
    if r.fixed:
        syllables = ", ".join(f"«{escape(s)}»" for s in r.fixed)
        lines.append(texts.RESULT_FIXED.format(syllables=syllables))
    return ["\n".join(lines)] if lines else []


def _praise(r: RecitationResult) -> list[str]:
    """Сначала — что уже верно (непрочитанное не в счёт); только если есть и ошибки."""
    total = len(r.expected_reading)
    right = sum(1 for _, wrong in r.expected_reading[: r.unread_from] if not wrong)
    if not r.feedback or not 0 < right < total:
        return []
    return [texts.RESULT_RIGHT.format(n=right, total=total)]


def _first_unread_consonant(reference: str, unread: int) -> int:
    """Номер (с 1) первой согласной непрочитанного слога."""
    return count_syllables(reference[: syllables(reference)[unread][0]]) + 1


def _result_keyboard(
    curriculum: Curriculum,
    r: RecitationResult,
    lesson: Lesson,
    has_audio: bool,
    resume: LessonItem | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_audio:
        kb.button(text=texts.LISTEN_BUTTON, callback_data=Listen(item_id=r.item.id))
    # ряд «◀️ Назад · 🔁 Ещё раз · ▶️ Дальше»: обе крайние — на соседние строки, «Ещё раз» —
    # снова карточка этой строки (там видно, что читать, и можно послушать эталон)
    nav = 1
    first_step = curriculum.locate(r.item.id)[1] == 0  # назад — «⬅️ Предыдущий урок» (FR-50)
    if not first_step and (previous := curriculum.previous_item(r.item.id)):
        kb.button(text=texts.BACK_BUTTON, callback_data=GoItem(item_id=previous.id))
        nav += 1
    kb.button(text=texts.AGAIN_BUTTON, callback_data=GoItem(item_id=r.item.id))
    next_row = False
    if resume is not None:  # начало занятия прочитано — туда, где ученик остановился
        title = curriculum.locate(resume.id)[0].title
        kb.button(
            text=texts.RESUME_BUTTON.format(title=title), callback_data=GoItem(item_id=resume.id)
        )
        next_row = True
    elif r.next_item is not None:
        next_lesson, _ = curriculum.locate(r.next_item.id)
        if next_lesson != lesson:  # длинная подпись — отдельной строкой
            label, next_row = texts.NEXT_LESSON_BUTTON.format(title=next_lesson.title), True
        else:
            label, nav = texts.NEXT_BUTTON, nav + 1
        kb.button(text=label, callback_data=GoItem(item_id=r.next_item.id))
    if r.lesson_completed:
        kb.button(text=texts.SHARE_BUTTON, callback_data=ShareLesson(lesson=lesson.id))
    prev = first_step and _previous_lesson_button(kb, curriculum, lesson)
    kb.button(text=texts.DISPUTE_BUTTON, callback_data=Dispute(attempt=r.attempt.id.hex))
    _home_row(kb)
    rows: Sequence[int] = (
        *((1,) if has_audio else ()),
        nav,
        *((1,) if next_row else ()),
        *((1,) if r.lesson_completed else ()),
        *((1,) if prev else ()),
        2,
    )
    kb.adjust(*rows)
    return kb.as_markup()


def _comparison(r: RecitationResult, budget: int) -> str:
    """«Нужно» и «У тебя» по слогам; слог с ошибкой подчёркнут (FR-43).

    Длинную строку укорачиваем по целым слогам (не внутри тега), чтобы уложиться в ``budget``.
    """
    for keep in range(len(r.expected_reading), 0, -1):
        tail = "…" if keep < len(r.expected_reading) else ""
        expected = "-".join(
            f"<u>{escape(text)}</u>" if wrong else escape(text)
            for text, wrong in r.expected_reading[:keep]
        )
        heard = escape(as_text(r.heard_reading[:keep])) if r.heard_reading else "—"
        lines = [
            texts.RESULT_EXPECTED.format(text=expected + tail),
            texts.RESULT_HEARD.format(text=heard + (tail if r.heard_reading[keep:] else "")),
            *(f"<i>{escape(line)}</i>" for line in r.legend),
        ]
        text = "\n".join(lines)
        if len(text) <= budget:
            return text
    return ""


def _explanations(r: RecitationResult, has_audio: bool) -> list[str]:
    """Коротко — до трёх мест (ADR-0031); «👄 Подробнее» — свёрнуто; одна строка «что сделать»."""
    shown = r.feedback[: views.MAX_ERRORS_SHOWN]
    numbers = texts.ERROR_NUMBERS
    out = [f"{n} {escape(e.text)}" for n, e in zip(numbers, shown, strict=False)]
    if len(r.feedback) > len(shown):
        out.append(texts.MORE_ERRORS.format(n=len(r.feedback) - len(shown)))
    more = [f"{n} {escape(e.more)}" for n, e in zip(numbers, shown, strict=False) if e.more]
    if more:
        out.append(
            f"<blockquote expandable>{texts.MORE_HEAD}\n" + "\n\n".join(more) + "</blockquote>"
        )
    out.append(texts.PLAN_LISTEN if has_audio else texts.PLAN_READ)
    return out


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
        text=texts.CONTINUE_BUTTON.format(title=curriculum.locate(item.id)[0].title),
        callback_data=GoItem(item_id=item.id),
    )
    kb.button(text=texts.LESSONS_BUTTON, callback_data=Lessons(part=-1))
    _home_row(kb)
    kb.adjust(1, 2)
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
        ("auto_reference", texts.SETTING_AUTO_REFERENCE, s.auto_reference),
        ("daily_opening", texts.SETTING_DAILY_OPENING, s.daily_opening),
        ("large_font", texts.SETTING_LARGE_FONT, s.large_font),
        ("research_block", texts.SETTING_RESEARCH_BLOCK, s.research_block),
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
    kb.button(text=texts.HELP_BUTTON, callback_data=Help())
    kb.button(text=texts.PRIVACY_BUTTON, callback_data=Privacy())
    kb.button(text=texts.ME_BUTTON, callback_data=Me())
    _home_row(kb)
    kb.adjust(1, 3, 1, 1, 1, 1, 1, 2, 2)
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
        text=texts.CONTINUE_BUTTON.format(title=curriculum.locate(item.id)[0].title),
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
    _back_to_settings(kb)
    _home_row(kb)
    kb.adjust(1, 2)
    return Screen(texts.HELP, kb.as_markup())


def privacy(research_consent: bool) -> Screen:
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
    return Screen(views.privacy(research_consent), kb.as_markup())


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
    _home_row(kb)
    kb.adjust(*((1,) if sheet else ()), 2)
    image = render.signs() if render.available() else None
    return Screen(texts.SIGNS, kb.as_markup(), image, "signs:v1")


SHEET_LISTEN_PER_ROW = 4


def letters_sheet(
    curriculum: Curriculum, lesson_id: str, audio: Collection[str], back_item: str = ""
) -> Screen:
    """Шпаргалка «буква → название → звук → 🔊» по книге строго до урока (FR-52, ADR-0062 п. 7).

    ``audio`` — id головных карточек, у которых есть эталон: 🔊 — существующий ``Listen``.
    ``back_item`` — карточка, с которой открыли («◀️ Назад» на неё); пусто — назад на «Знаки».
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
    раз» увели бы из раунда) — «🧠 Дальше по закреплению»; 🔊 эталона и «🚩 Бот ошибся» остаются."""
    keep = (Listen.__prefix__ + ":", Dispute.__prefix__ + ":")
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
