"""Кадры ролика: рисунок в позе + поток частиц воздуха + звуковые волны + панель; ffmpeg → mp4.

Шкала времени строится от звука: ``events`` — (начало, конец) каждого слога в секундах ролика.
"""

import itertools
import math
import random
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from articulate import GLOTTIS, LIPS, LOWER_TEETH, RIDGE, VOWELS, Head, Pose
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Шрифты macOS. На другой системе — поменять пути (нужны кириллица и арабский).
FONT_TEXT = "/System/Library/Fonts/Avenir Next.ttc"
FONT_ARABIC = "/System/Library/Fonts/GeezaPro.ttc"
BOLD, DEMI, MEDIUM = 0, 2, 5  # начертания в Avenir Next.ttc

SS = 2  # рисуем вдвое крупнее и уменьшаем — сглаженные края
W, H, FPS = 1920, 1080, 30
OUT_W, OUT_H = 1280, 720  # ADR-0074: 720p
INK, MUTED, HOT, BG = (34, 31, 44), (140, 132, 128), (200, 52, 46), (246, 241, 233)
CROP = (430, 380, 1147, 1153)  # что видно из рисунка: нос, рот, глотка
K = 900 / (CROP[3] - CROP[1])
X0, Y0, PANEL_X = 70, 90, 1000
PREP = 1.6  # секунд на подготовку до первого звука
ZONES = ("Полость рта", "Горло", "Язык", "Губы", "Нос")

# Путь воздуха (координаты рисунка): трахея → глотка → над языком → губы → наружу.
PATH = [
    (598, 1150),
    (600, 1000),
    (606, 880),
    (625, 790),
    (680, 748),
    (780, 742),
    (880, 760),
    (930, 795),
    (975, 822),
    (1040, 824),
]
OUT = [(1100, 822), (1180, 818)]
_rnd = random.Random(7)  # фиксированное зерно: пересборка даёт тот же ролик
PARTICLES = [
    (_rnd.random(), _rnd.uniform(-1, 1), _rnd.uniform(0.7, 1.3), _rnd.uniform(-1, 1))
    for _ in range(280)
]


def font(index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_TEXT, size * SS, index=index)


def ease(x: float) -> float:
    c = min(max(x, 0.0), 1.0)
    return c * c * (3 - 2 * c)


def to_frame(p: tuple[float, float]) -> tuple[float, float]:
    return ((X0 + (p[0] - CROP[0]) * K) * SS, (Y0 + (p[1] - CROP[1]) * K) * SS)


@dataclass(frozen=True, slots=True)
class Kind:
    """Тип артикуляции: место звука, подпись, шаги и что двигается."""

    place: str
    label: str
    spot: tuple[float, float]
    zone: str
    steps: tuple[str, str]
    motion: str  # glottal — связки; tap — удар кончиком; sib — щель у нижних зубов; lips — губы


KINDS = {
    "glottal": Kind("глубина горла", "глубина горла", GLOTTIS, "Горло",
                    ("1. Голосовые связки смыкаются", "2. Лёгкий толчок — и сразу гласный"), "glottal"),
    "tap": Kind("кончик языка · бугорок за зубами", "бугорок за зубами", RIDGE, "Язык",
                ("1. Кончик языка — к бугорку за зубами", "2. Один лёгкий удар — «р»"), "tap"),
    "sib": Kind("кончик языка · нижние зубы", "у нижних зубов", (944.0, 826.0), "Язык",
                ("1. Кончик языка — к нижним зубам", "2. Воздух со свистом, голос звучит"), "sib"),
    "lips": Kind("обе губы", "обе губы", LIPS, "Губы",
                 ("1. Сомкни губы", "2. Воздух давит на губы"), "lips"),
}  # fmt: skip


def _along(
    path: Sequence[tuple[float, float]], u: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    seg = [math.dist(a, b) for a, b in itertools.pairwise(path)]
    d = max(0.0, u) * sum(seg)
    for (a, b), length in zip(itertools.pairwise(path), seg, strict=True):
        if d <= length:
            r = d / length
            return (a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r), (
                (b[0] - a[0]) / length,
                (b[1] - a[1]) / length,
            )
        d -= length
    return path[-1], (1.0, 0.0)


def pose_at(
    motion: str,
    vowels: Sequence[str],
    heavy: Sequence[bool],
    t: float,
    events: Sequence[tuple[float, float]],
) -> Pose:
    """Поза рта в момент ``t``: подготовка согласного перед каждым слогом, затем гласный."""
    tip = back = 0.0
    acc = {"jaw": 0.0, "lift": 0.0, "protrude": 0.0, "spread": 0.0}
    for k, (s, e) in enumerate(events):
        pre = PREP if k == 0 else 0.16
        if motion == "tap":
            if s - pre < t < s:
                tip = max(tip, ease((t - (s - pre)) / (pre * 0.7)))
            if s <= t < s + 0.08:
                tip = max(tip, 1 - ease((t - s) / 0.08))
        if motion == "sib" and s - pre < t < s + 0.03:
            tip = max(tip, 0.7 * ease((t - (s - pre)) / (pre * 0.6)) * (1 - ease((t - s) / 0.06)))
        w = ease((t - s + 0.02) / 0.09) * (1 - ease((t - e) / 0.12))
        if w > 0:
            v = VOWELS[vowels[k]]
            acc["jaw"] += v.jaw * w
            acc["lift"] += v.lift * w
            acc["protrude"] += v.protrude * w
            acc["spread"] += v.spread * w
            back = max(back, float(heavy[k]) * w)
    target = RIDGE if motion == "tap" else LOWER_TEETH
    return Pose(tip=tip, back=back, tip_target=target, **acc)


def _particles(
    motion: str, t: float, events: Sequence[tuple[float, float]], layer: Image.Image
) -> None:
    d = ImageDraw.Draw(layer)
    first, last = events[0][0], events[-1][1]
    flow = ease((t - (first - PREP + 0.1)) / 0.6)
    if flow <= 0:
        return
    block = {"glottal": 0.03, "tap": 0.86, "lips": 0.965}.get(motion)  # где воздух копится до звука
    for ph, off, sp, spread in PARTICLES:
        started = [s for s, _ in events if s <= t]
        if not started:
            u = (ph + t * 0.45 * sp) % 1.0
            if block is not None:
                press = ease((t - (first - PREP * 0.7)) / (PREP * 0.7))
                lim = block - 0.012 * abs(off) * (1 - 0.8 * press)
                u = min(u, lim) if block > 0.5 else min(u * 0.25, lim)
            (x, y), (tx, ty) = _along(PATH, u)
            width = 3 if motion == "sib" and u > 0.85 else 9
            x, y, alpha = x - ty * off * width, y + tx * off * width, int(170 * flow)
        else:
            dt = t - started[-1]
            if ph < 0.4:  # облачко на выходе
                dist = (60 + 300 * sp) * (1 - math.exp(-dt * 3.2))
                ang = spread * 0.55
                x, y = 1040 + dist * math.cos(ang), 824 + dist * math.sin(ang) + 30 * spread * dt
                alpha = int(220 * max(0.0, 1 - dt / 1.4))
            else:  # поток во время гласного
                live = max(0.0, 1 - max(0.0, t - last - 0.1) / 0.5)
                u = (ph + t * 0.9 * sp) % 1.15
                (x, y), (tx, ty) = _along([*PATH, *OUT], min(u, 1.0))
                x, y = x - ty * off * 9, y + tx * off * 9
                alpha = int(170 * live * (1 - max(0.0, u - 0.9) * 4))
            if alpha <= 0:
                continue
        px, py = to_frame((x, y))
        r = (1.8 + 1.6 * sp) * SS
        d.ellipse((px - r, py - r, px + r, py + r), fill=(225, 244, 255, max(0, min(255, alpha))))
    if motion == "sib":  # свистящие штрихи у зубов
        for s, _ in events:
            if s - 0.3 < t < s + 0.25:
                for j in range(6):
                    q = (t * 7 + j / 6) % 1
                    ax, ay = to_frame((965 + q * 120, 822 + (j - 2.5) * 5))
                    bx, by = to_frame((991 + q * 120, 822 + (j - 2.5) * 5))
                    d.line((ax, ay, bx, by), fill=(235, 250, 255, int(220 * (1 - q))), width=3 * SS)


@dataclass(frozen=True, slots=True)
class Clip:
    """Что рисуем: крупный текст, название, тип артикуляции, слоги (одна или три плашки)."""

    title: str
    name: str
    kind: Kind
    syllables: tuple[tuple[str, str, str, bool], ...]  # (арабский, «ра», огласовка a/i/u, твёрдая)


def _base(clip: Clip) -> tuple[Image.Image, Image.Image, int]:
    aw = int((CROP[2] - CROP[0]) * K * SS)
    im = Image.new("RGB", (W * SS, H * SS), BG)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (X0 * SS, (Y0 + 10) * SS, X0 * SS + aw, (Y0 + 910) * SS), 36 * SS, fill=(60, 30, 20, 60)
    )
    sh = sh.filter(ImageFilter.GaussianBlur(20 * SS))
    im.paste(sh, (0, 0), sh)
    d = ImageDraw.Draw(im)
    d.text(
        ((PANEL_X + 330) * SS, 190 * SS),
        clip.title,
        font=ImageFont.truetype(FONT_ARABIC, 220 * SS),
        fill=INK,
        anchor="mm",
    )
    d.text(((PANEL_X + 330) * SS, 360 * SS), clip.name, font=font(BOLD, 56), fill=INK, anchor="mm")
    d.text((PANEL_X * SS, 420 * SS), "Место звука", font=font(MEDIUM, 26), fill=MUTED)
    d.text((PANEL_X * SS, 452 * SS), clip.kind.place, font=font(BOLD, 38), fill=HOT)
    d.text(
        (PANEL_X * SS, 868 * SS),
        "5 областей, где рождаются звуки",
        font=font(MEDIUM, 20),
        fill=MUTED,
    )
    for i, z in enumerate(ZONES):
        on, x = z == clip.kind.zone, (PANEL_X + i * 136) * SS
        d.rounded_rectangle(
            (x, 900 * SS, x + 126 * SS, 958 * SS), 29 * SS, fill=HOT if on else (232, 225, 216)
        )
        d.text(
            (x + 63 * SS, 929 * SS),
            z,
            font=font(DEMI if on else MEDIUM, 21 if len(z) < 7 else 17),
            fill="white" if on else MUTED,
            anchor="mm",
        )
    mask = Image.new("L", (aw, 900 * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, aw, 900 * SS), 36 * SS, fill=255)
    return im, mask, aw


def _overlay(
    d: ImageDraw.ImageDraw, clip: Clip, t: float, events: Sequence[tuple[float, float]]
) -> None:
    for s, _ in events:  # звуковые волны от губ
        for j in range(2):
            p = (t - s - j * 0.15) / 0.8
            if 0 < p < 1:
                sx, sy = to_frame((1046, 824))
                r = (30 + 160 * p) * SS
                d.arc(
                    (sx - r, sy - r, sx + r, sy + r),
                    -40,
                    40,
                    fill=(255, 255, 255, int(200 * (1 - p))),
                    width=5 * SS,
                )
    sx, sy = to_frame(clip.kind.spot)  # место звука
    r = (26 + 4 * (0.5 + 0.5 * math.sin(t * 6))) * SS
    d.ellipse((sx - r, sy - r, sx + r, sy + r), outline=(255, 255, 255, 230), width=7 * SS)
    d.ellipse((sx - r, sy - r, sx + r, sy + r), outline=HOT, width=4 * SS)
    lx, ly = to_frame((830, 1050))
    d.line((sx, sy + r, lx, ly - 26 * SS), fill="white", width=4 * SS)
    f = font(DEMI, 28)
    tw = d.textlength(clip.kind.label, font=f)
    d.rounded_rectangle(
        (lx - tw / 2 - 18 * SS, ly - 26 * SS, lx + tw / 2 + 18 * SS, ly + 26 * SS),
        26 * SS,
        fill=HOT,
    )
    d.text((lx, ly), clip.kind.label, font=f, fill="white", anchor="mm")
    first = events[0][0]
    current = 0 if t < first - PREP * 0.45 else 1 if t < first - 0.05 else 2
    steps = list(clip.kind.steps)
    if len(clip.syllables) == 1:
        ar, ru, v, _ = clip.syllables[0]
        steps.append(
            "3. "
            + {"a": "Открой рот", "i": "Губы слегка растяни", "u": "Губы кружком вперёд"}[v]
            + f" — «{ru}»"
        )
    for i, s in enumerate(steps):
        on = i == current
        if on:
            d.rounded_rectangle(
                (
                    (PANEL_X - 14) * SS,
                    (530 + i * 54 - 6) * SS,
                    (PANEL_X + 760) * SS,
                    (530 + i * 54 + 42) * SS,
                ),
                14 * SS,
                fill=(255, 255, 255),
            )
        d.text(
            (PANEL_X * SS, (530 + i * 54) * SS),
            s,
            font=font(DEMI if on else MEDIUM, 29),
            fill=INK if on else MUTED,
        )
    if len(clip.syllables) > 1:  # три плашки: звучащий слог — красный
        ar_font = ImageFont.truetype(FONT_ARABIC, 64 * SS)
        on_k = -1
        for k, (s, e) in enumerate(events):
            end = events[k + 1][0] - 0.08 if k + 1 < len(events) else e + 0.5
            if s - 0.08 <= t < end:
                on_k = k
        for k, (ar, ru, _, _) in enumerate(clip.syllables):
            x, y, on = (PANEL_X + k * 250) * SS, 660 * SS, k == on_k
            d.rounded_rectangle(
                (x, y, x + 230 * SS, y + 150 * SS), 24 * SS, fill=HOT if on else (255, 255, 255)
            )
            d.text(
                (x + 115 * SS, y + 62 * SS),
                ar,
                font=ar_font,
                fill="white" if on else INK,
                anchor="mm",
            )
            d.text(
                (x + 115 * SS, y + 122 * SS),
                f"«{ru}»",
                font=font(DEMI, 28),
                fill="white" if on else MUTED,
                anchor="mm",
            )


def render(
    head: Head,
    clip: Clip,
    audio: Path,
    events: Sequence[tuple[float, float]],
    audio_seconds: float,
    out: Path,
) -> None:
    """``events`` — слоги в секундах записи; ролик начинается с подготовки ``PREP``."""
    delay = PREP + 0.6 - events[0][0] + (0.12 if clip.kind.motion != "glottal" else 0.0)
    ev = [(delay + s, delay + max(e, s + (0.45 if len(events) == 1 else 0.18))) for s, e in events]
    duration = delay + audio_seconds + 1.8
    base, mask, aw = _base(clip)
    card = Image.new("L", base.size, 0)
    card.paste(mask, (X0 * SS, Y0 * SS))
    vowels = [v for _, _, v, _ in clip.syllables]
    heavy = [h for _, _, _, h in clip.syllables]
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(audio), "-filter_complex", f"[0:v]scale={OUT_W}:{OUT_H}:flags=lanczos[v];[1:a]adelay={int(delay * 1000)}:all=1,apad[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{duration:.2f}", "-c:v", "libx264", "-crf", "23", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert ff.stdin is not None  # noqa: S101
    for i in range(int(duration * FPS)):
        t = i / FPS
        im = base.copy()
        pose = pose_at(clip.kind.motion, vowels, heavy, t, ev)
        art = head.pose(pose).crop(CROP).resize((aw, 900 * SS), Image.Resampling.LANCZOS)
        im.paste(art, (X0 * SS, Y0 * SS), mask)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        _particles(clip.kind.motion, t, ev, layer)
        glow = layer.filter(ImageFilter.GaussianBlur(5 * SS))
        for lay in (glow, glow, layer):
            alpha = Image.fromarray(np.minimum(np.asarray(lay.split()[3]), np.asarray(card)))
            im.paste(lay, (0, 0), alpha)
        _overlay(ImageDraw.Draw(im, "RGBA"), clip, t, ev)
        frame = im.resize((W, H), Image.Resampling.LANCZOS)
        if t < 0.4:
            frame = Image.blend(Image.new("RGB", (W, H), BG), frame, ease(t / 0.4))
        ff.stdin.write(frame.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg не собрал {out}")
