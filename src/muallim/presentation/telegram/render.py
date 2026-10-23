"""Картинки для Telegram: строка книги крупно, буква урока красным, ошибки подсвечены (ADR-0024).

Telegram не умеет крупный шрифт и цвет в тексте, поэтому арабский текст рисуется картинкой
шрифтом Scheherazade New (SIL, OFL — assets/fonts): огласовки крупно и прямо над буквой.
Строка рисуется целиком (правильное соединение букв), а отдельные буквы перекрашиваются
полосой по их точным границам: граница буквы — ширина начала строки с ZWJ на конце
(буква в той же форме, что внутри слова).

Нужен Pillow с libraqm (на macOS: brew install fribidi; в Docker: libfribidi0). Без него
``available()`` → False, и бот показывает текстовые карточки.
"""

import io
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from muallim.application.breakdown import VOWEL_KINDS, Breakdown, ErrorGroup
from muallim.domain import arabic
from muallim.domain.assessment import ErrorKind
from muallim.presentation.telegram import texts, views

# Разбор строки — из домена (FR-54): те же объекты, а не копия.
HAMZA_FORMS = arabic.HAMZA_FORMS
MADD_LETTERS = arabic.MADD_LETTERS
PHONEME_OF = arabic.PHONEME_OF
SHADDA = arabic.SHADDA
Cluster = arabic.Cluster
WordState = arabic.WordState
clusters = arabic.clusters
consonant_clusters = arabic.consonant_clusters
error_clusters = arabic.error_clusters
unread_clusters = arabic.unread_clusters
word_states = arabic.word_states

FONTS = Path(__file__).parent / "assets" / "fonts"
ZWJ = "‍"
TATWEEL = "ـ"  # носитель знака, когда букв много

# Холст не шире 900 px (FR-48): Telegram сжимает картинку до ширины сообщения (~360 pt на
# телефоне), и на широком холсте буквы и огласовки мельчают. Шрифт — крупнее относительно ширины,
# длинная строка переносится, поля по бокам — только рамка.
WIDTH = 900
PAD = 40
TEXT_WIDTH = WIDTH - 2 * PAD - 40  # ширина строки арабского текста внутри рамки
ARABIC_SIZE = 112
SHORT_SIZE = 168  # короткая строка (слог, слово) — ещё крупнее
# ⚙️ «Крупный шрифт» (FR-51, ADR-0061): буквы карточки крупнее, холст по-прежнему 900 px —
# длинная строка просто переносится на большее число строк.
LARGE_SCALE = 1.3

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
# Одна реализация на домен и картинку (FR-54): здесь — реэкспорт из ``domain.arabic``.
def accent_clusters(text: str, letters: Collection[str]) -> set[int]:
    return {n for n, c in enumerate(clusters(text)) if c.base in letters}


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
    gap = min(26, TEXT_WIDTH // (total - 1))
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
    *,
    scale: float = 1.0,
) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    size = round((ARABIC_SIZE if len(text) > 14 else SHORT_SIZE) * scale)  # короткое — крупнее
    font = _font(size)
    line_height = int(size * 1.9)
    lines = _wrap(text.split(), font, TEXT_WIDTH)
    height = top + line_height * len(lines) + 120
    img = Image.new("RGB", (WIDTH, max(height, 440)), PAPER)
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
def card(
    text: str, accent: Collection[str], position: tuple[int, int], scale: float = 1.0
) -> bytes:
    """Карточка урока: строка книги, буква урока красным, точки «шаг k из n».

    ``scale`` — множитель шрифта (``LARGE_SCALE`` — «Крупный шрифт»), ширина та же.
    """
    color_of = dict.fromkeys(accent_clusters(text, accent), ACCENT)
    img, draw, _ = _arabic_block(text, color_of, top=96, scale=scale)
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
    widest = max((len(row) for row in rows), default=1)
    cell = min(120, (WIDTH - 2 * PAD) // max(widest, 1))
    size, r0 = cell * 2 // 3, cell * 2 // 5
    title_font = _font(56, bold=True)
    height = 150 + cell * len(rows) + 50
    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = _frame(img)
    draw.text(
        (WIDTH // 2, 88), "مُعَلِّمٌ ثَانِي", font=title_font, fill=INK, anchor="mm", direction="rtl"
    )
    font = _font(size)
    colors = {Mark.DONE: OK, Mark.STARTED: WARN, Mark.NEW: MUTED, Mark.CURRENT: ACCENT}
    for r, row in enumerate(rows):
        y = 150 + r * cell + cell // 2
        n = len(row)
        for i, (letter, mark) in enumerate(row):
            x = WIDTH // 2 + (n - 1) * cell // 2 - i * cell  # справа налево
            if mark is Mark.DONE:
                draw.ellipse((x - r0, y - r0, x + r0, y + r0), fill=GREEN_BG)
            if mark is Mark.CURRENT:
                draw.ellipse((x - r0, y - r0, x + r0, y + r0), outline=ACCENT, width=4)
            draw.text((x, y), letter, font=font, fill=colors[mark], anchor="mm")
    return _png(img)


def letters(text: str) -> bytes:
    """Строка таблицы алфавита (с. 10): буквы по отдельности, крупно, справа налево."""
    row = text.split()
    cell = (WIDTH - 2 * PAD) // max(len(row), 1)
    img = Image.new("RGB", (WIDTH, 360), PAPER)
    draw = _frame(img)
    font = _font(min(120, cell * 9 // 10))  # широкие буквы (ث ب) не слипаются
    for i, letter in enumerate(row):
        x = WIDTH - PAD - cell // 2 - i * cell
        draw.text((x, 180), letter, font=font, fill=INK, anchor="mm")
    return _png(img)


# Знаки огласовки на букве ب — номер под каждым совпадает с объяснением в подписи (screens.SIGNS)
SIGN_EXAMPLES = ("بَ", "بِ", "بُ", "بْ", "بّ", "بً", "بٍ", "بٌ", "بَا", "بِي", "بُو", "ٱ")


def signs() -> bytes:
    """Таблица знаков: 12 примеров в 3 ряда справа налево, под каждым — номер."""
    cols, cell_w, cell_h = 4, (WIDTH - 2 * PAD) // 4, 280
    rows = -(-len(SIGN_EXAMPLES) // cols)
    img = Image.new("RGB", (WIDTH, 100 + rows * cell_h + 30), PAPER)
    draw = _frame(img)
    font, small = _font(116), _font(40, bold=True)
    for i, text in enumerate(SIGN_EXAMPLES):
        r, c = divmod(i, cols)
        x = WIDTH - PAD - cell_w // 2 - c * cell_w
        y = 70 + r * cell_h
        draw.text(
            (x, y + 95),
            text,
            font=font,
            fill=ACCENT if i == len(SIGN_EXAMPLES) - 1 else INK,
            anchor="mm",
            direction="rtl",
        )
        draw.ellipse((x - 22, y + 222, x + 22, y + 266), fill=FRAME)
        draw.text((x, y + 243), str(i + 1), font=small, fill=PAPER, anchor="mm")
    return _png(img)


def rule(text: str, scale: float = 1.0) -> bytes:
    """Карточка правила: пример крупно, без подсветки."""
    img, _, _ = _arabic_block(text, {}, top=96, scale=scale)
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


def _fit(text: str, size: int, width: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Подпись PT Sans: шрифт уменьшается, пока строка не влезет в ``width`` (не мельче 18)."""
    while size > 18 and _ui_font(size, bold).getlength(text) > width:
        size -= 2
    return _ui_font(size, bold)


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
    img = Image.new("RGB", (WIDTH, 680), PAPER)
    draw = _frame(img)
    cell = (WIDTH - 2 * PAD) // 4
    x0 = WIDTH // 2 + (len(forms) - 1) * cell // 2
    font = _font(124)
    small = _fit(max(labels, key=len), 30, cell - 12)
    for i, (form, label) in enumerate(forms):
        x = x0 - i * cell
        draw.text((x, 140), form, font=font, fill=ACCENT, anchor="mm", direction="rtl")
        draw.text((x, 312), label, font=small, fill=(107, 98, 88), anchor="mm")  # ниже хвостов букв
    draw.line((PAD + 40, 352, WIDTH - PAD - 40, 352), fill=GREY_BG, width=2)
    # огласовки — по видимым границам посередине между чертой (352) и плашками зон (590):
    # у высокой связки «أُ» центр строки шрифта ниже глаза, и дамма наезжала на черту
    vowel_font = _font(116)
    left, top, right, bottom = draw.textbbox((0, 0), vowels, font=vowel_font, direction="rtl")
    draw.text(
        (WIDTH // 2 - (left + right) / 2, 471 - (top + bottom) / 2),
        vowels,
        font=vowel_font,
        fill=INK,
        direction="rtl",
    )
    if zone_labels:
        pill_font = _ui_font(28, bold=True)
        widths = [int(pill_font.getlength(t)) + 44 for t, _ in zone_labels]
        x = (WIDTH - sum(widths) - 16 * (len(widths) - 1)) // 2
        for (text, on), w in zip(zone_labels, widths, strict=True):
            box = (x, 590, x + w, 635)
            if on:
                draw.rounded_rectangle(box, radius=22, fill=INK)
            else:
                draw.rounded_rectangle(box, radius=22, outline=GREY_BG, width=2)
            draw.text(
                (x + w // 2, 612), text, font=pill_font, fill=PAPER if on else MUTED, anchor="mm"
            )
            x += w + 16
    return _png(img)


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
    font = _font(88)
    pad_x, gap, chip_h = 22, 14, 156
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
    label_font = _fit(score_label, 30, (WIDTH - 2 * PAD) // 2, bold=True)
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
            (WIDTH // 2 - 180, need, need_label, OK),  # «нужна ص вместо прозвучала س» слева направо
            (WIDTH // 2 + 180, heard, heard_label, ACCENT),
        ):
            draw.rounded_rectangle(
                (cx - 110, cy - 80, cx + 110, cy + 80), radius=18, fill=(255, 255, 255)
            )
            draw.rounded_rectangle(
                (cx - 110, cy - 80, cx + 110, cy + 80), radius=18, outline=GREY_BG, width=2
            )
            draw.text((cx, cy - 24), letter, font=big, fill=color, anchor="mm")
            draw.text((cx, cy + 58), label, font=small, fill=(107, 98, 88), anchor="mm")
        draw.text((WIDTH // 2, cy), instead, font=small, fill=INK, anchor="mm")
    return _png(img)


# ---------- разбор попытки группами (FR-54, ADR-0070) ----------
BADGE = 24  # запас над строкой для номеров групп
BADGE_RADIUS = 19
BADGE_STEP = 44  # номера над соседними буквами не помещаются в ряд — следующий ряд выше (I4)
LEGEND_MAX_ROWS = 6  # строк легенды не больше: дальше — texts.LEGEND_MORE (B2)
LEGEND_ROW = 180  # строка легенды: «Нужно:» буква крупно и подпись звука, рядом — «У тебя:»
LEGEND_LETTER = 104  # буква в легенде — крупно (FR-54): ≥ 30 pt на экране телефона
LEGEND_COLUMNS = (300, 590)  # середины колонок «Нужно» и «У тебя»
LEGEND_LABEL_WIDTH = 270
LEGEND_MORE_HEIGHT = 56
Color = tuple[int, int, int]
Box = tuple[int, int, int, int]


def legend_rows(breakdown: Breakdown) -> list[tuple[int, str, str]]:
    """Строка легенды на группу: (номер, нужно, у тебя) — номер совпадает с пунктом текста; не
    больше ``LEGEND_MAX_ROWS`` (длинная строка с десятками ошибок — B2)."""
    groups = breakdown.groups[:LEGEND_MAX_ROWS]
    return [(n, g.need_label, g.heard_label) for n, g in enumerate(groups, start=1)]


def group_numbers(breakdown: Breakdown) -> dict[int, int]:
    """Кластер строки → номер группы (первая группа места главнее): красная буква."""
    out: dict[int, int] = {}
    for n, g in enumerate(breakdown.groups, start=1):
        for place in g.places:
            for cluster in place.clusters:
                out.setdefault(cluster, n)
    return out


def badges(breakdown: Breakdown) -> list[tuple[int, int]]:
    """Номера над буквами: (кластер, номер группы) — над первой буквой каждого места групп из
    легенды. У одной буквы бывает несколько номеров (шадда и огласовка) — каждый виден (I4)."""
    out: dict[tuple[int, int], None] = {}
    for n, g in enumerate(breakdown.groups[:LEGEND_MAX_ROWS], start=1):
        for place in g.places:
            if place.clusters:
                out[(place.clusters[0], n)] = None
    return list(out)


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    right: float
    spans: list[tuple[float, float]]
    origin: tuple[float, int]
    offset: int  # номер первого кластера строки во всём тексте


@dataclass(frozen=True, slots=True)
class _Layout:
    font: ImageFont.FreeTypeFont
    line_height: int
    lines: list[_Line]
    badges: list[tuple[int, Box]]  # (номер, рамка)
    bottom: int


def _layout(text: str, breakdown: Breakdown, top: int) -> _Layout:
    """Вёрстка строки и номеров: номер — над буквой, если рядом уже номер — рядом выше."""
    size = ARABIC_SIZE if len(text) > 14 else SHORT_SIZE
    font = _font(size)
    line_height = int(size * 1.7)
    numbers: dict[int, list[int]] = {}
    for cluster, n in badges(breakdown):
        numbers.setdefault(cluster, []).append(n)
    r, gap = BADGE_RADIUS, 2 * BADGE_RADIUS + 6
    lines, boxes, y, offset = [], [], top, 0
    for line in _wrap(text.split(), font, TEXT_WIDTH):
        right = (WIDTH + font.getlength(line, direction="rtl")) / 2
        spans = _spans(line, font)
        wanted = sorted(
            (right - (a + b) / 2, n)
            for k, (a, b) in enumerate(spans)
            for n in numbers.get(offset + k, [])
        )
        rows: list[list[float]] = []
        placed: list[tuple[int, float, int]] = []  # (ряд, x, номер)
        for cx, n in wanted:
            row = next(
                (i for i, xs in enumerate(rows) if all(abs(cx - x) >= gap for x in xs)), None
            )
            if row is None:
                rows.append([])
                row = len(rows) - 1
            rows[row].append(cx)
            placed.append((row, cx, n))
        extra = max(len(rows) - 1, 0) * BADGE_STEP
        origin = (right, y + BADGE + extra + line_height // 2)
        ink_top = origin[1] + font.getbbox(line, anchor="rm", direction="rtl")[1]
        base = max(ink_top - 32, y + extra + 22)
        for row, cx, n in placed:
            cy = base - row * BADGE_STEP
            boxes.append((n, (int(cx - r), int(cy - r), int(cx + r), int(cy + r))))
        lines.append(_Line(line, right, spans, origin, offset))
        offset += len(spans)
        y += BADGE + extra + line_height
    return _Layout(font, line_height, lines, boxes, y)


def badge_boxes(text: str, breakdown: Breakdown) -> list[tuple[int, Box]]:
    """Где на картинке стоят номера групп: (номер, (x0, y0, x1, y1)); рамки не пересекаются."""
    return _layout(text, breakdown, _TOP).badges


def _is_arabic(ch: str) -> bool:
    return "\u0600" <= ch <= "\u06ff" or "\ufb50" <= ch <= "\ufeff"


def _runs(text: str) -> list[tuple[str, bool]]:
    """Подпись на куски: арабские буквы — шрифтом Scheherazade (в PT Sans их нет), остальное —
    PT Sans."""
    runs: list[tuple[str, bool]] = []
    for ch in text:
        is_arabic = _is_arabic(ch)
        if runs and runs[-1][1] == is_arabic:
            runs[-1] = (runs[-1][0] + ch, is_arabic)
        else:
            runs.append((ch, is_arabic))
    return runs


def _run_font(is_arabic: bool, size: int) -> ImageFont.FreeTypeFont:
    return _font(round(size * 1.4)) if is_arabic else _ui_font(size)


def _mixed_width(text: str, size: int) -> float:
    return sum(
        _run_font(is_arabic, size).getlength(run, direction="rtl" if is_arabic else None)
        for run, is_arabic in _runs(text)
    )


def _mixed(
    draw: ImageDraw.ImageDraw, at: tuple[float, int], text: str, size: int, fill: Color
) -> None:
    """Подпись слева направо от ``at`` (середина строки по высоте): кириллица и арабская буква."""
    x, y = at
    for run, is_arabic in _runs(text):
        font = _run_font(is_arabic, size)
        if is_arabic:  # по видимым границам: у арабской буквы середина строки шрифта ниже глаза
            _, top, _, bottom = draw.textbbox((0, 0), run, font=font, direction="rtl")
            draw.text((x, y - (top + bottom) / 2), run, font=font, fill=fill, direction="rtl")
            x += font.getlength(run, direction="rtl")
        else:
            draw.text((x, y), run, font=font, fill=fill, anchor="lm")
            x += font.getlength(run)


def _badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, n: int) -> None:
    r = 19
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
    draw.text((cx, cy), str(n), font=_ui_font(28, bold=True), fill=PAPER, anchor="mm")


def _recolor(
    img: Image.Image,
    line: str,
    font: ImageFont.FreeTypeFont,
    origin: tuple[float, int],
    paint: tuple[tuple[int, int, int, int], Color],
) -> None:
    """Перекрасить в строке ``line`` только то, что внутри рамки (буква по её границам)."""
    box, color = paint
    layer = Image.new("RGB", img.size, PAPER)
    ImageDraw.Draw(layer).text(origin, line, font=font, fill=color, anchor="rm", direction="rtl")
    ink = Image.new("L", img.size, 0)
    ImageDraw.Draw(ink).text(origin, line, font=font, fill=255, anchor="rm", direction="rtl")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    img.paste(layer, (0, 0), Image.composite(ink, Image.new("L", img.size, 0), mask))


def _marked_text(img: Image.Image, layout: _Layout, breakdown: Breakdown, text: str) -> None:
    """Строка крупно: верные буквы зелёные, ошибка — красная с номером над ней, не дочитанное —
    серое."""
    draw = ImageDraw.Draw(img)
    numbers = group_numbers(breakdown)
    unread_words = set(breakdown.unread)
    unread = {n for n, w in enumerate(arabic.cluster_words(text)) if w in unread_words}
    font, half = layout.font, layout.line_height // 2
    for line in layout.lines:
        draw.text(line.origin, line.text, font=font, fill=OK, anchor="rm", direction="rtl")
        top = line.origin[1] - half
        for k, (a, b) in enumerate(line.spans):
            n = line.offset + k
            color = MUTED if n in unread else ACCENT if n in numbers else None
            if color is not None:
                box = (int(line.right - b), top, int(line.right - a + 1), top + layout.line_height)
                _recolor(img, line.text, font, line.origin, (box, color))
    for n, (x0, y0, x1, y1) in layout.badges:
        _badge(draw, (x0 + x1) / 2, (y0 + y1) / 2, n)


def _glyph(
    draw: ImageDraw.ImageDraw, cx: float, box: tuple[int, int], text: str, fill: Color
) -> None:
    """Буква (слог) крупно шрифтом арабского текста, по видимым границам внутри полосы ``box``:
    хвост ح или ق не наезжает на подпись под ней."""
    top, bottom = box
    if not text:
        draw.text((cx, (top + bottom) / 2), "—", font=_ui_font(48), fill=fill, anchor="mm")
        return
    size = LEGEND_LETTER
    while True:
        font = _font(size)
        left, t, right, b = draw.textbbox((0, 0), text, font=font, direction="rtl")
        if b - t <= bottom - top or size <= 40:
            break
        size -= 6
    x = cx - (left + right) / 2
    y = (top + bottom) / 2 - (t + b) / 2
    draw.text((x, y), text, font=font, fill=fill, direction="rtl")


def _legend_sides(group: ErrorGroup) -> tuple[str, str]:
    """Что рисовать крупно: буквы как в тексте (ة, أ), шадда, или слоги буквы-носителя знака."""
    if group.kind in VOWEL_KINDS:
        carrier = group.carrier or TATWEEL
        return (
            carrier + group.expected if group.expected else carrier,
            carrier + group.heard if group.heard else carrier,
        )
    need = group.letter or ("" if group.kind is ErrorKind.EXTRA_SOUND else group.expected)
    if group.kind is ErrorKind.SHADDA_MISSING:
        return need + SHADDA, need
    if not group.letter and group.kind is not ErrorKind.EXTRA_SOUND:
        need = ""  # звук без буквы в тексте (н танвина) — не рисуем чужую букву (M3)
    return need, group.heard


def _legend(draw: ImageDraw.ImageDraw, breakdown: Breakdown, top: int) -> None:
    """Под чертой — строка на группу: номер, «Нужно:» и буква крупно зелёным, «У тебя:» и буква
    крупно красным, под буквами — подпись звука, справа — сколько раз."""
    draw.line((PAD + 30, top, WIDTH - PAD - 30, top), fill=GREY_BG, width=2)
    y = top + 16
    headings = (
        texts.RESULT_EXPECTED.format(text="").strip(),
        texts.RESULT_HEARD.format(text="").strip(),
    )
    for (n, need, heard), group in zip(legend_rows(breakdown), breakdown.groups, strict=False):
        _badge(draw, PAD + 40, y + LEGEND_ROW // 2 - 8, n)
        sides = zip(
            LEGEND_COLUMNS, headings, _legend_sides(group), (need, heard), (OK, ACCENT), strict=True
        )
        for cx, heading, glyph, label, color in sides:
            draw.text((cx, y + 16), heading, font=_ui_font(26), fill=INK, anchor="mm")
            _glyph(draw, cx, (y + 36, y + 128), glyph, color)
            size = 26
            while size > 18 and _mixed_width(label, size) > LEGEND_LABEL_WIDTH:
                size -= 2
            _mixed(draw, (cx - _mixed_width(label, size) / 2, y + 150), label, size, color)
        if times := views.times(group.times):
            draw.text(
                (WIDTH - PAD - 24, y + LEGEND_ROW // 2 - 8),
                times,
                font=_ui_font(26, bold=True),
                fill=ACCENT,
                anchor="rm",
            )
        y += LEGEND_ROW
    if (more := len(breakdown.groups) - LEGEND_MAX_ROWS) > 0:
        line = texts.LEGEND_MORE.format(n=more)
        draw.text((WIDTH // 2, y + 24), line, font=_ui_font(28), fill=INK, anchor="mm")


_TOP, _TOP_LABEL = 48, 96  # верх строки: без подписи и под подписью «Верно 2 слова из 5»


def result_marks(text: str, breakdown: Breakdown, score_label: str = "") -> bytes:
    """Разбор группами (FR-54): верные буквы зелёные, ошибка — красная только сама буква с
    номером группы над ней, не дочитанное — серое; внизу — строка на группу «нужно / у тебя»
    (не больше ``LEGEND_MAX_ROWS``). Холст 900 px (FR-48); высота растёт с числом групп."""
    layout = _layout(text, breakdown, _TOP_LABEL if score_label else _TOP)
    rows = len(legend_rows(breakdown))
    legend = LEGEND_ROW * rows + 40 if rows else 0
    if len(breakdown.groups) > rows:
        legend += LEGEND_MORE_HEIGHT
    img = Image.new("RGB", (WIDTH, layout.bottom + legend + 50), PAPER)
    draw = _frame(img)
    if score_label:
        label_font = _fit(score_label, 30, WIDTH - 2 * PAD - 40, bold=True)
        draw.text((PAD + 20, 70), score_label, font=label_font, fill=INK, anchor="lm")
    _marked_text(img, layout, breakdown, text)
    if rows:
        _legend(draw, breakdown, layout.bottom + 10)
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
    inner = WIDTH - 2 * PAD - 40
    draw.text((cx, 400), title, font=_fit(title, 52, inner, bold=True), fill=INK, anchor="mm")
    draw.text((cx, 465), subtitle, font=_fit(subtitle, 32, inner), fill=(107, 98, 88), anchor="mm")
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
    num = _ui_font(30)
    name_w, num_w = 400, 90  # название части — слева, полоса — посередине, «3/28» — справа
    for k, (name, done, total) in enumerate(parts):
        y = 90 + k * row_h
        font = _fit(name, 32, name_w - 24)
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
    """Начало занятия: истиаза и басмала, каждая отдельной строкой (остановка после каждой).

    Длинная фраза переносится; между фразами — промежуток шире, чем между строками фразы.
    """
    font, line_h, gap = _font(100), 180, 70
    wrapped = [_wrap(line.split(), font, TEXT_WIDTH) for line in lines]
    rows = sum(len(w) for w in wrapped)
    img = Image.new("RGB", (WIDTH, 100 + line_h * rows + gap * (len(lines) - 1)), PAPER)
    draw = _frame(img)
    y = 50 + line_h // 2
    for k, phrase in enumerate(wrapped):
        if k:  # черта между фразами: здесь остановка
            mid = y - line_h // 2 - gap // 2
            draw.line((WIDTH // 2 - 120, mid, WIDTH // 2 + 120, mid), fill=FRAME, width=2)
        for line in phrase:
            draw.text((WIDTH // 2, y), line, font=font, fill=INK, anchor="mm", direction="rtl")
            y += line_h
        y += gap
    return _png(img)
