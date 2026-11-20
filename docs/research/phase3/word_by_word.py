"""A second accepted reading for MostafaMaroof: every word on its own, with a stop (ADR-0088).

MostafaMaroof was trained on transcriptions where each word is written as if read alone (§11.8i):
no tanwin at the word end, no merge with the next word, no long vowel shortened before the next
word's sukun. Here that reading is built from the bot's own phonetiser — each word of the text
phonetised separately with a stop, the pieces joined — and accepted alongside the book's (Hafs)
reading. On the 200 cached correct ayahs: how often the model prefers the dataset transcription to
what the bot accepts, before and after adding the word-by-word reading.

Usage (from the project root, with the bot's phonetiser installed):
    python docs/research/phase3/word_by_word.py WAV_DIR LOGPROBS.npz OUT_JSON
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from muallim.infrastructure.asr.ctc import ctc_logprob, prepare  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402
from muallim.infrastructure.asr.phonetizer import _references  # noqa: E402


def word_by_word(text: str) -> tuple[str, ...]:
    out: list[str] = []
    for word in text.split():
        try:
            refs = dict(_references(word)[1])
        except Exception:  # noqa: BLE001, S112 — a stop sign or a sign alone is not a word
            continue
        out.extend(to_maroof(refs["waqf"]))
    return tuple(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    mv = json.loads(
        Path(hf_hub_download("MostafaMaroof/wav2vec2-arabic-phoneme-asr", "vocab.json")).read_text(
            encoding="utf-8"
        )
    )
    lps = np.load(args.cache)
    blank = mv["[PAD]"]
    book, both = [], []
    for line in (args.wavs / "refs_ayah.tsv").read_text(encoding="utf-8").splitlines():
        pid, phon, _t, uthmani, _w = line.split("\t")
        if pid not in lps.files:
            continue
        gold = [t.lower() if t in {"A", "I", "U", "AA", "II", "UU"} else t for t in phon.split()]
        hafs = to_maroof(dict(_references(uthmani)[1])["waqf"])
        words = word_by_word(uthmani)
        if any(t not in mv for t in (*gold, *hafs, *words)):
            continue
        lp = prepare(lps[pid], mv, long_is_short=False)

        def score(seq: tuple[str, ...] | list[str], lp: np.ndarray = lp) -> float:
            return ctc_logprob(lp, [mv[t] for t in seq], blank)

        g = score(gold)
        book.append(score(hafs) - g)
        both.append(float(np.logaddexp(score(hafs), score(words))) - g)

    def stats(v: list[float]) -> dict[str, float]:
        a = np.array(v)
        return {
            "ayahs": len(a),
            "accepted_not_behind_pct": round(100 * float((a >= 0).mean()), 1),
            "behind_by_more_than_4_pct": round(100 * float((a < -4).mean()), 1),
            "median": round(float(np.median(a)), 2),
        }

    out = {"book_reading_only": stats(book), "book_or_word_by_word": stats(both)}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
