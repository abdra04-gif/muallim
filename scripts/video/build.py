"""Собрать ролики «🎬 Как произносить» для букв (FR-56, ADR-0074): ``make videos a="ر ز"``.

Для буквы: запись-тройка ар-Раи из ``curriculum/audio/library`` (SRC-144, например «رَ رِ رُ») →
три слога вырезаются по паузам → 4 ролика (три слога и тройка, 720p) → ``curriculum/video/``
и строки ``videos.yaml`` со ``status: unchecked``. Бот показывает и непроверенные; плохой ролик
человек помечает ``status: bad``. Новая буква — строка в ``LETTERS`` (место звука и подсказки
утверждает человек, источник — ``scripts/book/theory.py``, SRC-059).
"""

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from articulate import Head
from render import KINDS, OUT_H, OUT_W, Clip, render

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "curriculum" / "audio" / "library"
VIDEO = ROOT / "curriculum" / "video"  # по умолчанию; флаг --out — другая папка
RATE = 16000

# буква → (тип артикуляции, название, [(слог, «как читается», огласовка, твёрдая)])
LETTERS: dict[str, tuple[str, str, list[tuple[str, str, str, bool]]]] = {
    "أ": ("glottal", "Алиф с хамзой", [("أَ", "а", "a", False), ("إِ", "и", "i", False), ("أُ", "у", "u", False)]),
    "ر": ("tap", "Ра", [("رَ", "ра", "a", True), ("رِ", "ри", "i", False), ("رُ", "ру", "u", True)]),
    "ز": ("sib", "Зай", [("زَ", "за", "a", False), ("زِ", "зи", "i", False), ("زُ", "зу", "u", False)]),
}  # fmt: skip

HEADER = """# Ролики «🎬 Как произносить» (ADR-0074, FR-56): рисунок — SRC-148 (P. J. Lynch, CC BY 2.5),
# звук — ар-Раи, «Нурания» (SRC-144); слоги вырезаны из троек по паузам (исключение из ADR-0068).
# status: unchecked → человек смотрит и ставит ok или bad (bad бот не показывает).
# Собирает scripts/video/build.py (make videos).
"""


def pcm(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32)


def loudness(x: np.ndarray, step: float) -> np.ndarray:
    n = int(RATE * step)
    lvl = np.array([np.sqrt((x[i : i + n] ** 2).mean()) for i in range(0, len(x), n)])
    return lvl / lvl.max()


def nuclei(x: np.ndarray, count: int) -> list[tuple[float, float]]:
    """Гласные ядра (громче 25 %), щелчки < 20 мс отброшены, лишние куски склеены с соседом."""
    loud = loudness(x, 0.01) > 0.25
    runs: list[list[float]] = []
    i = 0
    while i < len(loud):
        if loud[i]:
            j = i
            while j < len(loud) and loud[j]:
                j += 1
            if j - i >= 2:
                runs.append([i * 0.01, j * 0.01])
            i = j
        else:
            i += 1
    while len(runs) > count:  # самый короткий кусок — к ближайшему соседу
        k = min(range(len(runs)), key=lambda q: runs[q][1] - runs[q][0])
        left = runs[k][0] - runs[k - 1][1] if k > 0 else 9.0
        right = runs[k + 1][0] - runs[k][1] if k + 1 < len(runs) else 9.0
        if right <= left:
            runs[k][1] = runs[k + 1][1]
            del runs[k + 1]
        else:
            runs[k - 1][1] = runs[k][1]
            del runs[k]
    if len(runs) != count:
        raise ValueError(f"нашлось {len(runs)} слога вместо {count} — проверьте запись")
    return [(s, e) for s, e in runs]


def syllable_bounds(x: np.ndarray, nu: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Слог — от начала его согласного до конца гласного с коротким хвостом; промежутки выброшены."""
    step = 0.005
    lvl = loudness(x, step)
    total = len(x) / RATE
    out = []
    for k, (s, e) in enumerate(nu):
        lo = nu[k - 1][1] if k else 0.0
        hi = nu[k + 1][0] if k + 1 < len(nu) else total
        i, stop = int(s / step), int((lo + (s - lo) * 0.35) / step) if k else 0
        while i > stop and lvl[i - 1] > 0.05:
            i -= 1
        j = int(e / step)
        lim = min(int((e + 0.07) / step), int((e + (hi - e) * 0.4) / step), len(lvl) - 1)
        while j < lim and lvl[j] > 0.12:
            j += 1
        out.append((max(0.0, i * step - 0.01), j * step + 0.015))
    return out


def cut(src: Path, start: float, end: float, out: Path) -> None:
    af = f"atrim={start:.3f}:{end:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.008,areverse,afade=t=in:d=0.025,areverse,apad=pad_dur=0.15"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-af",
            af,
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            str(out),
        ],
        check=True,
    )


def library_file(text: str) -> Path:
    rows = yaml.safe_load((LIBRARY / "sounds.yaml").read_text(encoding="utf-8")) or []
    for row in rows:
        if row["text"] == text and row.get("status") != "bad":
            return LIBRARY / row["file"]
    raise SystemExit(f"в sounds.yaml нет записи «{text}»")


def seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return float(out)


def store(
    video: Path,
    tmp: Path,
    text: str,
    letter: str | None,
    origin: Path,
    rows: list[dict[str, object]],
) -> None:
    name = hashlib.sha256(tmp.read_bytes()).hexdigest()[:16] + ".mp4"
    old = next((r for r in rows if r["text"] == text), None)
    if old is not None and old["file"] == name:
        print(f"  {text}: без изменений")
        return
    (video / name).write_bytes(tmp.read_bytes())
    row: dict[str, object] = {"text": text}
    if letter:
        row["letter"] = letter
    row |= {"file": name, "seconds": round(seconds(video / name), 2), "width": OUT_W, "height": OUT_H,
            "status": "unchecked", "source": "SRC-144", "picture": "SRC-148",
            "origin": str(origin.relative_to(ROOT))}  # fmt: skip
    if old is not None:
        rows[rows.index(old)] = row
        if not any(r["file"] == old["file"] for r in rows):
            (video / str(old["file"])).unlink(missing_ok=True)
    else:
        rows.append(row)
    print(f"  {text}: {name} (unchecked)")


def build(video: Path, letter: str, head: Head, rows: list[dict[str, object]]) -> None:
    kind, name, syllables = LETTERS[letter]
    triple_text = " ".join(s for s, _, _, _ in syllables)
    src = library_file(triple_text)
    x = pcm(src)
    nu = nuclei(x, len(syllables))
    bounds = syllable_bounds(x, nu)
    print(f"{letter}: {src.name}, слоги {[(round(a, 2), round(b, 2)) for a, b in bounds]}")
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        for (ar, ru, v, heavy), (s, e) in zip(syllables, bounds, strict=True):
            piece = work / "syl.ogg"
            cut(src, s, e, piece)
            px = pcm(piece)
            out = work / "syl.mp4"
            clip = Clip(ar, ru.capitalize(), KINDS[kind], ((ar, ru, v, heavy),))
            render(head, clip, piece, nuclei(px, 1), len(px) / RATE, out)
            store(video, out, ar, None, src, rows)
        out = work / "triple.mp4"
        render(head, Clip(letter, name, KINDS[kind], tuple(syllables)), src, nu, len(x) / RATE, out)
        store(video, out, triple_text, letter, src, rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("letters", nargs="*", help="буквы, например: ر ز; пусто — все из LETTERS")
    p.add_argument("--out", type=Path, default=VIDEO, help="папка роликов (для пробы — временная)")
    args = p.parse_args()
    letters = args.letters or list(LETTERS)
    video: Path = args.out
    video.mkdir(parents=True, exist_ok=True)
    unknown = [x for x in letters if x not in LETTERS]
    if unknown:
        raise SystemExit(f"нет описания для {unknown}: добавьте в LETTERS (утверждает человек)")
    manifest = video / "videos.yaml"
    rows: list[dict[str, object]] = []
    if manifest.exists():
        rows = yaml.safe_load(manifest.read_text(encoding="utf-8")) or []
    head = Head()
    for letter in letters:
        build(video, letter, head, rows)
    manifest.write_text(
        HEADER + "\n" + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"→ {manifest}: {len(rows)} роликов")


if __name__ == "__main__":
    main()
