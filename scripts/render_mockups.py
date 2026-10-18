"""Страница макетов docs/design/mockups.html из docs/design/screens (make design).

Обычная HTML-страница: картинки встроены (data URI), открывается в любом браузере и публикуется
как артефакт. Подписи и кнопки — из screens.json, то есть ровно то, что показывает бот.
"""

import base64
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "docs" / "design" / "screens"
OUT = ROOT / "docs" / "design" / "mockups.html"

TITLES = {
    "01_home": "Главная", "02_parts": "Уроки: 9 частей книги", "03_part_letters": "Часть 2: буквы",
    "04_rule": "Правило перед разделом", "05_alphabet": "Алфавит (с. 10)", "06_letter": "Буква урока",
    "07_line": "Строка книги", "08_quran": "Аят: эталон Хусари", "09_result_errors": "Ошибки подсвечены",
    "10_result_done": "Урок пройден", "11_quiz": "Закрепление: вопрос", "12_quiz_answer": "Закрепление: ответ",
    "13_signs": "Знаки над и под буквой", "14_progress": "Прогресс", "15_help": "Как заниматься",
    "16_teacher": "Режим учителя",
}  # fmt: skip

CSS = """
:root{--bg:#F3EFE3;--panel:#FFFFFF;--fg:#221E1C;--muted:#5E5850;--line:#D9CFB4;--chat:#D9DFC8;
--btn:#5B6B4E;--btn-fg:#FFFFFF;--gold:#A9862E;
--display:'Noto Serif',Georgia,serif;--body:'Noto Sans','Noto Naskh Arabic',system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1B1A17;--panel:#2A2824;--fg:#F1ECE0;
--muted:#B9B2A3;--line:#4A453B;--chat:#2F3529;--btn:#6F8160;--btn-fg:#FFFFFF;--gold:#D4B05A;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#1B1A17;--panel:#2A2824;--fg:#F1ECE0;--muted:#B9B2A3;--line:#4A453B;
--chat:#2F3529;--btn:#6F8160;--btn-fg:#FFFFFF;--gold:#D4B05A;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:15px}
.wrap{max-width:1400px;margin:0 auto;padding-block:32px 64px;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-family:var(--display);font-weight:600;font-size:clamp(28px,4vw,42px);margin:0;text-wrap:balance}
.lead{color:var(--muted);max-width:70ch;line-height:1.5;margin:8px 0 0}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--gold);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:28px;margin-top:32px}
figure{margin:0;display:flex;flex-direction:column;gap:10px;min-width:0}
figcaption{font-weight:600;font-size:15px}
.phone{background:var(--chat);border:1px solid var(--line);border-radius:26px;overflow:hidden;
display:flex;flex-direction:column;min-height:620px}
.top{background:var(--panel);padding:12px 14px;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--line)}
.ava{width:36px;height:36px;border-radius:18px;background:var(--gold);color:#fff;display:grid;place-items:center;font-size:20px}
.name{font-weight:700;font-size:15px}.sub{font-size:12px;color:var(--muted)}
.chat{flex:1;padding:10px;display:flex;flex-direction:column;justify-content:flex-end;gap:6px}
.msg{background:var(--panel);border-radius:14px;overflow:hidden}
.msg img{display:block;width:100%}
.cap{padding:10px 12px;line-height:1.45;font-size:14px;white-space:pre-line;overflow-wrap:anywhere}
.spoiler{background:var(--muted);color:transparent;border-radius:4px;transition:color .2s}
.spoiler:hover{background:transparent;color:inherit}
.cap blockquote{margin:6px 0 0;padding-left:8px;border-left:3px solid var(--gold);color:var(--muted);font-size:13px}
.row{display:flex;gap:6px}
.row span{flex:1;background:var(--btn);color:var(--btn-fg);border-radius:10px;padding:9px 6px;text-align:center;font-size:13px;font-weight:600}
"""


def caption(text: str) -> str:
    # подписи бота — HTML Telegram (<b>, <i>, <blockquote>): оставляем только эти теги
    safe = html.escape(text)
    for tag in ("b", "i", "u"):
        safe = safe.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    safe = re.sub(r"&lt;blockquote[^&]*&gt;", "<blockquote>", safe).replace(
        "&lt;/blockquote&gt;", "</blockquote>"
    )
    # спойлер Telegram — в макете серой плашкой, текст виден при наведении
    return safe.replace("&lt;tg-spoiler&gt;", '<span class="spoiler">').replace(
        "&lt;/tg-spoiler&gt;", "</span>"
    )


def main() -> None:
    meta = json.loads((SCREENS / "screens.json").read_text("utf-8"))
    cards = []
    for name, m in meta.items():
        img = ""
        if m["image"]:
            data = base64.b64encode((SCREENS / m["image"]).read_bytes()).decode()
            img = f'<img src="data:image/png;base64,{data}" alt="{html.escape(TITLES.get(name, name))}">'
        rows = "".join(
            '<div class="row">' + "".join(f"<span>{html.escape(b)}</span>" for b in row) + "</div>"
            for row in m["buttons"]
        )
        cards.append(
            f'<figure><figcaption>{html.escape(TITLES.get(name, name))}</figcaption><div class="phone">'
            '<div class="top"><div class="ava">م</div><div><div class="name">Муаллим сани</div>'
            '<div class="sub">бот</div></div></div><div class="chat">'
            f'<div class="msg">{img}<div class="cap">{caption(m["caption"])}</div></div>'
            + (
                f'<div class="msg"><div class="cap">{caption(m["details"])}</div></div>'
                if m.get("details")
                else ""
            )
            + f"{rows}</div></div></figure>"
        )
    page = f"""<title>Муаллим сани — экраны бота</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700&family=Noto+Serif:wght@600&family=Noto+Naskh+Arabic:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
<div class="eyebrow">Telegram-бот · обучение чтению с нуля</div>
<h1>Муаллим сани — экраны бота</h1>
<p class="lead">Каждый экран нарисован кодом бота (make design): те же картинки, подписи и кнопки, что увидит ученик.
Порядок уроков — как в книге Максуди.</p>
<div class="grid">{"".join(cards)}</div>
</div>
"""
    OUT.write_text(page, "utf-8")
    print(f"Макеты: {len(cards)} экранов → {OUT} ({OUT.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
