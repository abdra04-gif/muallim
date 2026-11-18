# ruff: noqa: PERF401
"""Phase 3, step 4 prototype: choose among the card's variants (the answer the learner will see).

For each card the bot knows the correct reading and the typical errors. For a single syllable:
    correct          letter + its vowel (a held / long vowel counts as correct)
    other vowel      letter + each of the other two vowels
    no vowel         letter alone (as if read with sukun)
    look-alike       each confusable letter + the same vowel
The model scores how likely the recording is under each variant (CTC forward probability over
the frame log-probabilities saved by align_check.py); the most likely variant wins. Passed if the
correct one wins by at least MARGIN; otherwise the bot names the winning error. No training.

"Swap" trials, as in align_check.py: the same recording checked as if a look-alike letter or another
vowel had been asked — then the correct answer for the bot is to name the error.

Usage (from the project root):
    python docs/research/phase3/variants_check.py ALIGN_DIR
Writes ALIGN_DIR/variants.json.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from align_check import PAIRS

N_LETTERS, N_VOWELS = 28, 3
MARGINS = [0.0, 2.0, 4.0]


def ctc_logprob(lp: np.ndarray, target: list[int], blank: int) -> float:
    """log P(target | audio) under CTC: sum over all alignments (forward algorithm)."""
    ext = [blank]
    for t in target:
        ext += [t, blank]
    s_n = len(ext)
    alpha = np.full(s_n, -np.inf)
    alpha[0] = lp[0, ext[0]]
    if s_n > 1:
        alpha[1] = lp[0, ext[1]]
    for f in range(1, lp.shape[0]):
        prev = alpha.copy()
        for s in range(s_n):
            terms = [prev[s]]
            if s >= 1:
                terms.append(prev[s - 1])
            if s >= 2 and ext[s] != blank and ext[s] != ext[s - 2]:
                terms.append(prev[s - 2])
            alpha[s] = np.logaddexp.reduce(terms) + lp[f, ext[s]]
    return float(np.logaddexp(alpha[-1], alpha[-2]) if s_n > 1 else alpha[-1])


def variants(letter: int, vowel: int, names: list[str]) -> list[tuple[str, list[int]]]:
    out = [("correct", [letter, vowel])]
    for j in range(N_LETTERS, N_LETTERS + N_VOWELS):
        if j != vowel:
            out.append((f"vowel:{names[j]}", [letter, j]))
    out.append(("no vowel", [letter]))
    ln = names[letter]
    for a, b in PAIRS:
        other = b if a == ln else a if b == ln else None
        if other and other in names:
            out.append((f"letter:{other}", [names.index(other), vowel]))
    return out


def decide(lp: np.ndarray, letter: int, vowel: int, names: list[str], blank: int) -> dict:
    scored = [(lab, ctc_logprob(lp, seq, blank)) for lab, seq in variants(letter, vowel, names)]
    correct = scored[0][1]
    best_err = max(scored[1:], key=lambda x: x[1])
    return {"margin": round(correct - best_err[1], 3), "rival": best_err[0]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("align", type=Path)
    args = parser.parse_args()
    data = json.loads((args.align / "align.json").read_text(encoding="utf-8"))
    names = data["summary"]["names"]
    blank = len(names) - 1
    frames = np.load(args.align / "align_clips.npz")

    rows, swap_l, swap_v = [], [], []
    for r in data["rows"]:
        lp = frames[f"{r['item']}-{r['clip']}"].astype(np.float32)
        li, vi = names.index(r["letter"]), names.index(r["vowel"])
        res = decide(lp, li, vi, names, blank)
        rows.append({"item": r["item"], "clip": r["clip"], **res})
        ln = names[li]
        for a, b in PAIRS:
            other = b if a == ln else a if b == ln else None
            if other and other in names:
                swap_l.append(decide(lp, names.index(other), vi, names, blank)["margin"])
        for j in range(N_LETTERS, N_LETTERS + N_VOWELS):
            if j != vi:
                swap_v.append(decide(lp, li, j, names, blank)["margin"])

    g = np.array([r["margin"] for r in rows])
    sl, sv = np.array(swap_l), np.array(swap_v)
    summary = {
        "clips": len(rows),
        "swap_letter_trials": len(sl),
        "swap_vowel_trials": len(sv),
        "margins": {},
    }
    for m in MARGINS:
        summary["margins"][str(m)] = {
            "correct_passed": round(100 * float((g >= m).mean()), 1),
            "lookalike_passed": round(100 * float((sl >= m).mean()), 1),
            "other_vowel_passed": round(100 * float((sv >= m).mean()), 1),
        }
    (args.align / "variants.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
