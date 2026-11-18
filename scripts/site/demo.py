"""Демонстрация для профессоров (англ.) → docs/site/build/demo.html.

Шаблон docs/site/demo.tpl.html; живые виджеты — docs/design/widgets/v2/*.html, тот же код,
что пойдёт в бот. Только stdlib.
"""

import json
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIDGETS = ROOT / "docs" / "design" / "widgets" / "v2"
TEMPLATE = ROOT / "docs" / "site" / "demo.tpl.html"
OUT = ROOT / "docs" / "site" / "build" / "demo.html"
LIMIT = 4096

BARS = "".join(f'<i style="height:{h}px"></i>' for h in (8, 16, 20, 11, 18, 9, 16, 13, 20, 10))
PARTS = {
    "__VIDEO__": (
        '<div class="msg"><div class="vid"><div class="lt">ا ب ت</div>'
        '<div class="su"><span>subtitles</span></div><div class="pl">▶</div>'
        '<div class="du">4:32</div></div>'
        '<div class="txt">Lesson 1 · <span class="ar">ا ب ت</span> · teacher video</div></div>'
    ),
    "__VOICE_T__": (
        f'<div class="msg"><div class="voice"><div class="p">▶</div><div class="w">{BARS}</div>'
        '<small>0:02 · teacher\'s recording <span class="ar">بَ</span></small></div></div>'
    ),
    "__VOICE_ME__": (
        f'<div class="msg me"><div class="voice"><div class="p">▶</div><div class="w">{BARS}</div>'
        "<small>0:12</small></div></div>"
    ),
}


def build() -> Path:
    sources = {p.stem: p.read_text(encoding="utf-8") for p in sorted(WIDGETS.glob("*.html"))}
    for name, text in sources.items():
        packed = len(zlib.compress(text.encode(), 9))
        if packed > LIMIT:
            raise SystemExit(f"{name}: {packed} байт после сжатия, лимит {LIMIT}")
        print(f"{name}: {len(text.encode())} → {packed} байт")
    page = TEMPLATE.read_text(encoding="utf-8")
    for key, value in PARTS.items():
        page = page.replace(key, value)
    page = page.replace(
        "__WIDGETS__", json.dumps(sources, ensure_ascii=False).replace("</", "<\\/")
    )
    OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build().relative_to(ROOT))
