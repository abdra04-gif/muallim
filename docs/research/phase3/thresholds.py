# ruff: noqa: E501, PERF401
"""Thresholds of the three answers for the card variants with MostafaMaroof (ADR-0086 point 6, ADR-0087).

margin = log-probability of the correct reading − of the best error variant.
    margin >= PASS            → "passed"
    ERROR <= margin < PASS    → "say it again"
    margin < ERROR            → "error"
Measured on:
    840 learner syllables (align_check.py output): correct recordings, and the same recordings checked as if
        another vowel or a look-alike letter had been asked (a sure error — what an obvious error looks like);
    200 correct whole ayahs (results/compare_models_ayahs.json, the lowest margin of each ayah).

Usage (from the project root):
    python docs/research/phase3/thresholds.py ALIGN_DIR OUT_JSON
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from align_check import PAIRS
from variants_check import N_LETTERS, N_VOWELS, decide

GRID = [-8.0, -6.0, -5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0]
AYAHS = Path(__file__).parent / "results" / "compare_models_ayahs.json"


def share(x: np.ndarray) -> float:
    return round(100 * float(x.mean()), 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("align", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    data = json.loads((args.align / "align.json").read_text(encoding="utf-8"))
    names = data["summary"]["names"]
    blank = len(names) - 1
    frames = np.load(args.align / "align_clips.npz")

    good, look, vowel = [], [], []
    for r in data["rows"]:
        lp = frames[f"{r['item']}-{r['clip']}"].astype(np.float32)
        li, vi = names.index(r["letter"]), names.index(r["vowel"])
        good.append(decide(lp, li, vi, names, blank)["margin"])
        ln = names[li]
        for a, b in PAIRS:
            other = b if a == ln else a if b == ln else None
            if other and other in names:
                look.append(decide(lp, names.index(other), vi, names, blank)["margin"])
        for j in range(N_LETTERS, N_LETTERS + N_VOWELS):
            if j != vi:
                vowel.append(decide(lp, li, j, names, blank)["margin"])
    g, sl, sv = np.array(good), np.array(look), np.array(vowel)
    ay = json.loads(AYAHS.read_text(encoding="utf-8"))
    w = np.array([a["maroof"][0] for a in ay["ayahs"]])

    curve = {
        str(t): {
            "correct_syllable_passed": share(g >= t),
            "correct_syllable_scolded": share(g < t),
            "other_vowel_missed": share(sv >= t),
            "lookalike_missed": share(sl >= t),
            "correct_ayah_flagged": share(w < t),
        }
        for t in GRID
    }
    out = {
        "counts": {
            "syllables": len(g),
            "other_vowel": len(sv),
            "lookalike": len(sl),
            "ayahs": len(w),
        },
        "curve": curve,
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
