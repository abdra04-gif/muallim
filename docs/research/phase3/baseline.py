# ruff: noqa: E501
"""Baseline "before training": one row per recording with what every method heard and decided.

The same table is produced again after training; comparing the two row by row shows what changed.

Usage (from the project root):
    python docs/research/phase3/baseline.py ALIGN_DIR DEMO_JSON OUT_CSV
ALIGN_DIR — output of align_check.py; DEMO_JSON — output of demo_data.py.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

N_LETTERS, N_VOWELS = 28, 3
PASS_AT = 0.0

FIELDS = [
    "item", "student", "asked",
    "bot_heard", "bot_score", "bot_verdict", "bot_errors",
    "list84_best", "list84_p_asked", "list84_decision",
    "sound_letter_heard", "sound_letter_conf", "sound_letter_gop",
    "sound_vowel_heard", "sound_vowel_conf", "sound_vowel_gop", "sound_decision",
    "variants_rival", "variants_margin", "variants_decision",
    "maroof_heard", "espeak_heard", "tarteel_heard", "whisper_heard",
    "models_disagreeing_with_asked", "teacher_heard", "teacher_verdict",
]  # fmt: skip


def top(lp: np.ndarray, span: list[int], rng: range) -> tuple[int, float]:
    a, b = span
    if b <= a:
        return -1, 0.0
    m = lp[a:b].astype(np.float32).mean(axis=0)
    best = max(rng, key=lambda i: m[i])
    return best, math.exp(float(m[best]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("align", type=Path)
    parser.add_argument("demo", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    data = json.loads((args.align / "align.json").read_text(encoding="utf-8"))
    names = data["summary"]["names"]
    frames = np.load(args.align / "align_clips.npz")
    vpath = args.align / "variants.json"
    var = (
        {(v["item"], v["clip"]): v for v in json.loads(vpath.read_text(encoding="utf-8"))["rows"]}
        if vpath.exists()
        else {}
    )
    demo = {it["name"]: it for it in json.loads(args.demo.read_text(encoding="utf-8"))}

    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in data["rows"]:
            item = demo[r["item"]]
            d = item["clips"][r["clip"] - 1]
            lp = frames[f"{r['item']}-{r['clip']}"]
            bl, pl = top(lp, r["spans"][0], range(N_LETTERS))
            bv, pv = top(lp, r["spans"][1], range(N_LETTERS, N_LETTERS + N_VOWELS))
            ok = min(r["gop_letter"], r["gop_vowel"]) > PASS_AT
            w.writerow({
                "item": r["item"], "student": r["clip"], "asked": item["text"],
                "bot_heard": d["out"]["muaalem"], "bot_score": d["bot"]["score"],
                "bot_verdict": d["bot"]["verdict"], "bot_errors": " ".join(d["bot"]["errors"]),
                "list84_best": d["cls"]["best"], "list84_p_asked": d["cls"]["p"],
                "list84_decision": d["cls"]["decision"],
                "sound_letter_heard": names[bl] if bl >= 0 else "", "sound_letter_conf": round(pl, 3),
                "sound_letter_gop": r["gop_letter"],
                "sound_vowel_heard": names[bv] if bv >= 0 else "", "sound_vowel_conf": round(pv, 3),
                "sound_vowel_gop": r["gop_vowel"], "sound_decision": "accept" if ok else "error",
                "maroof_heard": d["out"]["maroof"], "espeak_heard": d["out"]["espeak"],
                "tarteel_heard": d["out"]["tarteel"], "whisper_heard": d["out"]["whisper"],
                "models_disagreeing_with_asked": sum(1 for k in ("muaalem", "maroof", "espeak", "tarteel") if not d["ok"][k]),
                "variants_rival": var.get((r["item"], r["clip"]), {}).get("rival", ""),
                "variants_margin": var.get((r["item"], r["clip"]), {}).get("margin", ""),
                "variants_decision": ("accept" if var[(r["item"], r["clip"])]["margin"] >= 0 else "error") if (r["item"], r["clip"]) in var else "",
                "teacher_heard": "", "teacher_verdict": "",
            })  # fmt: skip
    sys.stdout.write(f"{len(data['rows'])} rows → {args.out}\n")


if __name__ == "__main__":
    main()
