"""Собирает curriculum/course.ru.yaml из расшифровки всей книги (SRC-040, с. 10–85), в порядке книги.

    uv run --extra ml python scripts/book/build.py

Урок = раздел книги (длинные разделы делятся на части до LINES_PER_LESSON строк). Перед разделом —
карточка «📘 Правило» (объяснение своими словами, не текст книги). Карточка = строка книги или
одна фраза/аят из Корана (точный текст мусхафа, ссылка сура:аят — для эталона «как правильно»).
Программа — «только человек»: после пересборки человек сверяет огласовки и ставит verified.
"""

import sys
from pathlib import Path

import yaml
from quran_transcript import Aya

sys.path.insert(0, str(Path(__file__).parent))
import letters
import qmatch
import rules
import theory
from quran import Q
from texts import ACCENT, PARTS, RULES, TITLES

ROOT = Path(__file__).resolve().parents[2]
LINES_PER_LESSON = 8
SRC = "SRC-040"

SURAS = {  # страница книги -> суры на ней (с. 75–85)
    75: [1], 76: [2], 77: [93, 94], 78: [95, 96], 79: [97, 98], 80: [99, 100], 81: [101, 102],
    82: [103, 104, 105], 83: [106, 107, 108], 84: [109, 110, 111], 85: [112, 113, 114],
}  # fmt: skip
AYA_PAGE = {(98, 8): 80, (100, 10): 81, (100, 11): 81}
SURA_RU = {
    1: "аль-Фатиха", 2: "аль-Бакара, 1–5", 93: "ад-Духа", 94: "аш-Шарх", 95: "ат-Тин", 96: "аль-Алак",
    97: "аль-Кадр", 98: "аль-Баййина", 99: "аз-Зальзаля", 100: "аль-Адийат", 101: "аль-Кариа",
    102: "ат-Такасур", 103: "аль-Аср", 104: "аль-Хумаза", 105: "аль-Филь", 106: "Курайш",
    107: "аль-Маун", 108: "аль-Каусар", 109: "аль-Кафирун", 110: "ан-Наср", 111: "аль-Масад",
    112: "аль-Ихлас", 113: "аль-Фаляк", 114: "ан-Нас",
}  # fmt: skip


def src(page: int, line: int, note: str = "") -> dict:
    out = {"source_id": SRC, "page": page, "line": line, "verified": False}
    if note:
        out["note"] = note
    return out


def quran_phrase(spec: str) -> tuple[str, str]:
    """(точный текст, «сура:аят») для записи из quran.py."""
    if spec.startswith("#"):
        s, a = (int(x) for x in spec[1:].split(":"))
        return Aya(s, a).get().uthmani, f"{s}:{a}"
    if ":" in spec and "@" not in spec:
        _, text = spec.split(":", 1)
        return text, ""
    hits = qmatch.find(spec)
    if not hits:
        raise SystemExit(f"Нет в мусхафе: {spec!r}")
    s, a, text = hits[0]
    return text, f"{s}:{a}"


def sections() -> list[tuple[str, list[dict]]]:
    """Все карточки книги по порядку, сгруппированные по разделам (подряд идущие ключи)."""
    out: list[tuple[str, list[dict]]] = []

    def add(key: str, card: dict) -> None:
        if not out or out[-1][0] != key:
            out.append((key, []))
        out[-1][1].append(card)

    # Начало: истиаза (не из книги, но так начинают чтение) и басмала (с. 10, строка 1)
    fatiha = Aya(1, 1).get()
    add(
        "start",
        {
            "kind": "line",
            "text": fatiha.istiaatha_uthmani,
            "quran": "",
            "source": src(10, 1, "истиаза — перед чтением Корана (в книге не напечатана)"),
        },
    )
    add("start", {"kind": "line", "text": fatiha.uthmani, "quran": "1:1", "source": src(10, 1)})

    # с. 10–24: алфавит, хамза, буквы по одной
    for page in sorted(letters.LETTER_PAGES):
        for n, (key, kind, text) in enumerate(letters.LETTER_PAGES[page], start=1):
            if key == "start":
                continue
            if kind == "alphabet":
                add(
                    "alphabet",
                    {
                        "kind": "alphabet",
                        "text": text,
                        "name": letters.NAMES[text],
                        "source": src(page, n),
                    },
                )
                continue
            card = {
                "kind": "letter" if kind == letters.H else "line",
                "text": text,
                "source": src(page, n),
            }
            if kind == letters.N:
                card["note"] = "Обратите внимание: пары похожих слов"
            add(f"letter:{key}", card)

    # с. 25–74: слоги и слова (rules.py) и примеры из Корана по одной фразе (quran.py) — по страницам
    events: list[tuple[int, int, int, str, dict]] = []
    for page in sorted(rules.PAGES):
        for n, (key, kind, text) in enumerate(rules.PAGES[page], start=1):
            if key is None:
                continue
            card = {"kind": "line", "text": text, "source": src(page, n)}
            if kind == rules.H:
                card["note"] = "Образец"
            events.append((page, n, 0, key, card))
    for (page, line), (key, phrases) in Q.items():
        for k, spec in enumerate(phrases, start=1):
            text, ref = quran_phrase(spec)
            note = f"фраза {k} из {len(phrases)}" + (f" · Коран {ref}" if ref else "")
            card = {"kind": "line", "text": text, "quran": ref, "source": src(page, line, note)}
            events.append((page, line, k, key, card))
    for _, _, _, key, card in sorted(events, key=lambda e: e[:3]):
        add(key, card)

    # с. 75–85: суры
    for page, suras in sorted(SURAS.items()):
        for s in suras:
            first = Aya(s, 1).get()
            last = 5 if s == 2 else first.num_ayat_in_sura
            if s != 1:
                add(
                    f"sura:{s}",
                    {
                        "kind": "line",
                        "text": Aya(1, 1).get().uthmani,
                        "quran": "1:1",
                        "source": src(page, 1, "басмала перед сурой"),
                    },
                )
            for a in range(1, last + 1):
                p = AYA_PAGE.get((s, a), page)
                add(
                    f"sura:{s}",
                    {
                        "kind": "line",
                        "text": Aya(s, a).get().uthmani,
                        "quran": f"{s}:{a}",
                        "source": src(p, a, f"сура {SURA_RU[s]}, аят {a}"),
                    },
                )
    return out


def lessons() -> list[dict]:
    old = yaml.safe_load((ROOT / "curriculum" / "course.ru.yaml").read_text("utf-8"))
    heads = {
        it["text"]: it
        for les in old["lessons"]
        for it in les["items"]
        if it.get("kind") == "letter"
    }
    out: list[dict] = []
    for key, cards in sections():
        base = key.split(":")[0]
        if base == "letter":
            letter = key.split(":")[1]
            head = heads[cards[0]["text"]]
            cards[0].update(name=head["name"], sound=head["sound"], tip=head["tip"])
            shown = head["text"] if letter == "ء" else letter  # в книге с. 10 — أَ إِ أُ на элифе
            title = f"{shown} · {head['name']}"
            accent = letters_accent(letter)
            cards = letter_lesson(letter, cards)
        elif base == "sura":
            title = f"Сура {SURA_RU[int(key.split(':')[1])]}"
            accent = ""
        else:
            title = TITLES[base]
            accent = ACCENT.get(base, "")
        rule = None if base == "letter" else RULES.get(key) or RULES.get(base)
        if base == "sura" and any(les["section"] == "sura" for les in out):
            rule = None  # правило про суры — только перед первой
        practice = [c for c in cards if c["kind"] not in ("alphabet",)]
        if base in ("letter", "alphabet", "start") or len(practice) <= LINES_PER_LESSON + 2:
            chunks = [cards]
        else:  # поровну: 20 строк → 7+7+6, а не 8+8+4
            k = -(-len(cards) // LINES_PER_LESSON)
            size = -(-len(cards) // k)
            chunks = [cards[i : i + size] for i in range(0, len(cards), size)]
        for part, chunk in enumerate(chunks, start=1):
            n = len(out) + 1
            lid = f"L{n:03}"
            items = []
            if rule and part == 1:
                items.append(
                    {
                        "kind": "rule",
                        "text": rule[0],
                        "name": rule[1],
                        "tip": rule[2],
                        "source": dict(chunk[0]["source"], note="правило — своими словами"),
                    }
                )
            items += chunk
            for i, it in enumerate(items, start=1):
                it["id"] = f"{lid}-{i:02}"
            suffix = f" ({part}/{len(chunks)})" if len(chunks) > 1 else ""
            out.append(
                {
                    "id": lid,
                    "number": n,
                    "title": f"{n}. {title}{suffix}",
                    "kind": "line",
                    "accent": accent,
                    "section": base,
                    "part": PART_OF[base],
                    "source": {
                        "source_id": SRC,
                        "page": chunk[0]["source"]["page"],
                        "verified": False,
                    },
                    "items": [order(it) for it in items],
                }
            )
    return out


PART_OF = {section: name for name, keys in PARTS for section in keys}


def letter_lesson(letter: str, cards: list[dict]) -> list[dict]:
    """Урок буквы (ADR-0032): «как произносить» → каждая огласовка отдельно → строка книги.

    В уроке хамзы (первая буква) вместо «как произносить» — правила огласовок, и каждое стоит
    перед своей карточкой: так ученик учит «а», «и», «у» по одной, а не все вместе.
    """
    head = cards[0]
    source = head["source"]

    def rule(spec: tuple[str, str, str]) -> dict:
        text, name, tip = spec
        return {
            "kind": "rule",
            "text": text,
            "name": name,
            "tip": tip,
            "source": dict(source, note="правило — своими словами"),
        }

    sounds = head["sound"].split(" · ")
    out: list[dict] = []
    if letter == "ء":
        out += [rule(theory.VOWEL_RULES["overview"]), rule(theory.VOWEL_RULES["hamza"])]
    else:
        out.append(
            rule((letter, f"Как произносить {letter} · {head['name']}", theory.LETTERS[letter]))
        )
    for k, (syllable, vowel) in enumerate(zip(head["text"].split(), theory.VOWELS, strict=True)):
        if letter == "ء":
            out.append(rule(theory.VOWEL_RULES[vowel]))
        out.append(
            {
                "kind": "syllable",
                "text": syllable,
                "name": head["name"],
                "sound": sounds[k],
                "tip": theory.syllable_tip(letter, vowel),
                "source": dict(source, note="слог из строки книги — отдельно"),
            }
        )
    if letter == "ء":
        out.append(rule(theory.VOWEL_RULES["short"]))
    return out + cards


def letters_accent(letter: str) -> str:
    return "ءأإؤئآ" if letter == "ء" else letter


def order(item: dict) -> dict:
    keys = ("id", "kind", "text", "name", "sound", "tip", "note", "quran", "source")
    return {k: item[k] for k in keys if item.get(k)}


CONTENTS = [  # оглавление книги (с. 86) -> разделы программы
    ("Введение", 5, []), ("Предисловие", 6, []),
    ("Арабский алфавит", 10, ["start", "alphabet", "letter"]),
    ("Буквы «мадд»", 25, ["madd"]), ("Упражнения", 27, ["exercises"]),
    ("Буквы с «ташдидом» (удвоением)", 30, ["tashdid"]), ("Буквы с «танвином»", 32, ["tanwin"]),
    ("Встреча «танвина» с «ташдидом»", 34, ["tanwin_tashdid"]),
    ("Виды написания буквы «хэмзэ»", 35, ["hamza", "wasla", "ta_marbuta"]),
    ("Положение двух соседних букв, над первой из которых имеется «сукун»", 38, ["sukun"]),
    ("Присоединение к словам определённого артикля", 41, ["article"]),
    ("Буква م с «сукуном»", 43, ["mim"]),
    ("ن с «сукуном» и «танвин»", 45, ["noon_izhar", "noon_idgham", "noon_ikhfa", "iqlab"]),
    ("«Калькаля»", 54, ["qalqala"]), ("Маленькие буквы, встречающиеся в Коране", 55, ["small"]),
    ("Положение ي, которой предшествует «фатха»", 57, ["ya_alif"]),
    ("Положение و с маленьким ا", 57, ["waw_alif"]), ("Буквы, которые не читаются", 58, ["silent"]),
    ("Огласовка «кясрой» буквы ن с «сукуном»", 62, ["noon_kasra"]),
    ("Остановка и её знаки", 63, ["waqf"]), ("«Сакт»", 65, ["sakt"]),
    ("Виды «мадд». Удлинение гласного звука", 67, ["madd_types"]),
    ("Раздельные буквы, приходящие в начале сур", 70, ["muqattaat"]),
    ("Чёрный кружок в Коране; порядковые знаки", 73, ["signs"]),
    ("Суры для чтения", 75, ["sura"]), ("Оглавление", 86, []),
]  # fmt: skip


def write_contents(lessons_: list[dict]) -> None:
    rows = []
    for title, page, keys in CONTENTS:
        ids = [les["id"] for les in lessons_ if les["section"] in keys]
        rows.append({"title": title, "page": page, "sections": keys, "lessons": ids})
    head = (
        "# Оглавление рабочего издания (SRC-040, book/README.md) и уроки бота по каждому разделу.\n"
        "# Страницы — по нумерации книги (PDF = страница + 1). Генерируется scripts/book/build.py.\n"
    )
    body = yaml.safe_dump(
        {"edition": SRC, "sections": rows},
        allow_unicode=True,
        sort_keys=False,
        width=120,
        default_flow_style=None,
    )
    (ROOT / "book" / "contents.yaml").write_text(head + body, encoding="utf-8")


def main() -> None:
    doc = {
        "id": "al-muallim-al-thani-ru",
        "version": "2026.10.21-book-5",
        "title": "Муаллим сани — вся книга Максуди",
        "source": {
            "source_id": SRC,
            "page": 10,
            "verified": False,
            "note": "Вся книга, с. 10–85, в порядке книги. Сборка: scripts/book/build.py",
        },
        "lessons": lessons(),
    }
    header = (Path(__file__).parent / "HEADER.txt").read_text("utf-8")
    path = ROOT / "curriculum" / "course.ru.yaml"
    with path.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=110)
    write_contents(doc["lessons"])
    n_items = sum(len(les["items"]) for les in doc["lessons"])
    print(f"{len(doc['lessons'])} уроков, {n_items} карточек → {path}")


if __name__ == "__main__":
    main()
