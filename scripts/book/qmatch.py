"""Находит в Мединском мусхафе (Хафс, uthmani из quran_transcript) точный текст фразы.

На вход — фраза, набранная со скана приблизительно. Сравнение по «скелету» (буквы без огласовок,
варианты алифа/хамзы/йа сведены). Возвращает (сура, аят, точный текст) или None.
"""

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

import quran_transcript

BASE = Path(quran_transcript.__file__).parent / "quran-script"


def skel(w: str) -> str:
    w = unicodedata.normalize("NFC", w)
    out = []
    for ch in w:
        if unicodedata.category(ch) == "Mn" or ch in "ـۥۦ":
            continue
        ch = {
            "ٱ": "ا",
            "أ": "ا",
            "إ": "ا",
            "آ": "ا",
            "ى": "ي",
            "ئ": "ي",
            "ؤ": "و",
            "ة": "ه",
            "ء": "",
        }.get(ch, ch)
        out.append(ch)
    return "".join(out)


@lru_cache(maxsize=1)
def corpus():
    data = json.loads((BASE / "quran-uthmani-imlaey.json").read_text("utf-8"))["quran"]
    rows = []
    for sura in data["sura"]:
        for aya in sura["aya"]:
            words = aya["@uthmani"].split()
            rows.append((int(sura["@index"]), int(aya["@index"]), words, [skel(w) for w in words]))
    return rows


def loose(w: str) -> str:
    return w.replace("ا", "").replace("و", "").replace("ي", "")


def find(phrase: str):
    where = None
    if "@" in phrase:  # «фраза@сура:аят» — взять из этого аята
        phrase, ref = phrase.split("@")
        where = tuple(int(x) for x in ref.split(":"))
    hits = _find(phrase)
    return [h for h in hits if where is None or h[:2] == where]


def _find(phrase: str):
    target = [skel(w) for w in phrase.split()]
    target = [t for t in target if t]
    n = len(target)
    for key in (lambda x: x, loose):  # сначала точно по скелету, потом без букв-удлинителей
        want = [key(t) for t in target]
        hits = []
        for s, a, words, sk in corpus():
            ks = [key(x) for x in sk]
            hits.extend(
                (s, a, " ".join(words[i : i + n]))
                for i in range(len(ks) - n + 1)
                if ks[i : i + n] == want
            )
        if hits:
            return hits
    return []


if __name__ == "__main__":
    import sys

    for p in sys.argv[1:]:
        print(p, "->", find(p)[:3])
