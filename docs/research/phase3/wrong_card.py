# ruff: noqa: E501, S311, PERF401
"""What the card variants answer when the learner said something else entirely (ADR-0086, ADR-0087).

Each of the 840 syllable recordings is checked against 3 cards of an unrelated syllable (another letter,
not a look-alike pair; any vowel) — e.g. a recording of "zu" against the card "ba". The honest answer is "error".

Three ways, thresholds of the card variants PASS / ERROR = 0 / -4 (§11.8f, option A):
    margin only  — the card variants alone (correct − best typical error);
    fit          — plus an absolute check: (card's correct reading − best free path) per frame (rejected:
                   either lets wrong syllables through or scolds the right ones);
    other syl.   — plus "another syllable" as a rival: correct − best syllable with another, not look-alike,
                   letter (28 letters × 3 vowels). Below AGAIN → "say it again", below WRONG → "error".
Usage (from the project root):
    python docs/research/phase3/wrong_card.py ALIGN_DIR OUT_JSON
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from align_check import PAIRS
from variants_check import N_LETTERS, N_VOWELS, ctc_logprob, decide

PASS, ERROR = 0.0, -4.0
FITS = [-0.1, -0.2, -0.3]
OTHER = [(0.0, -4.0), (-2.0, -6.0), (-3.0, -6.0), (-3.0, -8.0)]  # (AGAIN, WRONG)


def by_card(m: float) -> str:
    return "passed" if m >= PASS else "again" if m >= ERROR else "error"


def with_other(m: float, mo: float, again: float, wrong: float) -> str:
    if mo < wrong:
        return "error"
    if mo < again:
        return "again" if m >= ERROR else "error"
    return by_card(m)


def shares(answers: list[str]) -> dict[str, float]:
    return {
        a: round(100 * answers.count(a) / len(answers), 1) for a in ("passed", "again", "error")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("align", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    data = json.loads((args.align / "align.json").read_text(encoding="utf-8"))
    names = data["summary"]["names"]
    blank = len(names) - 1
    frames = np.load(args.align / "align_clips.npz")
    near = {(a, b) for a, b in PAIRS} | {(b, a) for a, b in PAIRS}
    vowels = range(N_LETTERS, N_LETTERS + N_VOWELS)
    rng = random.Random(0)

    def check(lp: np.ndarray, sc: dict, k: int, v: int) -> tuple[float, float, float]:
        m = decide(lp, k, v, names, blank)["margin"]
        fit = (sc[(k, v)] - float(lp.max(axis=1).sum())) / len(lp)
        rivals = [s for (a, _), s in sc.items() if a != k and (names[k], names[a]) not in near]
        return m, fit, sc[(k, v)] - max(rivals)

    own, wrong = [], []
    for r in data["rows"]:
        lp = frames[f"{r['item']}-{r['clip']}"].astype(np.float32)
        sc = {(k, v): ctc_logprob(lp, [k, v], blank) for k in range(N_LETTERS) for v in vowels}
        li, vi = names.index(r["letter"]), names.index(r["vowel"])
        own.append(check(lp, sc, li, vi))
        others = [k for k in range(N_LETTERS) if k != li and (names[li], names[k]) not in near]
        for k in rng.sample(others, 3):
            wrong.append(check(lp, sc, k, rng.randrange(N_LETTERS, N_LETTERS + N_VOWELS)))

    def both(rule: object) -> dict[str, dict[str, float]]:
        return {
            "own_card": shares([rule(*x) for x in own]),  # type: ignore[operator]
            "wrong_card": shares([rule(*x) for x in wrong]),  # type: ignore[operator]
        }

    out = {
        "recordings": len(own),
        "wrong_card_trials": len(wrong),
        "margin_only": both(lambda m, f, mo: by_card(m)),
        "fit": {str(c): both(lambda m, f, mo, c=c: "error" if f < c else by_card(m)) for c in FITS},
        "other_syllable": {
            f"{a}/{w}": both(lambda m, f, mo, a=a, w=w: with_other(m, mo, a, w)) for a, w in OTHER
        },
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
