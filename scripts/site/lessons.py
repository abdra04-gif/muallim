"""Демонстрация уроков для профессоров (англ.) → docs/site/build/lessons.html.

Урок = страница книги. Русские объяснения, слоги и строки — из curriculum/course.ru.yaml (то же, что
показывает бот). Цитаты книги, переводы и вопросы — docs/site/lessons-content.yaml (правится там).
Виджеты — docs/design/widgets/v3: их код и пойдёт в бот.
"""

import base64
import json
import re
import unicodedata
import zlib
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
COURSE = ROOT / "curriculum" / "course.ru.yaml"
CONTENT = ROOT / "docs" / "site" / "lessons-content.yaml"
WIDGETS = ROOT / "docs" / "design" / "widgets" / "v3"
ASSETS = ROOT / "docs" / "site" / "build" / "assets"
PAGES = ROOT / "curriculum" / "book_pages"
TEMPLATE = ROOT / "docs" / "site" / "lessons.tpl.html"
SCRIPT = ROOT / "docs" / "site" / "lessons.sim.js"
OUT = ROOT / "docs" / "site" / "build" / "lessons.html"
LIMIT = 4096
STATE_LIMIT = 1024
PART_LINES = 2
LAST_FILLED_PAGE = 12  # с. 10–12 заполнены вручную, дальше — по программе
LETTERS = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
LANGS = ("ru", "en")
Card = dict[str, Any]
Course = dict[str, dict[str, Any]]
C: dict[str, Any] = yaml.safe_load(CONTENT.read_text(encoding="utf-8"))
HIGHLIGHT_RA = [["مِّن ", 0], ["رَّ", 1], ["بِّهِمْ", 0]]


def _course() -> Course:
    found: Course = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if str(node.get("id", "")).startswith("L") and "title" in node:
                found.setdefault(str(node["id"]), node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(yaml.safe_load(COURSE.read_text(encoding="utf-8")))
    return found


def _items(course: Course, lid: str, kind: str) -> list[dict[str, Any]]:
    return [it for it in course[lid].get("items", []) if it.get("kind") == kind]


def _lines(course: Course, ids: list[str]) -> list[list[str]]:
    return [str(it["text"]).split() for lid in ids for it in _items(course, lid, "line")]


def _letter_card(course: Course, lid: str, ch: str, lg: str) -> Card:
    card: Card = {
        "h": C["ui"][lg]["letter"].replace("#", ch),
        "a": _items(course, lid, "letter")[0]["text"],
        "s": [it["text"] for it in _items(course, lid, "syllable")],
    }
    if ch in C["book"]:  # цитата книги и объяснение есть пока для букв уроков 1–3
        card["w"] = C["book"][ch][lg]
        card["e"] = C[f"explain_{lg}"][ch]
    return card


def _lesson1_cards(course: Course, lg: str) -> list[Card]:
    vowels = {lg: C[f"explain_{lg}"]["vowels"] for lg in LANGS}
    hamza = {lg: C[f"explain_{lg}"]["ء"] for lg in LANGS}
    syllables = ["أَ", "إِ", "أُ"]
    return [
        {"h": C["ui"][lg]["vowels"], "a": "أَ إِ أُ", "e": vowels[lg], "s": syllables},
        {
            "h": C["ui"][lg]["hamza"],
            "a": "ا أَ",
            "w": C["book"]["ء"][lg],
            "e": hamza[lg],
            "s": syllables,
        },
    ]


def _rule_cards(lg: str) -> list[Card]:
    cards: list[Card] = [{"h": r[f"title_{lg}"], "a": r["arabic"], "w": r[lg]} for r in C["rule50"]]
    quiz = C["quiz"][lg]
    cards.append({"h": quiz["question"], "a": HIGHLIGHT_RA, "q": quiz["options"]})
    return cards


def _rule49_card(lg: str) -> Card:
    title = {"ru": "Идгам без гунны", "en": "Idgham without ghunna"}
    return {"h": title[lg], "a": HIGHLIGHT_RA, "w": C["rule49"][lg]}


VOWELS = {"\u064e": ("фатха", "fatha"), "\u0650": ("кясра", "kasra"), "\u064f": ("дамма", "damma")}
INSTR = {"\u064e": "фатхой", "\u0650": "кясрой", "\u064f": "даммой"}
SHAPE = {
    "\u064e": ("чёрточка над буквой", "a stroke above the letter"),
    "\u0650": ("чёрточка под буквой", "a stroke below the letter"),
    "\u064f": ("маленький و над буквой", "a small و above the letter"),
}
SWAP = {"\u064e": "\u0650", "\u0650": "\u064e", "\u064f": "\u064e"}  # что «прозвучало» в примере
TIP = {
    "\u064e": ("рот открыт, звук короткий", "the mouth is open, the vowel is short"),
    "\u0650": ("губы слегка растянуты, звук короткий", "the lips are slightly spread, short"),
    "\u064f": ("губы округлены, звук короткий", "the lips are rounded, short"),
}
ORDINAL = (("первый", "first"), ("второй", "second"), ("третий", "third"), ("четвёртый", "fourth"))


def _base_index(word: str, i: int) -> int:
    """Индекс буквы, к которой относится знак в позиции i (знаки — категория Mn)."""
    j = i - 1
    while j > 0 and unicodedata.category(word[j]) == "Mn":
        j -= 1
    return j


def _seat(base: str, vowel: str) -> str:
    """Хамза пишется под алифом только с кясрой."""
    if base in "أإ":
        return "إ" if vowel == "\u0650" else "أ"
    return base


def _mistake(word: str, li: int) -> dict[str, Any]:
    """Пример ошибки для демо: заменена огласовка первой огласованной буквы; без фонем."""
    for i, ch in enumerate(word):
        if ch in VOWELS:
            new = SWAP[ch]
            k = _base_index(word, i)
            base = word[k]
            heard = word[:k] + _seat(base, new) + word[k + 1 : i] + new + word[i + 1 :]
            need, got = VOWELS[ch], VOWELS[new]
            syl, bad = _seat(base, ch) + ch, _seat(base, new) + new
            letter = "ا" if base in "أإ" else base
            nth = ORDINAL[min(3, sum(unicodedata.category(c) != "Mn" for c in word[:k]))]
            ru = (
                f"В слове {word} {nth[0]} слог — {syl}: {need[0]} ({SHAPE[ch][0]}), "
                f"{TIP[ch][0]}. Вы прочитали {bad} — как с {INSTR[new]}."
            )
            en = (
                f"In {word} the {nth[1]} syllable is {syl}: {need[1]} ({SHAPE[ch][1]}), "
                f"{TIP[ch][1]}. You read {bad}, as with {got[1]}."
            )
            return {"w": word, "h": heard, "li": li, "s": syl, "b": bad, "l": letter,
                    "ru": ru, "en": en}  # fmt: skip
    return {"w": word, "h": word, "li": li, "s": "", "b": "", "l": "",
            "ru": "Послушайте учителя.", "en": "Listen to the teacher."}  # fmt: skip


def _parts(course: Course, spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Что читать вслух: урок делится на части по буквам (одна часть = строки одной буквы)."""
    groups = spec.get("parts") or [[spec["ids"], ""]]
    parts, start = [], 0
    for ids, letter in groups:
        count = len(_lines(course, ids))
        end = start + count  # не больше двух строк за раз
        parts += [
            {"lt": letter, "a": a, "z": min(a + PART_LINES, end)} for a in range(start, end, 2)
        ]
        start += count
    return parts


def _deep(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Видео к каждой букве: урок по книге (C["book_short"]) и произношение (C["swaid"])."""
    deep = []
    for ch in dict.fromkeys(spec.get("letters", "").replace(" ", "")):
        letter = "ا" if ch in "أإء" else ch
        if any(d["l"] == letter for d in deep):
            continue
        if letter in C["swaid"]:
            deep.append({"l": letter, "k": "sw", **C["swaid"][letter]})
        if letter in C["book_short"]:
            deep.append({"l": letter, "k": "ms", **C["book_short"][letter]})
    return deep


def _lesson(course: Course, spec: dict[str, Any], cards: dict[str, list[Card]]) -> dict[str, Any]:
    kind = "alphabet" if spec.get("alpha") else "line"
    lines = [str(it["text"]).split() for lid in spec["ids"] for it in _items(course, lid, kind)]
    marks = [[1] * len(line) for line in lines]
    for li, wi in spec["wrong"]:
        marks[li][wi] = 0
    label = (
        "Stage II example"
        if spec.get("extra")
        else "The alphabet"
        if spec.get("alpha")
        else f"Lesson {spec['n']}"
    )
    return {
        **spec,
        "pageFile": f"{spec['page']:03d}",
        "videos": C["videos"].get(spec["page"], []),
        "label": f"{label} · page {spec['page']}",
        "labelRu": (
            "Пример Этапа II"
            if spec.get("extra")
            else "Алфавит"
            if spec.get("alpha")
            else f"Урок {spec['n']}"
        )
        + f" · стр. {spec['page']}",
        "lines": lines,
        "marks": marks,
        "mistakes": [_mistake(lines[li][wi], li) for li, wi in spec["wrong"]],
        "parts": [{"lt": "", "a": 0, "z": len(lines)}]
        if spec.get("alpha")
        else _parts(course, spec),
        "crops": [
            f"line{spec['page']:03d}-{i + 1}"
            for i in range(len(C["line_crops"].get(spec["page"], [])))
        ],
        "where": [
            {"l": ch, "ru": C["book"][ch]["ru"], "en": C["book"][ch]["en"]}
            for ch in spec.get("where", "")
        ],
        "deep": _deep(spec),
        "rule": False,
        "cards": cards,
    }


def _pages(course: Course) -> list[dict[str, Any]]:
    l2 = [("L004", "ر"), ("L005", "ز"), ("L006", "م")]
    l3 = [("L007", "ت"), ("L008", "ن")]
    lesson1 = {
        "n": 1, "page": 10, "ids": ["L003"], "letters": "أَ إِ أُ", "wrong": [(0, 3)],
        "after": 1, "where": "ء", "titleEn": "Hamza on alif with fatha, kasra and damma", "titleRu": "Хамза на алифе с фатхой, кясрой и даммой",
    }  # fmt: skip
    lesson2 = {
        "n": 2, "page": 11, "ids": ["L004", "L005", "L006"], "letters": "ر ز م",
        "wrong": [(1, 4), (3, 7)], "after": 4, "where": "رزم",
        "parts": [[["L004"], "ر"], [["L005"], "ز"], [["L006"], "م"]],
        "titleEn": "Three new letters: ra, zay, mim", "titleRu": "Три новые буквы: ра, зай, мим",
    }  # fmt: skip
    lesson3 = {
        "n": 3, "page": 12, "ids": ["L007", "L008"], "letters": "ت ن", "wrong": [(0, 2), (4, 1)],
        "parts": [[["L007"], "ت"], [["L008"], "ن"]], "after": 6, "where": "تن",
        "titleEn": "Two new letters: ta, nun", "titleRu": "Две новые буквы: та, нун",
    }  # fmt: skip
    page49 = {
        "n": "", "page": 49, "ids": ["L062"], "letters": "", "extra": True, "wrong": [(2, 1)],
        "after": 28, "titleEn": "Stage II example: idgham without ghunna", "titleRu": "Пример Этапа II: идгам без гунны",
    }  # fmt: skip
    alphabet = {
        "n": 0, "page": 10, "ids": ["L002"], "alpha": True, "letters": "", "wrong": [],
        "after": 0, "titleEn": "The alphabet: all 28 letters", "titleRu": "Алфавит: все 28 букв",
    }  # fmt: skip
    pages = [
        _lesson(course, alphabet, {lg: [] for lg in LANGS}),
        _lesson(course, lesson1, {lg: _lesson1_cards(course, lg) for lg in LANGS}),
        _lesson(
            course, lesson2, {lg: [_letter_card(course, i, c, lg) for i, c in l2] for lg in LANGS}
        ),
        _lesson(
            course, lesson3, {lg: [_letter_card(course, i, c, lg) for i, c in l3] for lg in LANGS}
        ),
        _lesson(course, page49, {lg: [_rule49_card(lg)] for lg in LANGS}),
    ]
    pages += _auto_pages(course)
    pages.append({
        "n": "", "page": 50, "pageFile": "050", "letters": "", "extra": True, "rule": True,
        "label": "Rule page · page 50", "labelRu": "Правило · стр. 50", "titleEn": "Rule page: signs of idgham in the Quran", "titleRu": "Правило: знаки идгама в Коране",
        "lines": [], "marks": [], "mistakes": [], "parts": [], "after": 28, "deep": [],
        "videos": C["videos"][50],
        "cards": {lg: _rule_cards(lg) for lg in LANGS},
        "quiz": {lg: {"ok": C["quiz"][lg]["right"], "no": C["quiz"][lg]["wrong"]} for lg in LANGS},
    })  # fmt: skip
    return pages


def _auto_pages(course: Course) -> list[dict[str, Any]]:
    """Уроки 4–15 (с. 13–24) по программе бота: строки и слоги — как есть, без примеров ошибок."""
    by_page: dict[int, list[tuple[str, str]]] = {}
    for lid, lesson in course.items():
        if lesson.get("section") == "letter" and int(lesson["source"]["page"]) > LAST_FILLED_PAGE:
            by_page.setdefault(int(lesson["source"]["page"]), []).append((lid, lesson["accent"]))
    pages = []
    for page, pairs in sorted(by_page.items()):
        _page_image(page)
        spec = {
            "n": page - 9, "page": page, "ids": [lid for lid, _ in pairs], "auto": True,
            "letters": " ".join(ch for _, ch in pairs), "wrong": [], "after": 0,
            "parts": [[[lid], ch] for lid, ch in pairs],
            "titleEn": "Letters " + " ".join(ch for _, ch in pairs),
            "titleRu": "Буквы " + " ".join(ch for _, ch in pairs),
        }  # fmt: skip
        cards = {lg: [_letter_card(course, lid, ch, lg) for lid, ch in pairs] for lg in LANGS}
        pages.append(_lesson(course, spec, cards))
    return pages


def _page_image(page: int) -> None:
    out = ASSETS / f"page{page:03d}.jpg"
    if not out.exists():
        image = Image.open(PAGES / f"{page:03d}.jpg").convert("RGB")
        image.thumbnail((537, 760))
        image.save(out, quality=78)


def _check_states(pages: list[dict[str, Any]]) -> None:
    worst = 0
    for page in pages:
        for lg, cards in page["cards"].items():
            for card in cards:
                state = {"lg": lg, "l": page["n"], "pg": page["page"], "i": 9, "N": 9, "c": card}
                text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
                size = len(text.encode())
                worst = max(worst, size)
                if size > STATE_LIMIT:
                    raise SystemExit(f"с. {page['page']} ({lg}): {size} байт > {STATE_LIMIT}")
    print(f"самое большое состояние карточки: {worst} байт из {STATE_LIMIT}")


def _stage1(course: Course) -> list[list[Any]]:
    """Уроки Этапа I по страницам книги: [номер, страница, буквы, статус после уроков 1–3]."""
    by_page: dict[int, str] = {}
    for lesson in course.values():
        if lesson.get("section") == "letter":
            page = int(lesson["source"]["page"])
            by_page[page] = by_page.get(page, "") + str(lesson.get("accent") or "")
    rows = []
    for n, page in enumerate(sorted(by_page), start=1):
        letters = "أ" if page == 10 else " ".join(by_page[page])
        rows.append([n, page, letters, "D" if n <= 3 else "C" if n == 4 else "N"])
    return rows


PARTS_EN = {
    1: "Introduction", 2: "Letters and vowel marks", 3: "Long vowels", 4: "Shadda and tanwin",
    5: "Hamza, the article, sukun", 6: "Mim and nun", 7: "Features of Quranic script",
    8: "Stopping and madd", 9: "Surahs",
}  # fmt: skip


def _book(course: Course) -> list[dict[str, Any]]:
    """Вся книга по частям: урок = страница (ADR-0084), страницы без уроков — «только правило»."""
    page_part: dict[int, int] = {}
    part_ru: dict[int, str] = {}
    label: dict[int, str] = {}
    for lesson in course.values():
        if "source" not in lesson or not lesson.get("part"):
            continue
        num = int(str(lesson["part"]).split(".")[0])
        if num == 1:  # «Знакомство» — та же с. 10, что и первый урок букв
            continue
        page = int(lesson["source"]["page"])
        page_part.setdefault(page, num)
        part_ru[num] = str(lesson["part"]).split(". ", 1)[1]
        accent = str(lesson.get("accent") or "") if num == 2 else ""
        title = re.sub(r" \(\d+/\d+\)$", "", str(lesson["title"]).split(". ", 1)[-1])
        label.setdefault(page, accent if accent else title)
        if num == 2 and accent:
            label[page] = "".join(dict.fromkeys(label[page] + accent))
    parts: list[dict[str, Any]] = []
    for page in range(10, 86):
        num = page_part.get(page) or page_part.get(page - 1) or page_part.get(page + 1) or 9
        if not parts or parts[-1]["n"] != num:
            parts.append({"n": num, "ru": part_ru[num], "en": PARTS_EN[num], "pages": []})
        text = label.get(page, "")
        if page == 10:
            text = "أ"
        elif num == 2:
            text = " ".join(text)
        parts[-1]["pages"].append([page - 9, page, text, 0 if page in label else 1])
    return parts


def _cells(text: str) -> list[str]:
    """Клетки разметки: буква со своими знаками (ADR-0079), пробел — граница слов."""
    cells: list[str] = []
    for ch in text:
        if ch == " ":
            cells.append(" ")
        elif cells and cells[-1] != " " and unicodedata.category(ch) == "Mn":
            cells[-1] += ch
        else:
            cells.append(ch)
    return cells


def _annotation(course: Course) -> list[dict[str, Any]]:
    tasks = []
    for t in C["annotation"]:
        line = _items(course, t["lesson"], "line")[t["line"] - 1]["text"]
        cells = _cells(line)
        conf = {int(k): v for k, v in t.get("conf", {}).items()}
        cf = "".join(
            " " if ch == " " else conf[i][0] if i in conf else "g" for i, ch in enumerate(cells)
        )
        det = {str(i): v[1:] for i, v in conf.items()}
        tasks.append({"pg": t["page"], "li": t["page_line"], "c": cells, "cf": cf, "det": det,
                      "bv": t["bot"]})  # fmt: skip
    return tasks


VOWEL_MARKS = ("\u064e", "\u0650", "\u064f")


def _letters(course: Course) -> dict[str, dict[str, Any]]:
    """Карточка каждой из 28 букв: урок и страница книги, слоги, цитата книги (если есть)."""
    info: dict[str, dict[str, Any]] = {}
    for n, page, letters, _ in _stage1(course):
        for raw in letters.split():
            ch = "ا" if raw == "أ" else raw
            seat = "ء" if ch == "ا" else ch
            syl = [_seat("أ", v) + v if ch == "ا" else ch + v for v in VOWEL_MARKS]
            card: dict[str, Any] = {"n": n, "pg": page, "s": syl}
            if seat in C["book"]:
                card["q"] = {lg: C["book"][seat][lg] for lg in LANGS}
                card["e"] = {lg: C[f"explain_{lg}"][seat] for lg in LANGS}
            info[ch] = card
    return info


def _crops() -> None:
    """Строки для чтения — вырезки из скана книги (ADR-0084), а не набранный текст."""
    scale = 1287 / 760  # координаты в C["line_crops"] — по превью высотой 760
    for page, boxes in C["line_crops"].items():
        image = Image.open(PAGES / f"{page:03d}.jpg")
        width = image.size[0]
        for i, (top, bottom) in enumerate(boxes, start=1):
            box = (int(width * 0.09), int(top * scale), int(width * 0.91), int(bottom * scale))
            crop = image.crop(box).convert("RGB")
            crop.save(ASSETS / f"line{page:03d}-{i}.jpg", quality=82)


def _map(done: str, current: str) -> str:
    return "".join("D" if ch in done else "C" if ch == current else "N" for ch in LETTERS)


def _data() -> dict[str, Any]:
    course = _course()
    pages = _pages(course)
    _check_states(pages)
    groups = ["ا", "رزم", "تن"]
    letter_lesson = {str(LETTERS.index(ch)): i for i, chars in enumerate(groups) for ch in chars}
    info = _letters(course)
    by_n = {str(p["n"]): i for i, p in enumerate(pages) if p["n"] != ""}
    by_n.update({"40": 4, "41": len(pages) - 1})
    return {
        "lessons": pages, "letters": LETTERS, "letterLesson": letter_lesson, "info": info, "ay": C["abu_yasin"],
        "idx49": 4, "idx50": len(pages) - 1, "byN": by_n,
        "stage1": [[0, 10, "ا ب ت ث …", "N"], *_stage1(course)], "review": C["review"],
        "book": _book(course), "annot": _annotation(course),
        "start": {"n": 0, "m": _map("", "ا"), "nl": 0, "np": 10, "k": 2},
        "after": {"n": 6, "m": _map("ارزمتن", "ي"), "nl": 4, "np": 13},
    }  # fmt: skip


def _widgets() -> dict[str, str]:
    sources = {p.stem: p.read_text(encoding="utf-8") for p in sorted(WIDGETS.glob("*.html"))}
    for name, text in sources.items():
        packed = len(zlib.compress(text.encode(), 9))
        if packed > LIMIT:
            raise SystemExit(f"{name}: {packed} байт после сжатия, лимит {LIMIT}")
        print(f"{name}: {len(text.encode())} → {packed} байт")
    return sources


def _images() -> dict[str, str]:
    _crops()
    return {
        p.stem: "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        for p in sorted(ASSETS.glob("*.jpg"))
    }


def _js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _bilingual(page: str) -> str:
    """[[English||Русский]] в шаблоне → две версии; видна та, что выбрана переключателем языка страницы."""
    page = re.sub(
        r"\[\[(.*?)\|\|(.*?)\]\]",
        r'<span class="le">\1</span><span class="lr">\2</span>',
        page,
        flags=re.S,
    )
    if "[[" in page or "||" in page.split("<script>")[0]:
        raise SystemExit("шаблон: незакрытая пара [[en||ru]]")
    return page


def build() -> Path:
    page = _bilingual(TEMPLATE.read_text(encoding="utf-8"))
    script = SCRIPT.read_text(encoding="utf-8")
    page = page.replace("__SCRIPT__", "<script>\n" + script + "</script>\n")
    page = page.replace("__WIDGETS__", _js(_widgets()))
    page = page.replace("__DATA__", _js(_data()))
    page = page.replace("__IMG__", _js(_images()))
    OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    print(out.relative_to(ROOT), out.stat().st_size, "байт")
