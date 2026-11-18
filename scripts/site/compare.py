"""Страница «Муаллим 2.0: сравнение» → docs/site/build/compare.html (uv run python scripts/site/compare.py).

Концепт ChatGPT (картинка), наши виджеты v1 и итог v2 — живые, с имитацией TelegramWidget.
Размер виджетов считаем так же, как сервер Telegram: zlib, уровень 9. Только stdlib.
"""

import base64
import html
import json
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIDGETS = ROOT / "docs" / "design" / "widgets"
TEMPLATE = ROOT / "docs" / "site" / "compare.tpl.html"
CONCEPT = ROOT / "docs" / "site" / "build" / "concept.jpg"  # сжатая копия muallim-2.0-eight-screens
OUT = ROOT / "docs" / "site" / "build" / "compare.html"
LIMIT = 4096

LETTERS = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"  # пример состояния; в боте приходит с сервера
SYL = ["بَ", "تَ", "ثَ", "بِ", "تِ", "ثِ", "بُ", "تُ", "ثُ"]
LESSON = {"v": 1, "l": 1, "k": 2, "a": "ب ت ث", "d": "4:32", "w": SYL}
PATH = {"v": 1, "L": LETTERS, "m": "DDDC" + "N" * 24, "n": 3, "t": 28, "u": 1, "U": 3, "k": 2}

V1 = [
    ("lesson", "Урок (v1)", {"l": 1, "k": 5, "p": 2, "v": 1, "a": [
        {"a": "ب", "n": "باء", "s": ["بَ", "بِ", "بُ"]},
        {"a": "ت", "n": "تاء", "s": ["تَ", "تِ", "تُ"]},
    ], "w": SYL, "r": []}),
    ("streak", "Серия (v1)", {"k": 5, "t": 4, "d": "1111000"}),
    ("map", "Карта (v1)", {"m": "DDDC" + "N" * 24, "k": 2}),
    ("milestone", "Веха (v1)", {"k": 21, "u": 28}),
]  # fmt: skip

VIDEO = (
    '<div class="msg"><div class="vid"><div class="su"><span>русские субтитры</span></div>'
    '<div class="pl">▶</div><div class="du">4:32</div></div>'
    '<div class="txt">Видео-урок: <span class="ar">ب ت ث</span> · живая речь</div></div>'
)
BARS = "".join(f'<i style="height:{h}px"></i>' for h in (8, 16, 20, 11, 18, 9, 16, 13, 20, 10))
VOICE_BOT = (
    f'<div class="msg"><div class="voice"><div class="p">▶</div><div class="w">{BARS}</div>'
    '<small>0:02 · запись учителя <span class="ar">بَ</span></small></div></div>'
)
VOICE_ME = (
    f'<div class="msg me"><div class="voice"><div class="p">▶</div><div class="w">{BARS}</div>'
    "<small>0:14</small></div></div>"
)
FEEDBACK = (
    "🟡 <b>Попытка принята!</b> 7 из 9 слогов верно. Послушайте ещё раз "
    '<span class="ar">ثَ</span> и <span class="ar">ثُ</span>: нажмите на них в разборе.'
)

V2 = [
    ("home", {"v": 1, "st": "Этап I", "ss": "Буквы и огласовки", "n": 3, "t": 28, "k": 2,
              "nx": "Урок 2"}, "", "Муаллим · Этап I: 3 из 28 · серия 2 дня",
     "Главная", "Одна главная кнопка, серия, «n из 28» с сервера. Две второстепенные кнопки."),
    ("lesson", {**LESSON, "s": 1}, VIDEO, "Урок 1 · шаг 1 из 4: посмотрите видео выше",
     "Шаг 1 · видео", "Видео — обычное сообщение. Виджет под ним ждёт «Видео просмотрено»."),
    ("lesson", {**LESSON, "s": 2}, "", "Урок 1 · шаг 2 из 4: слова урока",
     "Шаг 2 · слова", "Нажатие на слово — бот присылает запись учителя (ниже)."),
    ("lesson", {**LESSON, "s": 3}, "", "Урок 1 · шаг 3 из 4: пришлите голосовое",
     "Шаг 3 · попытка", "Записи в виджете нет: ученик пишет голосовое микрофоном Telegram."),
    ("lesson", {**LESSON, "s": 4, "r": [1, 1, 0, 1, 1, 0, 1, 1, 1]}, "", FEEDBACK,
     "Шаг 4 · разбор", "✓ / ! из ответа бэкенда, замечания — в подписи. Повторить или дальше."),
    ("path", {**PATH, "tab": 1}, "", "Карта букв: 3 из 28",
     "Карта букв", "Буквы и порядок приходят с сервера. Пройденную можно повторить."),
    ("path", {**PATH, "tab": 2}, "", "Прогресс: 3 из 28 · уроков 1 из 3 · серия 2 дня",
     "Прогресс", "Только настоящие метрики, без выдуманных достижений."),
    ("milestone", {"v": 1, "t": 28, "u": 28, "k": 21, "s2": 1}, "",
     "Веха пройдена: все 28 букв", "Веха 28/28", "Конфетти только здесь; Этап II — если открыт."),
]  # fmt: skip

PHONE_TOP = (
    '<div class="top"><div class="ava">م</div><div><div class="nm">Муаллим</div>'
    '<div class="sb">бот</div></div></div>'
)


def _widget(key: str, state: object, caption: str) -> str:
    data = html.escape(json.dumps(state, ensure_ascii=False), quote=True)
    return (
        f'<div class="msg"><div class="wb" data-w="{key}" data-state="{data}"></div>'
        f'<div class="txt dim">{caption}</div></div>'
    )


def _figure(chat: str, title: str, note: str) -> str:
    return (
        f'<figure><div class="phone">{PHONE_TOP}<div class="chat">{chat}</div></div>'
        f'<div class="log">журнал: нажмите в виджете</div>'
        f'<div class="cap"><b>{title}</b><span>{note}</span></div></figure>'
    )


def _v2() -> str:
    out = []
    for i, (name, state, before, caption, title, note) in enumerate(V2):
        chat = before + _widget(f"v2/{name}", state, caption)
        if i == 2:
            chat += VOICE_BOT
        if i == 3:
            chat += VOICE_ME
        out.append(_figure(chat, title, note))
    return "\n".join(out)


def _v1() -> str:
    return "\n".join(
        _figure(_widget(f"v1/{name}", state, title), title, "прошлая версия")
        for name, title, state in V1
    )


def _sources() -> dict[str, str]:
    found = {f"v1/{p.stem}": p for p in sorted(WIDGETS.glob("*.html"))}
    found |= {f"v2/{p.stem}": p for p in sorted((WIDGETS / "v2").glob("*.html"))}
    return {k: p.read_text(encoding="utf-8") for k, p in found.items()}


def _sizes(sources: dict[str, str]) -> str:
    rows = []
    for key, text in sources.items():
        raw = len(text.encode())
        packed = len(zlib.compress(text.encode(), 9))
        cells = (key, raw, packed, LIMIT - packed)
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return "\n".join(rows)


def build() -> Path:
    sources = _sources()
    concept = "data:image/jpeg;base64," + base64.b64encode(CONCEPT.read_bytes()).decode()
    page = TEMPLATE.read_text(encoding="utf-8")
    parts = {
        "__CONCEPT__": concept,
        "__V1__": _v1(),
        "__V2__": _v2(),
        "__SIZES__": _sizes(sources),
        "__WIDGETS__": json.dumps(sources, ensure_ascii=False).replace("</", "<\\/"),
    }
    for key, value in parts.items():
        page = page.replace(key, value)
    OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    print(out.relative_to(ROOT), out.stat().st_size, "байт")
