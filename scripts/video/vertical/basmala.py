# ruff: noqa
"""Пробный ролик «басмала», версия 3 — по образцу IMG_6472: 4 буквы (ب ل ر ح), камера едет
губы → бугорок → горло → общий план с подписями → карточка. Звук — басмала аль-Афаси (SRC-145).

  uv run --group video python -I <этот файл> <001001.mp3> <artext> <out.mp4> [секунды,через,запятую]
"""

import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts" / "video"))

import numpy as np
from articulate import LIPS, LOWER_TEETH, RIDGE, VOWELS, Head, Pose
from PIL import Image, ImageDraw, ImageFilter, ImageFont


# Щель перед губами — в цвет фона ролика (в articulate.py она белая под светлый фон).
import articulate as _art
from articulate import CAVITY_MAX, MOUTH, PIVOT, RX0, RX1, RY0, RY1, _border, _smooth


def _jaw_dark(self, img: np.ndarray, p: Pose) -> np.ndarray:
    xx, yy = self.xx, self.yy
    lower = yy > _border(xx)
    # вес поворота: спереди челюсть целиком, к глотке и шее — плавно ноль
    w = _smooth((xx - 690) / 260) * (1 - _smooth((yy - 1010) / 80) * (1 - _smooth((xx - 900) / 60)))
    a = -math.radians(p.jaw) * w
    c, s = np.cos(a), np.sin(a)
    dx, dy = xx - PIVOT[0], yy - PIVOT[1]
    sx = np.where(lower, PIVOT[0] + c * dx - s * dy, xx)
    sy = np.where(lower, PIVOT[1] + s * dx + c * dy, yy)
    upper_lip = (~lower) & (xx > 975) & (yy > 690)
    sy = np.where(upper_lip, yy + p.lift * _smooth((xx - 975) / 40) * _smooth((yy - 700) / 110), sy)
    lips = _smooth((xx - 985) / 30) * np.exp(-(((yy - 824) / 95) ** 2))
    sx = sx - (p.protrude - p.spread) * lips
    gap = (lower & (sy < _border(sx) - 0.5)) | (upper_lip & (sy > _border(sx) + 0.5))
    out = self._sample(img, sx, sy)
    # щель: в глубине — цвет полости, между губами — тёмный рот, перед губами — фон
    ax = np.clip(xx.astype(int), 0, img.shape[1] - 1)
    ay = np.clip((_border(xx) - 8).astype(int), 0, img.shape[0] - 1)
    inner = np.minimum(img[ay, ax], CAVITY_MAX)
    depth = np.clip((xx - 975) / 80, 0, 1)[..., None]
    mouth = MOUTH * (1 - 0.3 * depth) + np.array([150, 60, 60], np.float32) * 0.3 * depth
    fade = _smooth((xx - 1004 - p.protrude) / 12)[..., None]
    blend = _smooth((xx - 962) / 26)[..., None]
    fill = inner * (1 - blend) + (mouth * (1 - fade) + np.array(BG, np.float32) * fade) * blend
    out = np.where(gap[..., None], fill, out)
    res = img.copy()
    res[RY0:RY1, RX0:RX1] = out
    return res


Head._jaw = _jaw_dark


AUDIO, ARTEXT, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
TMP = OUT.parent / "parts"
TMP.mkdir(exist_ok=True)

W, H, FPS = 1080, 1920, 30
OUT_W, OUT_H = 720, 1280
BG = (12, 18, 30)
FONT_TEXT = "/System/Library/Fonts/Avenir Next.ttc"
AUD0 = 0.35  # басмала начинается
DUR = 18.0
AUD2 = 7.6  # второе прослушивание — на общем плане
IMG_W, IMG_H = 1147, 1153

GREEN, ORANGE, BLUE, PURPLE = (61, 220, 132), (255, 159, 67), (74, 168, 255), (197, 108, 240)
COL = {"ب": GREEN, "ل": BLUE, "ر": ORANGE, "ح": PURPLE}
AT = {"ب": LIPS, "ل": (916.0, 778.0), "ر": (950.0, 750.0), "ح": (590.0, 965.0)}
# Подписи общего плана — по первым строкам scripts/book/theory.py (черновик, утверждает автор).
LABEL = {
    "ب": ("Ба", "обе губы сомкнуты"),
    "ل": ("Лям", "края языка у дёсен верхних зубов"),
    "ر": ("Ра", "кончик языка у бугорка за зубами"),
    "ح": ("Ха", "середина горла"),
}
CARD = [  # карточка в конце (черновик)
    ("Правильные места звуков", "(махрадж)"),
    ("Точные огласовки", "(харакаты)"),
    ("Правильная протяжка", "(мадд)"),
    ("Чёткое, размеренное", "чтение"),
]

# Время звуков в записи (CTC Muaalem): для движения рта.
VOWEL_AT = [
    ("i", 0.14, 0.30),
    ("i", 0.50, 0.58),
    ("a", 0.86, 1.18),
    ("i", 1.27, 1.38),
    ("a", 1.66, 1.80),
    ("a", 2.03, 2.34),
    ("i", 2.43, 2.50),
    ("a", 2.82, 2.94),
    ("i", 3.05, 5.55),
]
TIP_AT = [
    (0.32, "s"),
    (0.60, "r"),
    (0.80, "r"),
    (1.44, "r"),
    (1.60, "r"),
    (2.40, "r"),
    (2.56, "r"),
    (2.76, "r"),
]

# Камера: (время, центр x, центр y, масштаб — экранных пикселей на пиксель рисунка).
A = (985.0, 800.0, 2.5)  # губы крупно
B = (935.0, 780.0, 2.7)  # бугорок за зубами
C = (720.0, 800.0, 2.5)  # горло
D = (960.0, 720.0, 1.3)  # общий план
KF = [(0.0, A), (2.2, A), (2.9, B), (4.9, B), (5.6, C), (6.9, C), (7.6, D), (99.0, D)]


def ease(x: float) -> float:
    c = min(max(x, 0.0), 1.0)
    return c * c * (3 - 2 * c)


def window(t: float, a: float, b: float, fin: float = 0.25, fout: float = 0.25) -> float:
    return ease((t - a) / fin) * (1 - ease((t - b) / fout))


def cam(t: float) -> tuple[float, float, float]:
    for (t0, c0), (t1, c1) in zip(KF, KF[1:]):
        if t0 <= t < t1:
            u = ease((t - t0) / (t1 - t0))
            return tuple(a + (b - a) * u for a, b in zip(c0, c1))  # type: ignore[return-value]
    return D


def f(size: int, idx: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_TEXT, size, index=idx)


def artext(text: str, size: int, color: str, name: str) -> Image.Image:
    p = TMP / f"{name}.png"
    subprocess.run([ARTEXT, text, str(size), str(p), color], check=True)
    return Image.open(p).convert("RGBA")


LETTER = {c: artext(c, 78, "FFFFFF", f"L{ord(c)}") for c in COL}
LETTER_S = {c: artext(c, 48, "FFFFFF", f"S{ord(c)}") for c in COL}


def fade(img: Image.Image, a: float) -> Image.Image:
    if a >= 1:
        return img
    img = img.copy()
    img.putalpha(img.split()[3].point(lambda v: int(v * a)))
    return img


def pose_at(ta: float) -> Pose:
    acc = {"jaw": 0.0, "lift": 0.0, "protrude": 0.0, "spread": 0.0}
    for v, s, e in VOWEL_AT:
        w = ease((ta - s + 0.03) / 0.07) * (1 - ease((ta - e) / 0.1))
        for key in acc:
            acc[key] += getattr(VOWELS[v], key) * w * 0.6
    tip, target = 0.0, RIDGE
    for pk, kind in TIP_AT:
        w = ease((ta - (pk - 0.12)) / 0.08) * (1 - ease((ta - (pk + 0.02)) / 0.08))
        if w > tip:
            tip, target = w * (0.7 if kind == "s" else 1.0), (LOWER_TEETH if kind == "s" else RIDGE)
    return Pose(tip=tip, tip_target=target, **acc)


def to_screen(p: tuple[float, float], c: tuple[float, float, float]) -> tuple[float, float]:
    cx, cy, s = c
    return (W / 2 + (p[0] - cx) * s, H / 2 + (p[1] - cy) * s)


WHITE: Image.Image | None = None  # где на исходном рисунке белый фон (не лицо)


def head_view(img: Image.Image, c: tuple[float, float, float]) -> Image.Image:
    cx, cy, s = c
    w, h = W / s, H / s
    x0, y0 = cx - w / 2, cy - h / 2
    box = (x0, y0, x0 + w, y0 + h)
    v = img.transform((W, H), Image.Transform.EXTENT, box, Image.Resampling.BICUBIC, fillcolor=BG)
    wm = WHITE.transform(
        (W, H), Image.Transform.EXTENT, box, Image.Resampling.BILINEAR, fillcolor=255
    )
    a = np.asarray(v).astype(np.float32)
    white = np.maximum(
        (np.asarray(wm).astype(np.float32) / 255)[..., None],
        np.clip((a.min(axis=2, keepdims=True) - 225) / 25, 0, 1),
    )
    ys = y0 + (np.arange(H) + 0.5) / s
    xs = x0 + (np.arange(W) + 0.5) / s
    ky = np.clip(np.minimum(ys, IMG_H - ys) / 60, 0, 1)
    kx = np.clip(np.minimum(xs, IMG_W - xs) / 60, 0, 1)
    k = (ky[:, None] * kx[None, :])[..., None]
    k = k * k * (3 - 2 * k)
    keep = (1 - white) * k
    out = a * keep + np.array(BG, np.float32) * (1 - keep)
    return Image.fromarray(out.astype(np.uint8))


def pin(
    d: ImageDraw.ImageDraw,
    lay: Image.Image,
    c: str,
    xy: tuple[float, float],
    a: float,
    burst: float = -1,
    r: int = 58,
    small: bool = False,
) -> None:
    col = COL[c]
    x, y = xy
    if 0 < burst < 1:  # звуковая вспышка: кольцо и лучи
        al = int(235 * (1 - burst) * a)
        rr = r + 8 + 60 * burst
        d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=(*col, al), width=5)
        for j in range(24):
            ang = j * math.pi / 12
            r1 = r + 6 + 24 * burst
            r2 = r1 + 16 + 30 * burst * (0.6 + 0.4 * math.sin(j * 2.3))
            d.line(
                (
                    x + r1 * math.cos(ang),
                    y + r1 * math.sin(ang),
                    x + r2 * math.cos(ang),
                    y + r2 * math.sin(ang),
                ),
                fill=(*col, al),
                width=4,
            )
    d.ellipse((x - r, y - r, x + r, y + r), fill=(20, 24, 34, int(150 * a)))
    d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, int(200 * a)), width=3)
    d.ellipse((x - r + 5, y - r + 5, x + r - 5, y + r - 5), outline=(*col, int(255 * a)), width=7)
    li = fade((LETTER_S if small else LETTER)[c], a)
    lay.paste(li, (int(x - li.width / 2), int(y - li.height / 2 + 5)), li)


def curve(
    d: ImageDraw.ImageDraw,
    a: tuple[float, float],
    ctrl: tuple[float, float],
    b: tuple[float, float],
    col: tuple[int, int, int],
    prog: float,
    alpha: float,
    both: bool = False,
) -> None:
    """Изогнутая стрелка a → b; ``both`` — наконечник и в начале (как «туда-обратно» в образце)."""
    if prog <= 0.02 or alpha <= 0.01:
        return
    pts = []
    for i in range(31):
        u = prog * i / 30
        pts.append(
            (
                (1 - u) ** 2 * a[0] + 2 * (1 - u) * u * ctrl[0] + u * u * b[0],
                (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * ctrl[1] + u * u * b[1],
            )
        )
    fill = (*col, int(255 * alpha))
    d.line(pts, fill=fill, width=13, joint="curve")

    def head_at(p2: tuple[float, float], p1: tuple[float, float]) -> None:
        ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        tip = (p2[0] + 14 * math.cos(ang), p2[1] + 14 * math.sin(ang))
        l = (
            tip[0] + 40 * math.cos(ang + math.pi - 0.55),
            tip[1] + 40 * math.sin(ang + math.pi - 0.55),
        )
        r = (
            tip[0] + 40 * math.cos(ang + math.pi + 0.55),
            tip[1] + 40 * math.sin(ang + math.pi + 0.55),
        )
        d.polygon([tip, l, r], fill=fill)

    head_at(pts[-1], pts[-3])
    if both and prog > 0.5:
        head_at(pts[0], pts[2])


TEXT = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"
# Где буква в тексте (с огласовками). ل в «ар-» не читается — не подсвечиваем.
SPANS = {"ب": [(0, 2)], "ل": [(8, 4)], "ر": [(17, 3), (31, 3)], "ح": [(20, 2), (34, 2)]}
HEX = {c: "%02X%02X%02X" % COL[c] for c in COL}


def basmala(letters: str, name: str) -> Image.Image:
    p = TMP / f"{name}.png"
    rng = [f"{a}:{n}:{HEX[c]}" for c in letters for a, n in SPANS[c]]
    subprocess.run([ARTEXT, TEXT, "104", str(p), "AEB5C4", "Geeza Pro", *rng], check=True)
    return Image.open(p).convert("RGBA")


BAS = {k: basmala(k, f"bas_{i}") for i, k in enumerate(["", "ب", "لر", "ح", "بلرح"])}
# Слоги — запись автора проекта; последний — «м» (чтец останавливается, сукун).
SYLS = ["бис", "мил", "лаа", "һир", "рах̣", "маа", "нир", "ра", "х̣ии", "м"]
SYL_T = [0.0, 0.44, 0.76, 1.20, 1.56, 1.96, 2.36, 2.72, 2.96, 5.62, 6.03]  # границы в записи
SYL_OF = {"ب": {0}, "ل": {1, 2}, "ر": {3, 4, 6, 7}, "ح": {4, 8}}
# Подписи сцен: имя и звук — по «Как сказать», место — первая строка scripts/book/theory.py.
SCENE_TEXT = {
    "ب": [("ب", "Ба — звук «б»", "Обе губы сомкнуты и резко размыкаются.")],
    "لر": [
        ("ل", "Лям — мягкое «ль», как в «лямка»", "Края языка у дёсен верхних зубов."),
        ("ر", "Ра — «р», один лёгкий удар языком", "Кончик языка у бугорка за зубами."),
    ],
    "ح": [
        (
            "ح",
            "Ха — сильный чистый выдох",
            "Середина горла: горло сужено, но без хрипа. Не русское «х».",
        )
    ],
}
CARD2 = [
    "1. Послушай ещё раз",
    "2. Повтори вслух по слогам",
    "3. Отправь голосовое — бот проверит",
]
S1, S2, S3, OV, CD = (0.25, 2.3), (2.75, 5.0), (5.5, 7.05), (7.4, 13.9), (14.0, 17.4)


def sf(size: int, weight: str = "Semibold") -> ImageFont.FreeTypeFont:
    fnt = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
    try:
        fnt.set_variation_by_name(weight)
    except Exception:
        pass
    return fnt


def bump(u: float) -> float:
    return ease(u / 0.08) * (1 - ease((u - 0.2) / 0.12))


def scene_pose(t: float) -> Pose:
    if t < S2[0] - 0.2:  # губы смыкаются и размыкаются на каждый пульс
        w = bump((t - 0.3) % 0.75) if t > 0.3 else 0.0
        return Pose(jaw=2.2 * w, lift=3.0 * w)
    if t < S3[0] - 0.2:  # рот приоткрыт, кончик языка поднимается к бугорку и держится
        o = window(t, S2[0] - 0.1, S2[1], 0.3, 0.3)
        tip = window(t, S2[0] + 0.2, S2[1] - 0.2, 0.5, 0.3)
        return Pose(jaw=2.2 * o, lift=2.0 * o, tip=tip, tip_target=RIDGE)
    if t < OV[0]:
        o = window(t, S3[0] - 0.1, S3[1], 0.3, 0.3)
        return Pose(jaw=1.6 * o, lift=1.5 * o)
    ta = t - AUD2
    return pose_at(ta) if 0 <= ta <= 6.1 else Pose()


def caption(
    d: ImageDraw.ImageDraw, lay: Image.Image, rows: list[tuple[str, str, str]], a: float
) -> None:
    yb = 1540
    hrow = 165
    d.rounded_rectangle(
        (36, yb, W - 36, yb + 40 + hrow * len(rows)), 34, fill=(16, 22, 34, int(215 * a))
    )
    for n, (c, title, place) in enumerate(rows):
        y = yb + 30 + n * hrow
        d.ellipse((66, y + 8, 156, y + 98), fill=(*COL[c], int(255 * a)))
        li = fade(LETTER_S[c], a)
        lay.paste(li, (int(111 - li.width / 2), int(y + 53 - li.height / 2 + 4)), li)
        d.text((184, y + 6), title, font=sf(42), fill=(*COL[c], int(255 * a)))
        words, cur, lines = place.split(), "", []
        fp = sf(34, "Regular")
        for w in words:
            nxt = f"{cur} {w}".strip()
            if d.textlength(nxt, font=fp) > W - 250 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = nxt
        lines.append(cur)
        for k, line in enumerate(lines[:2]):
            d.text((184, y + 62 + k * 42), line, font=fp, fill=(225, 228, 236, int(255 * a)))


def header(d: ImageDraw.ImageDraw, lay: Image.Image, t: float, key: str, a: float) -> None:
    band = Image.new("RGBA", (W, 470), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(470):
        bd.line((0, y, W, y), fill=(*BG, int(235 * min(1.0, (470 - y) / 170) * a)))
    lay.alpha_composite(band)
    img = BAS[key]
    sc = min(1.0, (W - 70) / img.width)
    bm = fade(img.resize((int(img.width * sc), int(img.height * sc)), Image.Resampling.LANCZOS), a)
    lay.paste(bm, (int((W - bm.width) / 2), 70), bm)
    # слоги: подсвечены те, где звучит буква сцены; на общем плане — текущий слог под звук
    hot: dict[int, tuple[int, int, int]] = {}
    for c in key:
        for k in SYL_OF[c]:
            hot.setdefault(k, COL[c])
    ta = t - AUD2
    cur = next((k for k in range(10) if SYL_T[k] <= ta < SYL_T[k + 1]), -1) if t >= OV[0] else -1
    fs = sf(42)
    parts = []
    for k, s in enumerate(SYLS):
        parts.append((s, k))
        if k < 9:
            parts.append(("-", -1))
    total = sum(d.textlength(p, font=fs) for p, _ in parts)
    x = (W - total) / 2
    y = 285
    for p, k in parts:
        wdt = d.textlength(p, font=fs)
        col = hot.get(k, (150, 158, 175)) if k >= 0 else (110, 118, 135)
        if k >= 0 and k == cur:
            d.rounded_rectangle(
                (x - 8, y - 6, x + wdt + 8, y + 58), 14, fill=(255, 255, 255, int(40 * a))
            )
            col = (255, 255, 255) if k not in hot else col
        d.text((x, y), p, font=fs, fill=(*col, int(255 * a)))
        x += wdt


def frame(i: int, head: Head) -> Image.Image:
    t = i / FPS
    c = cam(t)
    im = head_view(head.pose(scene_pose(t)), c)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    # шапка рисуется первой: прозрачный текст поверх карточки «пробивал» её насквозь
    key = (
        "ب" if t < S2[0] - 0.2 else "لر" if t < S3[0] - 0.2 else "ح" if t < OV[0] - 0.1 else "بلرح"
    )
    ha = 1 - ease((t - CD[0]) / 0.4) if t > CD[0] else ease((t - 0.1) / 0.4)
    if ha > 0.02:
        header(d, lay, t, key, ha)

    # 1. ب — губы, пульс
    a = window(t, *S1)
    if a > 0:
        pin(d, lay, "ب", to_screen(AT["ب"], c), a, ((t - 0.3) % 0.75) / 0.75)
        caption(d, lay, SCENE_TEXT["ب"], a)
    # 2. ل и ر — кончик языка поднимается
    a = window(t, *S2)
    if a > 0:
        pl, pr = to_screen(AT["ل"], c), to_screen(AT["ر"], c)
        tipx, tipy = to_screen((880.0, 830.0), c)
        prog = ease((t - S2[0] - 0.25) / 0.55)
        curve(
            d,
            (tipx - 20, tipy + 40),
            (tipx - 10, tipy - 120),
            (pr[0] - 40, pr[1] + 60),
            ORANGE,
            prog,
            a,
        )
        pin(d, lay, "ل", pl, a)
        pin(d, lay, "ر", pr, a, ((t - S2[0] - 0.8) % 0.9) / 0.9 if t > S2[0] + 0.8 else -1)
        caption(d, lay, SCENE_TEXT["لر"], a)
    # 3. ح — горло, воздух снизу
    a = window(t, *S3)
    if a > 0:
        ph = to_screen(AT["ح"], c)
        prog = ease((t - S3[0] - 0.15) / 0.6)
        curve(
            d,
            (ph[0] - 70, ph[1] + 300),
            (ph[0] + 40, ph[1] + 220),
            (ph[0] - 10, ph[1] + 75),
            PURPLE,
            prog,
            a,
        )
        pin(d, lay, "ح", ph, a, ((t - S3[0] - 0.7) % 0.8) / 0.8 if t > S3[0] + 0.7 else -1)
        caption(d, lay, SCENE_TEXT["ح"], a)
    # 4. общий план под второе прослушивание
    a = window(t, OV[0], OV[1], 0.4, 0.35)
    if a > 0:
        for n, ch in enumerate("رلبح"):
            aa = ease((t - OV[0] - 0.2 - n * 0.25) / 0.35) * a
            p = to_screen(AT[ch], c)
            bx, by = 690, 640 + n * 190
            d.line((p, (bx - 10, by + 34)), fill=(*COL[ch], int(230 * aa)), width=4)
            d.ellipse((bx - 20, by + 24, bx, by + 44), fill=(*COL[ch], int(255 * aa)))
            name, text = LABEL[ch]
            fb = f(36, 2)
            words, cur, wrapped = f"{name} — {text}".split(), "", []
            for w in words:
                nxt = f"{cur} {w}".strip()
                if d.textlength(nxt, font=fb) > 330 and cur:
                    wrapped.append(cur)
                    cur = w
                else:
                    cur = nxt
            wrapped.append(cur)
            d.rounded_rectangle(
                (bx, by, W - 24, by + 24 + 44 * len(wrapped)), 14, fill=(20, 24, 34, int(210 * aa))
            )
            for k, line in enumerate(wrapped):
                d.text(
                    (bx + 18, by + 12 + k * 44), line, font=fb, fill=(240, 240, 245, int(255 * aa))
                )
            pin(d, lay, ch, p, aa, r=34, small=True)
        d.text(
            (W / 2, 1640),
            "Слушай целиком и следи за слогами",
            font=sf(38, "Regular"),
            anchor="mm",
            fill=(200, 205, 215, int(255 * a)),
        )
    # 5. твоя очередь
    a = window(t, CD[0], CD[1], 0.4, 0.5)
    if a > 0:
        lay.alpha_composite(Image.new("RGBA", (W, H), (*BG, int(170 * a))))
        x0, y0, x1, y1 = 80, 560, W - 80, 1400
        d.rounded_rectangle(
            (x0, y0, x1, y1),
            44,
            fill=(16, 22, 34, int(200 * a)),
            outline=(255, 255, 255, int(70 * a)),
            width=2,
        )
        d.text(
            (W / 2, y0 + 80),
            "Во имя Аллаха, Милостивого, Милосердного",
            font=sf(32, "Regular"),
            anchor="mm",
            fill=(200, 205, 215, int(255 * a)),
        )
        d.text(
            (W / 2, y0 + 200),
            "Твоя очередь",
            font=sf(70),
            anchor="mm",
            fill=(255, 212, 121, int(255 * a)),
        )
        for n, line in enumerate(CARD2):
            aa = ease((t - CD[0] - 0.3 - n * 0.4) / 0.4) * a
            d.text(
                (x0 + 70, y0 + 330 + n * 130),
                line,
                font=sf(44),
                fill=(240, 240, 245, int(255 * aa)),
            )

    glow = lay.filter(ImageFilter.GaussianBlur(7))
    im.paste(glow, (0, 0), glow.split()[3].point(lambda v: v // 3))
    im.paste(lay, (0, 0), lay)
    if t < 0.4:
        im = Image.blend(Image.new("RGB", (W, H), BG), im, ease(t / 0.4))
    if t > DUR - 0.6:
        im = Image.blend(im, Image.new("RGB", (W, H), BG), ease((t - DUR + 0.6) / 0.6))
    return im


def main() -> None:
    global WHITE
    head = Head()
    rest = np.asarray(head.pose(Pose())).astype(np.float32)
    wm = np.clip((rest.min(axis=2) - 225) / 25, 0, 1)
    WHITE = Image.fromarray((wm * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    if len(sys.argv) > 4:
        for s in sys.argv[4].split(","):
            frame(int(float(s) * FPS), head).save(OUT.parent / f"f{s}.png")
        return
    track = OUT.parent / "track.wav"  # две басмалы, собрана заранее
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(track),
        "-vf",
        f"scale={OUT_W}:{OUT_H}:flags=lanczos",
        "-t",
        f"{DUR:.2f}",
        "-c:v",
        "libx264",
        "-crf",
        "22",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(OUT),
    ]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(DUR * FPS)
    for i in range(n):
        ff.stdin.write(frame(i, head).tobytes())
        if i % 30 == 0:
            print(f"кадр {i}/{n}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg failed")


if __name__ == "__main__":
    main()
