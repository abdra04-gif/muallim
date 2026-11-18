"""Сайт-описание: docs/site/content/*.md → docs/site/build/ (index.html, spec-for-chatgpt.md).

Запуск: make site. Править — только docs/site/content (Markdown) и docs/site/site.css.
Схемы — функции ниже (inline SVG, светлая/тёмная тема). В Markdown схема — строка
`{{fig:имя|описание словами}}`: на сайте рисуется картинка, в spec-for-chatgpt.md остаётся
описание словами (ChatGPT не видит inline SVG).
Только stdlib.
"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "docs" / "site" / "content"
OUT = ROOT / "docs" / "site" / "build"

LETTERS = list("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")  # 28 букв алфавита


# ───────────────────────── схемы ─────────────────────────
def _text(x: float, y: float, cls: str, s: str) -> str:
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="middle">{html.escape(s)}</text>'


def _box(x: int, y: int, size: tuple[int, int], texts: tuple[str, str], cls: str = "box") -> str:
    w, h = size
    title, sub = texts
    t = _text(x + w / 2, y + h / 2 - (6 if sub else -5), "t", title)
    s = _text(x + w / 2, y + h / 2 + 14, "s", sub) if sub else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" class="{cls}"/>{t}{s}'


def _arrow(x1: int, y1: int, x2: int, y2: int) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="ar" marker-end="url(#ah)"/>'


DEFS = (
    '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="ahp"/></marker></defs>'
)


def fig_journey() -> str:
    steps = [
        ("1 · Видео", "≤ 5 мин, 1–3 буквы"),
        ("2 · Слова", "картинка + аудио"),
        ("3 · Попытка", "голосовое ученика"),
        ("4 · Разбор", "текст или картинка"),
        ("5 · Прогресс", "шаг n из 4 · серия 🔥"),
    ]
    parts = [DEFS, _text(450, 20, "s", "Один урок (повторяется для каждых 1–3 букв)")]
    for i, texts in enumerate(steps):
        x = 10 + i * 178
        parts.append(_box(x, 40, (150, 76), texts, "box acc" if i in (0, 2) else "box"))
        if i:
            parts.append(_arrow(x - 26, 78, x - 2, 78))
    done = ("Урок пройден", "поздравление · серия продолжается")
    parts.append(_box(10, 170, (330, 70), done, "box ok"))
    milestone = ("Все 28 букв прочитаны", "ВЕХА с визуализацией → открывается Этап II")
    parts.append(_box(370, 170, (520, 70), milestone, "box gold"))
    parts.append(_arrow(340, 205, 366, 205))
    parts.append(_arrow(800, 116, 800, 164))
    return f'<svg viewBox="0 0 900 260" role="img" aria-label="Путь ученика">{"".join(parts)}</svg>'


def _bullets(x: int, y: int, items: list[str]) -> str:
    return "".join(
        f'<text x="{x}" y="{y + i * 22}" class="s">• {html.escape(t)}</text>'
        for i, t in enumerate(items)
    )


def fig_stages() -> str:
    one = ("Этап I · буквы и огласовки", "28 пунктов программы, прочитать всё один раз")
    two = ("Этап II · дальше", "пп. 3–8 таблицы профессора")
    parts = [DEFS, _box(10, 20, (420, 150), one, "box acc")]
    parts.append(
        _bullets(
            30,
            110,
            [
                "видео-урок, слова + аудио, попытка, разбор",
                "мягко: ошибки показываем, идеала не требуем",
                "без транслитерации, без AI-звука и AI-картинок",
            ],
        )
    )
    parts += [_box(450, 60, (120, 70), ("ВЕХА", "28 / 28"), "box gold"), _arrow(430, 95, 446, 95)]
    parts += [_arrow(570, 95, 596, 95), _box(600, 20, (290, 150), two)]
    parts.append(
        _bullets(
            620,
            110,
            [
                "доп. ресурсы: живой человек (видео)",
                "углублённая артикуляция (махарадж)",
                "для старательных — онлайн-учитель",
            ],
        )
    )
    return f'<svg viewBox="0 0 900 190" role="img" aria-label="Этапы">{"".join(parts)}</svg>'


def fig_milestone() -> str:
    parts = [_text(450, 22, "s", "Пример: карта вехи, 12 из 28 прочитано (все 28 — Этап II)")]
    for i, ch in enumerate(LETTERS):
        x, y = 12 + (i % 14) * 63, 40 + (i // 14) * 78
        cls = "cell ok" if i < 12 else ("cell cur" if i == 12 else "cell")
        parts.append(f'<rect x="{x}" y="{y}" width="56" height="66" rx="10" class="{cls}"/>')
        parts.append(_text(x + 28, y + 44, "ar-l", ch))
    done = 876 * 12 // 28
    parts.append('<rect x="12" y="204" width="876" height="14" rx="7" class="bar"/>')
    parts.append(f'<rect x="12" y="204" width="{done}" height="14" rx="7" class="barf"/>')
    return f'<svg viewBox="0 0 900 232" role="img" aria-label="Карта вехи">{"".join(parts)}</svg>'


def _phone(x: int, title: str, lines: list[str], buttons: list[str], big: str) -> str:
    p = [f'<rect x="{x}" y="10" width="210" height="400" rx="22" class="ph"/>']
    p.append(_text(x + 105, 36, "t", title))
    p.append(f'<rect x="{x + 14}" y="52" width="182" height="96" rx="10" class="img"/>')
    p.append(_text(x + 105, 115, "big", big))
    for i, ln in enumerate(lines):
        p.append(f'<text x="{x + 16}" y="{172 + i * 20}" class="s">{html.escape(ln)}</text>')
    for i, b in enumerate(buttons):
        y = 338 + i * 34
        p.append(f'<rect x="{x + 14}" y="{y}" width="182" height="28" rx="8" class="btn"/>')
        p.append(_text(x + 105, y + 19, "bt", b))
    return "".join(p)


def fig_screens() -> str:
    ph = [
        _phone(
            10,
            "Урок 1 · шаг 1 из 4",
            ["Видео-урок (≤ 5 мин)", "Арабская речь,", "русские субтитры"],
            ["▶ Смотреть видео", "Дальше → слова"],
            "▶",
        ),
        _phone(
            235,
            "Урок 1 · шаг 2 из 4",
            ["Слова урока на картинке", "и голосовое: как правильно", "Послушай, потом повтори"],
            ["🔊 Ещё раз", "🎤 Читать самому"],
            "ب ـَ ا",
        ),
        _phone(
            460,
            "Урок 1 · шаг 3 из 4",
            ["Пришли голосовое:", "прочитай слова с картинки", "Идеала не нужно"],
            ["⏭ Пропустить"],
            "🎤",
        ),
        _phone(
            685,
            "Урок 1 · шаг 4 из 4",
            ["Разбор: что услышано", "Что поправить (1–3 пункта)", "Урок засчитан ✔ · 🔥 3"],
            ["Следующий урок", "📊 Мой прогресс"],
            "✔",
        ),
    ]
    return f'<svg viewBox="0 0 910 420" role="img" aria-label="Экраны урока">{"".join(ph)}</svg>'


def fig_widgets() -> str:
    parts = [DEFS]
    parts.append(_box(10, 30, (190, 80), ("Ученик", "Telegram, личный чат")))
    parts.append(_box(350, 30, (220, 80), ("Бот (наш)", "хранит состояние"), "box acc"))
    parts.append(_box(700, 30, (190, 80), ("Telegram", "рисует виджет")))
    parts += [_arrow(200, 55, 346, 55), _text(273, 46, "s", "тап: request ≤ 64 Б")]
    parts += [_arrow(346, 90, 204, 90), _text(273, 108, "s", "ответ ≤ 1024 Б, за 15 с")]
    parts += [_arrow(570, 70, 696, 70), _text(633, 62, "s", "sendWidget / edit…Data")]
    bottom = (
        "Виджет = неизменный HTML ≤ 32 КБ (≤ 4 КБ сжатого) + состояние ≤ 1024 Б",
        "без сети · без ввода · только тапы · только в личном чате (прод)",
    )
    parts.append(_box(10, 150, (880, 80), bottom))
    return f'<svg viewBox="0 0 900 250" role="img" aria-label="Виджеты">{"".join(parts)}</svg>'


FIGS = {
    "journey": fig_journey,
    "stages": fig_stages,
    "milestone": fig_milestone,
    "screens": fig_screens,
    "widgets": fig_widgets,
}

# ───────────────────────── Markdown → HTML ─────────────────────────
FIG_RE = re.compile(r"^\{\{fig:(\w+)\|(.*)\}\}$")


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', s)


def md_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
        elif m := FIG_RE.match(ln.strip()):
            svg, cap = FIGS[m.group(1)](), _inline(m.group(2))
            out.append(f'<figure class="fig">{svg}<figcaption>{cap}</figcaption></figure>')
            i += 1
        elif ln.startswith("#"):
            n = len(ln) - len(ln.lstrip("#"))
            text = ln[n:].strip()
            slug = re.sub(r"\W+", "-", text.lower()).strip("-")
            out.append(f'<h{n} id="{slug}">{_inline(text)}</h{n}>')
            i += 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[2:]
            t = (
                "<div class='tw'><table><thead><tr>"
                + "".join(f"<th>{_inline(c)}</th>" for c in head)
                + "</tr></thead><tbody>"
            )
            t += "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body
            )
            out.append(t + "</tbody></table></div>")
        elif re.match(r"^(\s*[-*] |\d+\. )", ln):
            ordered = bool(re.match(r"^\d+\. ", ln))
            items = []
            while i < len(lines) and re.match(r"^(\s*[-*] |\d+\. )", lines[i]):
                items.append(re.sub(r"^(\s*[-*] |\d+\. )", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
        elif ln.startswith(">"):
            q = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(q))}</blockquote>")
        else:
            p = []
            while (
                i < len(lines)
                and lines[i].strip()
                and not re.match(r"^(#|\||>|\{\{fig|\s*[-*] |\d+\. )", lines[i])
            ):
                p.append(lines[i].strip())
                i += 1
            out.append(f"<p>{_inline(' '.join(p))}</p>")
    return "\n".join(out)


def md_for_chatgpt(md: str) -> str:
    """Картинки → описание словами (ChatGPT не видит inline SVG)."""
    return re.sub(r"^\{\{fig:\w+\|(.*)\}\}$", r"*[Схема]* \1", md, flags=re.MULTILINE)


CSS = (ROOT / "docs" / "site" / "site.css").read_text(encoding="utf-8")


def build() -> list[Path]:
    files = sorted(CONTENT.glob("*.md"))
    if not files:
        raise SystemExit(f"нет разделов в {CONTENT}")
    OUT.mkdir(parents=True, exist_ok=True)
    sections = [f.read_text(encoding="utf-8") for f in files]
    nav: list[str] = []
    body: list[str] = []
    for sec in sections:
        for ln in sec.splitlines():
            if ln.startswith("## ") or (ln.startswith("# ") and not nav):
                t = ln.lstrip("# ").strip()
                slug = re.sub(r"\W+", "-", t.lower()).strip("-")
                nav.append(f'<a href="#{slug}">{html.escape(t)}</a>')
        body.append(md_to_html(sec))
    title = "План первой версии Муаллим"
    page = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{CSS}</style></head><body><div class='layout'>"
        f"<nav><b>{title}</b>{''.join(nav)}</nav><main>{''.join(body)}</main></div></body></html>"
    )
    layout = (
        f"<div class='layout'><nav><b>{title}</b>{''.join(nav)}</nav>"
        f"<main>{''.join(body)}</main></div>"
    )
    meta = '<meta name="claude:viewport-fit-sides" content="cover">'
    fragment = f"<title>{title}</title>{meta}<style>{CSS}</style>{layout}"
    artifact = OUT / "artifact.html"  # без doctype/head/body: их добавляет публикация артефакта
    artifact.write_text(fragment, encoding="utf-8")
    index = OUT / "index.html"
    index.write_text(page, encoding="utf-8")
    spec = OUT / "spec-for-chatgpt.md"
    spec.write_text("\n\n".join(md_for_chatgpt(s) for s in sections), encoding="utf-8")
    return [index, spec, artifact]


if __name__ == "__main__":
    for p in build():
        print(p.relative_to(ROOT), p.stat().st_size, "байт")
