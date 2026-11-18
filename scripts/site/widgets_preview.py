"""Страница «Бот на виджетах» из docs/design/widgets/*.html (uv run python scripts/site/widgets_preview.py).

Размер считаем так же, как сервер Telegram: zlib, уровень 9. Только stdlib.
"""

import json
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIDGETS = ROOT / "docs" / "design" / "widgets"
TEMPLATE = ROOT / "docs" / "site" / "widgets-preview.tpl.html"
OUT = ROOT / "docs" / "site" / "build" / "widgets.html"
LIMIT = 4096
NAMES = {
    "lesson": "Урок",
    "streak": "Серия",
    "map": "Карта",
    "milestone": "Веха",
}
SAMPLE_STATES = {
    "lesson": {
        "l": 1, "k": 5, "p": 3, "v": 3,
        "a": [{"a": "ب", "n": "باء", "s": ["بَ", "بِ", "بُ"]}] * 3,
        "w": ["بَ", "تَ", "ثَ", "بِ", "تِ", "ثِ", "بُ", "تُ", "ثُ"],
        "r": [1, 1, 0, 1, 1, 1, 1, 0, 1],
    },
    "streak": {"k": 5, "t": 4, "d": "1111000"},
    "map": {"m": "D" * 11 + "C" + "N" * 16, "k": 5},
    "milestone": {"k": 21, "u": 28},
}  # fmt: skip


def _size_rows(sources: dict[str, str]) -> str:
    rows = []
    for key, html in sources.items():
        raw = len(html.encode())
        packed = len(zlib.compress(html.encode(), 9))
        cells = (NAMES[key], raw, packed, LIMIT - packed)
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return "\n".join(rows)


def _state_rows() -> str:
    rows = []
    for key, state in SAMPLE_STATES.items():
        text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        rows.append(
            f"<tr><td>{NAMES[key]}</td><td><code>{text}</code></td>"
            f"<td>{len(text.encode())} байт из 1024</td></tr>"
        )
    return "\n".join(rows)


def build() -> Path:
    sources = {k: (WIDGETS / f"{k}.html").read_text(encoding="utf-8") for k in NAMES}
    payload = json.dumps(sources, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("__WIDGETS__", payload)
    page = page.replace("__SIZES__", _size_rows(sources))
    page = page.replace("__STATES__", _state_rows())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build().relative_to(ROOT))
