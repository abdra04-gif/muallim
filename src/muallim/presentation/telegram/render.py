"""Картинки для Telegram: строка книги крупно, буква урока красным, ошибки подсвечены (ADR-0024).

Telegram не умеет крупный шрифт и цвет в тексте, поэтому арабский текст рисуется картинкой
шрифтом Scheherazade New (SIL, OFL — assets/fonts): огласовки крупно и прямо над буквой.
Строка рисуется целиком (правильное соединение букв), а отдельные буквы перекрашиваются
полосой по их точным границам: граница буквы — ширина начала строки с ZWJ на конце
(буква в той же форме, что внутри слова).

Нужен Pillow с libraqm (на macOS: brew install fribidi; в Docker: libfribidi0). Без него
``available()`` → False, и бот показывает текстовые карточки.
"""

import difflib
import io
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont, features

from muallim.domain.phonetics import CONSONANTS

FONTS = Path(__file__).parent / "assets" / "fonts"
ZWJ = "‍"
SHADDA = "ّ"
HAMZA_FORMS = frozenset("ءأإؤئآ")
MADD_LETTERS = frozenset("اىوي")  # без знаков — удлинение, а не согласный
PHONEME_OF: Final = {"ة": "ت", "ى": "ي"}  # как буква текста записана в фонемах

WIDTH = 1280
PAD = 64
ARABIC_SIZE = 104

# Палитра «как в книге»: бумага, золотая рамка, чёрный текст, красная буква урока
PAPER = (251, 247, 236)
FRAME = (200, 164, 77)
INK = (34, 30, 28)
ACCENT = (200, 40, 40)
WRONG_BG = (255, 214, 214)
OK = (46, 125, 50)
WARN = (230, 160, 0)
MUTED = (190, 182, 165)
DOT = (215, 205, 180)


class Mark(StrEnum):
    """Состояние буквы на карте алфавита."""

    DONE = "done"
    STARTED = "started"
    NEW = "new"
    CURRENT = "current"


def available() -> bool:
    return bool(features.check("raqm"))


@cache
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "ScheherazadeNew-Bold.ttf" if bold else "ScheherazadeNew-Regular.ttf"
    return ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.RAQM)


# ---------- разбор текста ----------
@dataclass(frozen=True, slots=True)
class Cluster:
    """Буква со своими огласовками; start/end — индексы в строке."""

    start: int
    end: int
    base: str
    marks: str

    @property
    def is_consonant(self) -> bool:
        if self.base in HAMZA_FORMS:
            return True
        if self.base in MADD_LETTERS and not self.marks:
            return False
        return unicodedata.category(self.base) == "Lo"


def clusters(text: str) -> list[Cluster]:
    out: list[Cluster] = []
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and unicodedata.category(text[j]) == "Mn":
            j += 1
        if not text[i].isspace():
            out.append(Cluster(i, j, text[i], text[i + 1 : j]))
        i = j
    return out


def consonant_clusters(text: str) -> list[int]:
    """Номер кластера для каждого согласного по порядку (шадда — два согласных)."""
    order: list[int] = []
    for n, c in enumerate(clusters(text)):
        if c.is_consonant:
            order += [n] * (2 if SHADDA in c.marks else 1)
    return order


def accent_clusters(text: str, letters: Collection[str]) -> set[int]:
    return {n for n, c in enumerate(clusters(text)) if c.base in letters}


def error_clusters(
    text: str, syllables: Collection[int | None], reference: str | None = None
) -> set[int]:
    """Слоги ошибок (с 1, по согласным эталона) → кластеры текста (ADR-0024).

    С ``reference`` (эталон в фонемах) согласные сопоставляются по буквам: в фонемах шадда
    бывает одной согласной, «ٱ» внутри фразы не читается, и счёт по номеру уезжает.
    Буквы мадда и непроизносимые буквы подсвечиваются вместе со своим слогом.
    """
    if reference is None:
        order = consonant_clusters(text)
        return {order[s - 1] for s in syllables if s is not None and 1 <= s <= len(order)}
    owner = _owners(text, reference)
    letters = clusters(text)
    found = set()
    for s in syllables:
        if s is not None and 1 <= s <= len(owner):
            found.add(owner[s - 1])
    # к ошибочной букве — её «хвост» без своего звука (мадд, татвиль) и немые буквы перед ней
    tied = _tied(letters, set(owner))
    return {n for n in range(len(letters)) if tied[n] in found}


def unread_clusters(text: str, reference: str, consonant: int) -> set[int]:
    """Кластеры текста от ``consonant``-й согласной эталона (с 1) до конца строки."""
    total = sum(1 for ch in reference if ch in CONSONANTS)
    return error_clusters(text, range(consonant, total + 1), reference)


def _letter(c: Cluster) -> str:
    """Буква текста так, как она записана в фонемах."""
    return "ء" if c.base in HAMZA_FORMS or c.base == "ٱ" else PHONEME_OF.get(c.base, c.base)


def _owners(text: str, reference: str) -> list[int]:
    """Для каждой согласной эталона — кластер текста, к которому она относится."""
    letters = clusters(text)
    spoken = [n for n, c in enumerate(letters) if c.is_consonant]
    sounds = [ch for ch in reference if ch in CONSONANTS]
    matcher = difflib.SequenceMatcher(
        None, [_letter(letters[n]) for n in spoken], sounds, autojunk=False
    )
    owner: list[int] = []
    for _, i1, i2, j1, j2 in matcher.get_opcodes():
        for k in range(j2 - j1):
            if i2 > i1:  # equal/replace: по порядку, лишние фонемы — к последней букве
                owner.append(spoken[min(i1 + k, i2 - 1)])
            else:  # вставка (шадда двумя согласными, танвин) — к предыдущей букве
                owner.append(owner[-1] if owner else spoken[min(i1, len(spoken) - 1)])
    return owner


def _tied(letters: Sequence[Cluster], voiced: set[int]) -> list[int]:
    """Кластер → чью ошибку он разделяет: буква без звука — с соседней звучащей."""
    tied = list(range(len(letters)))
    last = None
    for n, c in enumerate(letters):  # мадд и татвиль — к предыдущей звучащей
        if n in voiced:
            last = n
        elif not c.is_consonant and last is not None:
            tied[n] = last
    following = None
    for n in range(len(letters) - 1, -1, -1):  # немая согласная (ٱ, лям) — к следующей
        if n in voiced:
            following = n
        elif letters[n].is_consonant and following is not None:
            tied[n] = following
    return tied


# ---------- вёрстка ----------
def _wrap(words: Sequence[str], font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and font.getlength(trial, direction="rtl") > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _spans(line: str, font: ImageFont.FreeTypeFont) -> list[tuple[float, float]]:
    """Для каждого кластера строки — [от, до] в пикселях от правого края."""
    spans = []
    for c in clusters(line):
        joiner = ZWJ if c.end < len(line) and not line[c.end].isspace() else ""
        left = font.getlength(
            line[: c.start] + (ZWJ if c.start and not line[c.start - 1].isspace() else ""),
            direction="rtl",
        )
        right = font.getlength(line[: c.end] + joiner, direction="rtl")
        spans.append((left if c.start else 0.0, right))
    return spans


def _frame(img: Image.Image) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    draw.rectangle((14, 14, w - 15, h - 15), outline=FRAME, width=4)
    draw.rectangle((26, 26, w - 27, h - 27), outline=FRAME, width=1)
    for x, y in ((26, 26), (w - 27, 26), (26, h - 27), (w - 27, h - 27)):
        draw.regular_polygon((x, y, 9), 4, rotation=45, fill=FRAME)
    return draw


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _dots(draw: ImageDraw.ImageDraw, y: int, current: int, total: int) -> None:
    if total <= 1:
        return
    gap = 26
    x0 = WIDTH // 2 + (total - 1) * gap // 2  # справа налево, как читается книга
    for i in range(total):
        x = x0 - i * gap
        r = 8 if i == current else 6
        fill = ACCENT if i == current else (FRAME if i < current else DOT)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _arabic_block(
    text: str,
    color_of: dict[int, tuple[int, int, int]],
    background_of: Collection[int] = (),
    top: int = 120,
    text_color: tuple[int, int, int] = INK,
) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    size = ARABIC_SIZE if len(text) > 14 else int(ARABIC_SIZE * 1.6)  # короткое — крупнее
    font = _font(size)
    line_height = int(size * 1.9)
    lines = _wrap(text.split(), font, WIDTH - 2 * PAD - 40)
    height = top + line_height * len(lines) + 120
    img = Image.new("RGB", (WIDTH, max(height, 520)), PAPER)
    draw = _frame(img)
    y = top + (img.height - top - 120 - line_height * len(lines)) // 2
    offset = 0  # номер первого кластера строки во всём тексте
    for line in lines:
        line_width = font.getlength(line, direction="rtl")
        right = (WIDTH + line_width) / 2
        spans = _spans(line, font)
        for k, (a, b) in enumerate(spans):
            if offset + k in background_of:
                draw.rounded_rectangle(
                    (right - b - 6, y + 18, right - a + 6, y + line_height - 18),
                    radius=18,
                    fill=WRONG_BG,
                )
        draw.text(
            (right, y + line_height // 2),
            line,
            font=font,
            fill=text_color,
            anchor="rm",
            direction="rtl",
        )
        for k, (a, b) in enumerate(spans):
            color = color_of.get(offset + k)
            if color is None:
                continue
            layer = Image.new("RGB", img.size, PAPER)
            ImageDraw.Draw(layer).text(
                (right, y + line_height // 2),
                line,
                font=font,
                fill=color,
                anchor="rm",
                direction="rtl",
            )
            box = (int(right - b), y, int(right - a + 1), y + line_height)
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).rectangle(box, fill=255)
            ink = Image.new("L", img.size, 0)
            ImageDraw.Draw(ink).text(
                (right, y + line_height // 2),
                line,
                font=font,
                fill=255,
                anchor="rm",
                direction="rtl",
            )
            img.paste(layer, (0, 0), Image.composite(ink, Image.new("L", img.size, 0), mask))
        offset += len(spans)
        y += line_height
    return img, ImageDraw.Draw(img), y


# ---------- экраны ----------
def card(text: str, accent: Collection[str], position: tuple[int, int]) -> bytes:
    """Карточка урока: строка книги, буква урока красным, точки «карточка k из n»."""
    color_of = dict.fromkeys(accent_clusters(text, accent), ACCENT)
    img, draw, _ = _arabic_block(text, color_of)
    _dots(draw, img.height - 64, position[0], position[1])
    return _png(img)


def result(text: str, wrong: Collection[int], score: int, unread: Collection[int] = ()) -> bytes:
    """Результат в три цвета: верно — зелёным, ошибка — красным на розовом, не прочитано —
    серым. Полоса сверху — цвет оценки."""
    wrong = set(wrong) - set(unread)
    color_of = dict.fromkeys(wrong, ACCENT) | dict.fromkeys(unread, MUTED)
    img, draw, _ = _arabic_block(text, color_of, background_of=wrong, text_color=OK)
    bar = OK if score >= 90 else WARN if score >= 80 else ACCENT
    draw.rectangle((40, 40, 40 + int((WIDTH - 80) * score / 100), 52), fill=bar)
    draw.rectangle((40, 40, WIDTH - 40, 52), outline=MUTED, width=1)
    return _png(img)


def alphabet(rows: Sequence[Sequence[tuple[str, Mark]]]) -> bytes:
    """Карта букв (с. 10 книги): пройдено — зелёные, начато — жёлтые, текущая — красная."""
    size, cell = 92, 150
    title_font = _font(64, bold=True)
    height = 170 + cell * len(rows) + 60
    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = _frame(img)
    draw.text(
        (WIDTH // 2, 100), "مُعَلِّمٌ ثَانِي", font=title_font, fill=INK, anchor="mm", direction="rtl"
    )
    font = _font(size)
    colors = {Mark.DONE: OK, Mark.STARTED: WARN, Mark.NEW: MUTED, Mark.CURRENT: ACCENT}
    for r, row in enumerate(rows):
        y = 170 + r * cell + cell // 2
        n = len(row)
        for i, (letter, mark) in enumerate(row):
            x = WIDTH // 2 + (n - 1) * cell // 2 - i * cell  # справа налево
            if mark is Mark.DONE:
                draw.ellipse((x - 58, y - 58, x + 58, y + 58), fill=(225, 241, 226))
            if mark is Mark.CURRENT:
                draw.ellipse((x - 58, y - 58, x + 58, y + 58), outline=ACCENT, width=4)
            draw.text((x, y), letter, font=font, fill=colors[mark], anchor="mm")
    return _png(img)


def letters(text: str) -> bytes:
    """Строка таблицы алфавита (с. 10): буквы по отдельности, крупно, справа налево."""
    row = text.split()
    cell = (WIDTH - 2 * PAD) // max(len(row), 1)
    img = Image.new("RGB", (WIDTH, 420), PAPER)
    draw = _frame(img)
    font = _font(130)
    for i, letter in enumerate(row):
        x = WIDTH - PAD - cell // 2 - i * cell
        draw.text((x, 210), letter, font=font, fill=INK, anchor="mm")
    return _png(img)


# Знаки огласовки на букве ب — номер под каждым совпадает с объяснением в подписи (screens.SIGNS)
SIGN_EXAMPLES = ("بَ", "بِ", "بُ", "بْ", "بّ", "بً", "بٍ", "بٌ", "بَا", "بِي", "بُو", "ٱ")


def signs() -> bytes:
    """Таблица знаков: 12 примеров в 3 ряда справа налево, под каждым — номер."""
    cols, cell_w, cell_h = 4, (WIDTH - 2 * PAD) // 4, 280
    rows = -(-len(SIGN_EXAMPLES) // cols)
    img = Image.new("RGB", (WIDTH, 110 + rows * cell_h + 40), PAPER)
    draw = _frame(img)
    font, small = _font(120), _font(40, bold=True)
    for i, text in enumerate(SIGN_EXAMPLES):
        r, c = divmod(i, cols)
        x = WIDTH - PAD - cell_w // 2 - c * cell_w
        y = 90 + r * cell_h
        draw.text(
            (x, y + 95),
            text,
            font=font,
            fill=ACCENT if i == len(SIGN_EXAMPLES) - 1 else INK,
            anchor="mm",
            direction="rtl",
        )
        draw.ellipse((x - 22, y + 218, x + 22, y + 262), fill=FRAME)
        draw.text((x, y + 239), str(i + 1), font=small, fill=PAPER, anchor="mm")
    return _png(img)


def rule(text: str) -> bytes:
    """Карточка правила: пример крупно, без подсветки."""
    img, _, _ = _arabic_block(text, {})
    return _png(img)


# ---------- экраны из макетов (ADR-0050) ----------
# Русские подписи на картинках — PT Sans (ParaType, OFL — assets/fonts/OFL-PTSans.txt): в
# Scheherazade New нет кириллицы. Сами подписи приходят параметрами из texts.py.
GREEN_BG = (225, 241, 226)
GREY_BG = (237, 228, 205)
NON_JOINING = frozenset("اأإآدذرزوؤءة")  # не соединяются со следующей буквой


@cache
def _ui_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "PTSans-Bold.ttf" if bold else "PTSans-Regular.ttf"
    return ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.RAQM)


def letter_forms(
    letter: str, vowels: str, labels: Sequence[str], zone_labels: Sequence[tuple[str, bool]]
) -> bytes:
    """Карточка буквы: формы в слове справа налево (отдельно, в начале, в середине, в конце),
    ниже — буква с огласовками, внизу — зоны звука, нужная выделена.

    ``labels`` — подписи 4 форм в этом порядке; у несоединяемых букв форм две (отдельно, в конце),
    у хамзы — одна.
    """
    tatweel = "ـ"
    if letter == "ء":
        forms = [(letter, labels[0])]
    elif letter in NON_JOINING:
        forms = [(letter, labels[0]), (tatweel + letter, labels[3])]
    else:
        forms = [
            (letter, labels[0]),
            (letter + tatweel, labels[1]),
            (tatweel + letter + tatweel, labels[2]),
            (tatweel + letter, labels[3]),
        ]
    img = Image.new("RGB", (WIDTH, 720), PAPER)
    draw = _frame(img)
    cell = (WIDTH - 2 * PAD) // 4
    x0 = WIDTH // 2 + (len(forms) - 1) * cell // 2
    font, small = _font(130), _ui_font(30)
    for i, (form, label) in enumerate(forms):
        x = x0 - i * cell
        draw.text((x, 150), form, font=font, fill=ACCENT, anchor="mm", direction="rtl")
        draw.text((x, 330), label, font=small, fill=(107, 98, 88), anchor="mm")  # ниже хвостов букв
    draw.line((PAD + 40, 375, WIDTH - PAD - 40, 375), fill=GREY_BG, width=2)
    draw.text((WIDTH // 2, 480), vowels, font=_font(110), fill=INK, anchor="mm", direction="rtl")
    if zone_labels:
        pill_font = _ui_font(28, bold=True)
        widths = [int(pill_font.getlength(t)) + 44 for t, _ in zone_labels]
        x = (WIDTH - sum(widths) - 16 * (len(widths) - 1)) // 2
        for (text, on), w in zip(zone_labels, widths, strict=True):
            box = (x, 625, x + w, 670)
            if on:
                draw.rounded_rectangle(box, radius=22, fill=INK)
            else:
                draw.rounded_rectangle(box, radius=22, outline=GREY_BG, width=2)
            draw.text(
                (x + w // 2, 647), text, font=pill_font, fill=PAPER if on else MUTED, anchor="mm"
            )
            x += w + 16
    return _png(img)


class WordState(StrEnum):
    OK = "ok"
    WRONG = "wrong"
    UNREAD = "unread"


def word_states(text: str, wrong: Collection[int], unread: Collection[int]) -> list[WordState]:
    """Состояние каждого слова строки по кластерам ошибок: хоть одна ошибка — слово неверно;
    все буквы не прочитаны — слово не прочитано."""
    words = text.split()
    of_word: list[list[int]] = [[] for _ in words]
    for n, c in enumerate(clusters(text)):
        of_word[text[: c.start].count(" ") if " " in text else 0].append(n)
    out = []
    for members in of_word:
        if members and all(m in unread for m in members):
            out.append(WordState.UNREAD)
        elif any(m in wrong and m not in unread for m in members):
            out.append(WordState.WRONG)
        else:
            out.append(WordState.OK)
    return out


def result_words(
    text: str,
    states: Sequence[WordState],
    score: int,
    score_label: str,
    swap: tuple[str, str, str, str, str] | None = None,
) -> bytes:
    """Разбор по словам: верные — зелёные плашки, неверное — красная с рамкой, непрочитанные —
    серые. ``swap`` — (нужная буква, прозвучавшая, «нужна», «вместо», «прозвучала»)."""
    words = text.split()
    font = _font(84)
    pad_x, gap, chip_h = 26, 18, 150
    widths = [int(font.getlength(w, direction="rtl")) + 2 * pad_x for w in words]
    rows: list[list[int]] = [[]]
    used = 0
    for i, w in enumerate(widths):
        if rows[-1] and used + gap + w > WIDTH - 2 * PAD:
            rows.append([])
            used = 0
        used += (gap if rows[-1] else 0) + w
        rows[-1].append(i)
    height = 130 + len(rows) * (chip_h + gap) + (190 if swap else 40) + 40
    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = _frame(img)
    bar = OK if score >= 90 else WARN if score >= 80 else ACCENT  # цвет — по баллу, как в result()
    label_font = _ui_font(30, bold=True)
    label_w = int(label_font.getlength(score_label)) + 30
    draw.text((PAD, 72), score_label, font=label_font, fill=INK, anchor="lm")
    left, right = PAD + label_w, WIDTH - PAD
    draw.rounded_rectangle((left, 64, right, 80), radius=8, fill=GREY_BG)
    share = sum(1 for s in states if s is WordState.OK) / max(len(states), 1)  # как в подписи
    draw.rounded_rectangle((left, 64, left + int((right - left) * share), 80), 8, fill=bar)
    y = 120
    fills = {WordState.OK: GREEN_BG, WordState.WRONG: WRONG_BG, WordState.UNREAD: GREY_BG}
    inks = {WordState.OK: OK, WordState.WRONG: ACCENT, WordState.UNREAD: MUTED}
    for row in rows:
        total = sum(widths[i] for i in row) + gap * (len(row) - 1)
        x = (WIDTH + total) // 2  # справа налево
        for i in row:
            box = (x - widths[i], y, x, y + chip_h)
            state = states[i] if i < len(states) else WordState.OK
            draw.rounded_rectangle(box, radius=18, fill=fills[state])
            if state is WordState.WRONG:
                draw.rounded_rectangle(box, radius=18, outline=ACCENT, width=4)
            draw.text(
                (x - widths[i] // 2, y + chip_h // 2),
                words[i],
                font=font,
                fill=inks[state],
                anchor="mm",
                direction="rtl",
            )
            x -= widths[i] + gap
        y += chip_h + gap
    if swap:
        need, heard, need_label, instead, heard_label = swap
        small, big = _ui_font(28), _font(90)
        cy = y + 85
        for cx, letter, label, color in (
            (WIDTH // 2 - 190, need, need_label, OK),  # «нужна ص вместо прозвучала س» слева направо
            (WIDTH // 2 + 190, heard, heard_label, ACCENT),
        ):
            draw.rounded_rectangle(
                (cx - 120, cy - 80, cx + 120, cy + 80), radius=18, fill=(255, 255, 255)
            )
            draw.rounded_rectangle(
                (cx - 120, cy - 80, cx + 120, cy + 80), radius=18, outline=GREY_BG, width=2
            )
            draw.text((cx, cy - 15), letter, font=big, fill=color, anchor="mm")
            draw.text((cx, cy + 55), label, font=small, fill=(107, 98, 88), anchor="mm")
        draw.text((WIDTH // 2, cy), instead, font=small, fill=INK, anchor="mm")
    return _png(img)


def postcard(
    medal: str, title: str, subtitle: str, week: Sequence[bool] = (), streak: str = ""
) -> bytes:
    """Открытка «урок пройден»: золотая медаль с буквой урока, название, неделя и серия.

    Без имени и псевдонима: открытку пересылают (ADR-0050).
    """
    height = 720 if (week or streak) else 560
    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = _frame(img)
    cx, cy, r = WIDTH // 2, 210, 130
    for k in range(r, 0, -2):  # мягкий градиент золота от края к центру
        t = k / r
        light = (244, 227, 176)
        color = tuple(int(a + (b - a) * (1 - t)) for a, b in zip(FRAME, light, strict=True))
        draw.ellipse((cx - k, cy - k, cx + k, cy + k), fill=color)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(180, 142, 54), width=5)
    draw.ellipse((cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12), outline=PAPER, width=3)
    arabic = any("؀" <= ch <= "ۿ" for ch in medal)
    medal_font = _font(150) if arabic else _ui_font(96, bold=True)
    direction = "rtl" if arabic else None
    left, top, right, bottom = draw.textbbox((0, 0), medal, font=medal_font, direction=direction)
    # по видимым границам, а не по строке шрифта: у буквы с хвостом центр строки ниже глаза
    draw.text(
        (cx - (left + right) / 2, cy - (top + bottom) / 2),
        medal,
        font=medal_font,
        fill=(122, 31, 31),
        direction=direction,
    )
    draw.text((cx, 400), title, font=_ui_font(52, bold=True), fill=INK, anchor="mm")
    draw.text((cx, 465), subtitle, font=_ui_font(32), fill=(107, 98, 88), anchor="mm")
    if week:
        gap = 44
        x0 = cx - (len(week) - 1) * gap // 2
        for i, active in enumerate(week):
            x = x0 + i * gap
            draw.ellipse((x - 14, 535, x + 14, 563), fill=OK if active else GREY_BG)
    if streak:
        draw.text((cx, 620), streak, font=_ui_font(34, bold=True), fill=INK, anchor="mm")
    return _png(img)


def book_progress(
    parts: Sequence[tuple[str, int, int]], week: Sequence[bool], day_labels: Sequence[str]
) -> bytes:
    """Прогресс по книге: полоса на каждую часть (зелёная — пройдена, жёлтая — начата) и неделя
    занятий (последний день — сегодня, обведён)."""
    row_h = 62
    height = 90 + row_h * len(parts) + (200 if week else 40)
    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = _frame(img)
    font, num = _ui_font(32), _ui_font(30)
    name_w, num_w = 470, 110
    for k, (name, done, total) in enumerate(parts):
        y = 90 + k * row_h
        draw.text((PAD, y), name, font=font, fill=INK, anchor="lm")
        left, right = PAD + name_w, WIDTH - PAD - num_w
        draw.rounded_rectangle((left, y - 11, right, y + 11), radius=6, fill=GREY_BG)
        if done:
            color = OK if done >= total else WARN
            draw.rounded_rectangle(
                (left, y - 11, left + max(22, int((right - left) * done / total)), y + 11),
                radius=6,
                fill=color,
            )
        draw.text((WIDTH - PAD, y), f"{done}/{total}", font=num, fill=MUTED, anchor="rm")
    if week:
        y = 90 + row_h * len(parts) + 40
        cell = (WIDTH - 2 * PAD) // len(week)
        for i, (active, label) in enumerate(zip(week, day_labels, strict=True)):
            x = PAD + cell * i + cell // 2
            draw.text((x, y), label, font=_ui_font(26), fill=MUTED, anchor="mm")
            box = (x - 40, y + 25, x + 40, y + 105)
            draw.rounded_rectangle(box, radius=14, fill=OK if active else GREY_BG)
            if i == len(week) - 1:
                draw.rounded_rectangle(box, radius=14, outline=ACCENT, width=4)
    return _png(img)


def opening(lines: Sequence[str]) -> bytes:
    """Начало занятия: истиаза и басмала, каждая отдельной строкой (остановка после каждой)."""
    font, line_h = _font(92), 190
    img = Image.new("RGB", (WIDTH, 120 + line_h * len(lines)), PAPER)
    draw = _frame(img)
    for k, line in enumerate(lines):
        y = 60 + line_h // 2 + k * line_h + 30
        draw.text((WIDTH // 2, y), line, font=font, fill=INK, anchor="mm", direction="rtl")
    return _png(img)
