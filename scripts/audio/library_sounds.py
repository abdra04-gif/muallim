"""Готовые записи «как правильно» для букв и слогов (ADR-0068) — без модели и без нарезки из чтения.

    uv run python scripts/audio/library_sounds.py

Источник букв и слогов — «Аль-Каида ан-Нурания» в чтении Мухаммада Фарука ар-Раи (SRC-144): каждую
букву и каждый слог он произносит отдельно, с паузой. Файлы по одному берём из копии приложения
ibr7h/al-qaida-nooraniyya (зафиксированный коммит), но подписи там местами сдвинуты — поэтому файл
выбираем по устройству урока, а не по подписи:
- урок 1: буквы алфавита по названию, f1-04 … f1-32 в порядке LETTERS;
- урок 4: на каждую букву 5 файлов подряд — фатха с проговариванием («ра — фатха — ра»), кясра,
  пара, дамма, тройка «рa ри ру»; порядок букв — VOWEL_ORDER.
Истиаза — аль-Афаси, EveryAyah (SRC-145).

Обрезаем только тишину по краям и перекодируем в OGG/Opus. Результат: curriculum/audio/library/
<хэш>.ogg, sounds.yaml и review.html (прослушать). Решения человека (status ok/bad, manual) при
пересборке сохраняются.
"""

import hashlib
import html
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml
from cuts_manifest import merge_manifest  # рядом: scripts/audio/cuts_manifest.py

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "curriculum" / "audio" / "library"
CACHE = Path.home() / ".cache" / "muallim" / "library"
RAAI_COMMIT = "2b8cf778f0096be1cc436cd098cfc70b014db162"
RAAI = (
    "https://raw.githubusercontent.com/ibr7h/al-qaida-nooraniyya/"
    + RAAI_COMMIT
    + "/assets/audio/{name}"
)
ALAFASY = "https://everyayah.com/data/Alafasy_128kbps/{name}"

FATHA, KASRA, DAMMA = "َ", "ِ", "ُ"
LETTERS = [
    "ا",
    "ب",
    "ت",
    "ث",
    "ج",
    "ح",
    "خ",
    "د",
    "ذ",
    "ر",
    "ز",
    "س",
    "ش",
    "ص",
    "ض",
    "ط",
    "ظ",
    "ع",
    "غ",
    "ف",
    "ق",
    "ك",
    "ل",
    "م",
    "ن",
    "و",
    "ه",
    "ء",
    "ي",
]
VOWEL_ORDER = [
    "أ",
    "ه",
    "ع",
    "ح",
    "غ",
    "خ",
    "ق",
    "ك",
    "ج",
    "ش",
    "ي",
    "ض",
    "ل",
    "ن",
    "ر",
    "ط",
    "د",
    "ت",
    "ص",
    "س",
    "ز",
    "ظ",
    "ذ",
    "ث",
    "ف",
    "و",
    "ب",
    "م",
]
TRIM = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse"
)


def plan() -> list[dict[str, object]]:
    """[{text, origin, source, manual?}] — какой текст каким файлом звучит."""
    rows: list[dict[str, object]] = []

    def raai(text: str, name: str) -> None:
        rows.append({"text": text, "origin": RAAI.format(name=name), "source": "SRC-144"})

    for i, letter in enumerate(LETTERS):
        raai(letter, f"f1-{i + 4:02d}.mp3")
    for g, letter in enumerate(VOWEL_ORDER):
        first = 2 + 5 * g
        fatha, kasra, damma = (
            (letter + FATHA, "إ" + KASRA, letter + DAMMA)
            if letter == "أ"
            else (letter + FATHA, letter + KASRA, letter + DAMMA)
        )
        raai(fatha, f"f4-{first:02d}.mp3")
        raai(kasra, f"f4-{first + 1:02d}.mp3")
        raai(damma, f"f4-{first + 3:02d}.mp3")
        raai(f"{fatha} {kasra} {damma}", f"f4-{first + 4:02d}.mp3")
    raai("بًا بٍ بٌ", "f5-11.mp3")  # урок 5, тройка с танвином
    raai("الٓمٓ", "f3-03.mp3")  # урок 3, «алиф лям мим»
    rows.append(
        {
            "text": "أَعُوذُ بِٱللَّهِ مِنَ ٱلشَّيْطَانِ ٱلرَّجِيمِ",
            "origin": ALAFASY.format(name="audhubillah.mp3"),
            "source": "SRC-145",
            "manual": True,
        }
    )
    return rows


def download(url: str) -> Path:
    path = CACHE / hashlib.sha256(url.encode()).hexdigest()[:16]
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "muallim/0.1"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 # адреса только из кода
            path.write_bytes(r.read())
        time.sleep(0.2)
    return path


def encode(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", TRIM, "-ac", "1",
         "-c:a", "libopus", "-b:a", "48k", str(dst)],
        check=True,
    )  # fmt: skip


def seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return round(float(out.stdout), 2)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "sounds.yaml"
    old = (
        {r["text"]: r for r in yaml.safe_load(manifest.read_text(encoding="utf-8")) or []}
        if manifest.is_file()
        else {}
    )
    rows = []
    for row in plan():
        text, origin = str(row["text"]), str(row["origin"])
        name = hashlib.sha256(f"{text}|{origin}".encode()).hexdigest()[:16] + ".ogg"
        dst = OUT / name
        if not dst.is_file():
            encode(download(origin), dst)
        prev = old.get(text, {})
        status = prev.get("status", "unchecked") if prev.get("file") == name else "unchecked"
        rows.append(
            {
                "text": text,
                "file": name,
                "status": status,
                "seconds": seconds(dst),
                **{k: v for k, v in row.items() if k != "text"},
            }
        )
    rows = merge_manifest(old.values(), rows)  # ручные строки и отклонённые не теряем
    for path in OUT.glob("*.ogg"):  # файлы, которых больше нет в списке
        if path.name not in {r["file"] for r in rows}:
            path.unlink()
    header = (
        "# Готовые записи «как правильно» (ADR-0068): ар-Раи, «Нурания» (SRC-144);\n"
        "# истиаза — аль-Афаси (SRC-145). Генерирует scripts/audio/library_sounds.py.\n"
        "# status: unchecked → человек слушает review.html и ставит ok или bad (bad бот не даёт).\n"
    )
    manifest.write_text(
        header + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    cards = "".join(
        f"<tr><td class=ar>{html.escape(r['text'])}</td>"
        f"<td><audio controls preload=none src='{r['file']}'></audio></td>"
        f"<td>{r['seconds']} с</td><td>{r['status']}</td><td>{r['source']}</td></tr>"
        for r in rows
    )
    (OUT / "review.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Готовые записи</title>"
        "<style>body{font:15px system-ui;margin:16px}"
        "td{padding:4px 10px;border-bottom:1px solid #ddd}.ar{font-size:26px;direction:rtl}</style>"
        f"<h1>Готовые записи букв и слогов ({len(rows)})</h1><table>{cards}</table>\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} записей → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
