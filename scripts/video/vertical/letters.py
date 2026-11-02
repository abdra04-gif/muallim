# ruff: noqa
"""Вертикальные ролики букв в стиле басмалы: буква крупно, камера у места звука,
звук ар-Раи (SRC-144) трижды с пульсом, рот двигается, внизу «как сказать» и место (theory.py).

  uv run --group video python -I letters.py <artext> <папка> <буква> [секунды,для,кадров]
"""

import math
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "scripts" / "video"))
sys.path.insert(0, str(ROOT / "scripts" / "book"))

import numpy as np
import yaml
from articulate import (
    LIPS,
    CAVITY_MAX,
    MOUTH,
    PIVOT,
    RX0,
    RX1,
    RY0,
    RY1,
    Head,
    Pose,
    _border,
    _smooth,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from theory import LETTERS as THEORY

ARTEXT, OUTDIR, LETTER = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
TMP = OUTDIR / "parts"
TMP.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 30
OUT_W, OUT_H = 720, 1280
BG = (12, 18, 30)
IMG_W, IMG_H = 1147, 1153
GREEN, ORANGE, BLUE = (61, 220, 132), (255, 159, 67), (74, 168, 255)

# буква: имя (как в уроке), цвет, место на рисунке, что двигается, камера (x, y, масштаб)
SPEC = {
    "ب": ("Бэ", GREEN, LIPS, "lips", (960.0, 820.0, 2.5)),
    "ت": ("Тэ", ORANGE, (946.0, 790.0), "tip", (930.0, 800.0, 2.6)),
    "ث": ("Сэ", ORANGE, (968.0, 816.0), "teeth", (935.0, 810.0, 2.6)),
    "ج": ("Джим", BLUE, (845.0, 745.0), "mid", (880.0, 800.0, 2.4)),
}
NAME, COL, AT, MOTION, CAM = SPEC[LETTER]
PLACE = THEORY[LETTER].split("\n")[0]
HOW = THEORY[LETTER].split("\n")[1].removeprefix("Как сказать: ").split(". ")[0].rstrip(".")
HOW = HOW[0].upper() + HOW[1:]

lib = yaml.safe_load((ROOT / "curriculum/audio/library/sounds.yaml").read_text(encoding="utf-8"))
REC = ROOT / "curriculum/audio/library" / next(r["file"] for r in lib if r["text"] == LETTER)
SR = 48000
_raw = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", str(REC), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
    capture_output=True,
    check=True,
).stdout
X = np.frombuffer(_raw, np.float32)
REC_LEN = len(X) / SR
PLAYS = [1.1, 1.1 + REC_LEN + 1.0, 1.1 + 2 * (REC_LEN + 1.0)]
DUR = PLAYS[-1] + REC_LEN + 1.6


# --- щель перед губами в цвет фона (как в ролике басмалы) ---
def _jaw_dark(self, img: np.ndarray, p: Pose) -> np.ndarray:
    import math as m

    xx, yy = self.xx, self.yy
    lower = yy > _border(xx)
    w = _smooth((xx - 690) / 260) * (1 - _smooth((yy - 1010) / 80) * (1 - _smooth((xx - 900) / 60)))
    a = -m.radians(p.jaw) * w
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
    ax = np.clip(xx.astype(int), 0, img.shape[1] - 1)
    ay = np.clip((_border(xx) - 8).astype(int), 0, img.shape[0] - 1)
    inner = np.minimum(img[ay, ax], CAVITY_MAX)
    depth = np.clip((xx - 975) / 80, 0, 1)[..., None]
    mouth = MOUTH * (1 - 0.3 * depth) + np.array([150, 60, 60], np.float32) * 0.3 * depth
    fade_ = _smooth((xx - 1004 - p.protrude) / 12)[..., None]
    blend = _smooth((xx - 962) / 26)[..., None]
    fill = inner * (1 - blend) + (mouth * (1 - fade_) + np.array(BG, np.float32) * fade_) * blend
    out = np.where(gap[..., None], fill, out)
    res = img.copy()
    res[RY0:RY1, RX0:RX1] = out
    return res


Head._jaw = _jaw_dark


def ease(x: float) -> float:
    c = min(max(x, 0.0), 1.0)
    return c * c * (3 - 2 * c)


def window(t: float, a: float, b: float, fin: float = 0.3, fout: float = 0.3) -> float:
    return ease((t - a) / fin) * (1 - ease((t - b) / fout))


def sf(size: int, weight: str = "Semibold") -> ImageFont.FreeTypeFont:
    fnt = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
    try:
        fnt.set_variation_by_name(weight)
    except Exception:
        pass
    return fnt


def artext(text: str, size: int, color: str, name: str) -> Image.Image:
    p = TMP / f"{name}.png"
    subprocess.run([ARTEXT, text, str(size), str(p), color], check=True)
    return Image.open(p).convert("RGBA")


HEX = "%02X%02X%02X" % COL
BIG = artext(LETTER, 230, HEX, f"big{ord(LETTER)}")
PIN = artext(LETTER, 74, "FFFFFF", f"pin{ord(LETTER)}")


def fade(img: Image.Image, a: float) -> Image.Image:
    if a >= 1:
        return img
    img = img.copy()
    img.putalpha(img.split()[3].point(lambda v: int(v * a)))
    return img


def pose(t: float) -> Pose:
    """Перед каждым звуком — подготовка согласного, на звуке — «а» (имя буквы)."""
    jaw = lift = tip = back = 0.0
    target = AT
    for s in PLAYS:
        prep = window(t, s - 0.55, s + 0.06, 0.3, 0.1)
        if MOTION in ("tip", "teeth"):
            tip = max(tip, prep)
        if MOTION == "mid":
            back = max(back, prep * 0.8)
        o = window(t, s + 0.08, s + REC_LEN - 0.1, 0.1, 0.25)
        jaw, lift = max(jaw, 3.6 * o), max(lift, 4.5 * o)
    if MOTION == "lips":  # губы сомкнуты до звука, раскрываются на звуке
        pass
    return Pose(jaw=jaw, lift=lift, tip=tip, back=back, tip_target=target)


WHITE: Image.Image | None = None


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
    return Image.fromarray((a * keep + np.array(BG, np.float32) * (1 - keep)).astype(np.uint8))


def to_screen(p: tuple[float, float], c: tuple[float, float, float]) -> tuple[float, float]:
    cx, cy, s = c
    return (W / 2 + (p[0] - cx) * s, H / 2 + (p[1] - cy) * s)


def cam(t: float) -> tuple[float, float, float]:
    wide = (CAM[0] - 60, CAM[1] - 40, CAM[2] * 0.8)
    u = ease((t - 0.2) / 0.9)  # въезд к месту звука
    return tuple(a + (b - a) * u for a, b in zip(wide, CAM))  # type: ignore[return-value]


def pin(
    d: ImageDraw.ImageDraw, lay: Image.Image, xy: tuple[float, float], a: float, burst: float
) -> None:
    x, y = xy
    r = 58
    if 0 < burst < 1:
        al = int(235 * (1 - burst) * a)
        rr = r + 8 + 70 * burst
        d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=(*COL, al), width=5)
        for j in range(24):
            ang = j * math.pi / 12
            r1 = r + 6 + 26 * burst
            r2 = r1 + 16 + 34 * burst * (0.6 + 0.4 * math.sin(j * 2.3))
            d.line(
                (
                    x + r1 * math.cos(ang),
                    y + r1 * math.sin(ang),
                    x + r2 * math.cos(ang),
                    y + r2 * math.sin(ang),
                ),
                fill=(*COL, al),
                width=4,
            )
    d.ellipse((x - r, y - r, x + r, y + r), fill=(20, 24, 34, int(150 * a)))
    d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, int(200 * a)), width=3)
    d.ellipse((x - r + 5, y - r + 5, x + r - 5, y + r - 5), outline=(*COL, int(255 * a)), width=7)
    li = fade(PIN, a)
    lay.paste(li, (int(x - li.width / 2), int(y - li.height / 2 + 5)), li)


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int, d: ImageDraw.ImageDraw) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        nxt = f"{cur} {w}".strip()
        if d.textlength(nxt, font=font) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    return [*lines, cur]


def frame(i: int, head: Head) -> Image.Image:
    t = i / FPS
    c = cam(t)
    im = head_view(head.pose(pose(t)), c)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    a = ease((t - 0.1) / 0.4)

    # шапка: буква крупно, имя
    band = Image.new("RGBA", (W, 560), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(560):
        bd.line((0, y, W, y), fill=(*BG, int(240 * min(1.0, (560 - y) / 200))))
    lay.alpha_composite(band)
    playing = any(s <= t < s + REC_LEN for s in PLAYS)
    big = (
        BIG
        if not playing
        else BIG.resize((int(BIG.width * 1.06), int(BIG.height * 1.06)), Image.Resampling.LANCZOS)
    )
    big = fade(big, a)
    lay.paste(big, (int(W / 2 - big.width / 2), int(215 - big.height / 2)), big)
    d.text((W / 2, 430), NAME, font=sf(64), anchor="mm", fill=(240, 240, 245, int(255 * a)))

    # место звука — пульс на каждом звуке
    burst = -1.0
    for s in PLAYS:
        if s - 0.05 <= t < s + 0.9:
            burst = (t - s + 0.05) / 0.9
    pin(d, lay, to_screen(AT, c), ease((t - 0.7) / 0.4), burst)

    # внизу: как сказать + место
    ca = ease((t - 0.9) / 0.4)
    yb = 1480
    d.rounded_rectangle((36, yb, W - 36, yb + 360), 34, fill=(16, 22, 34, int(215 * ca)))
    d.ellipse((66, yb + 34, 156, yb + 124), fill=(*COL, int(255 * ca)))
    li = fade(
        artext(LETTER, 48, "FFFFFF", f"cap{ord(LETTER)}")
        if False
        else PIN.resize((52, int(PIN.height * 52 / PIN.width))),
        ca,
    )
    lay.paste(li, (int(111 - li.width / 2), int(yb + 79 - li.height / 2 + 4)), li)
    fh = sf(44)
    y = yb + 40
    for line in wrap(HOW, fh, W - 260, d)[:2]:
        d.text((184, y), line, font=fh, fill=(*COL, int(255 * ca)))
        y += 54
    fp = sf(36, "Regular")
    y = max(y + 18, yb + 160)
    for line in wrap(PLACE, fp, W - 140, d)[:3]:
        d.text((70, y), line, font=fp, fill=(225, 228, 236, int(255 * ca)))
        y += 46

    # в конце — «повтори вслух»
    ea = window(t, PLAYS[-1] + REC_LEN + 0.2, DUR, 0.4, 0.6)
    if ea > 0:
        d.rounded_rectangle((180, 1330, W - 180, 1440), 55, fill=(255, 212, 121, int(235 * ea)))
        d.text(
            (W / 2, 1385),
            "Твоя очередь: повтори вслух",
            font=sf(42),
            anchor="mm",
            fill=(12, 18, 30, int(255 * ea)),
        )

    glow = lay.filter(ImageFilter.GaussianBlur(7))
    im.paste(glow, (0, 0), glow.split()[3].point(lambda v: v // 3))
    im.paste(lay, (0, 0), lay)
    if t < 0.4:
        im = Image.blend(Image.new("RGB", (W, H), BG), im, ease(t / 0.4))
    if t > DUR - 0.5:
        im = Image.blend(im, Image.new("RGB", (W, H), BG), ease((t - DUR + 0.5) / 0.5))
    return im


def main() -> None:
    global WHITE
    head = Head()
    rest = np.asarray(head.pose(Pose())).astype(np.float32)
    WHITE = Image.fromarray(
        (np.clip((rest.min(axis=2) - 225) / 25, 0, 1) * 255).astype(np.uint8)
    ).filter(ImageFilter.GaussianBlur(1.2))
    if len(sys.argv) > 4:
        for s in sys.argv[4].split(","):
            frame(int(float(s) * FPS), head).save(OUTDIR / f"{ord(LETTER)}_{s}.png")
        return
    track = np.zeros(int((DUR + 0.5) * SR), np.float32)
    for s in PLAYS:
        i0 = int(s * SR)
        track[i0 : i0 + len(X)] += X
    wav = OUTDIR / f"{ord(LETTER)}.wav"
    import wave

    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())
    out = OUTDIR / f"{ord(LETTER)}.mp4"
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
        str(wav),
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
        str(out),
    ]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(DUR * FPS)
    for i in range(n):
        ff.stdin.write(frame(i, head).tobytes())
        if i % 30 == 0:
            print(f"{LETTER} кадр {i}/{n}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"{LETTER} готово {out} {DUR:.2f}", flush=True)


if __name__ == "__main__":
    main()
