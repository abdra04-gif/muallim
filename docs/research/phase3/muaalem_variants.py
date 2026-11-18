# ruff: noqa: PERF401
"""Card variants on the bot's own model Muaalem (ADR-0086, point 7): is one model enough?

Same 840 recordings and the same variants as variants_check.py (correct reading; the other two
vowels; no vowel; look-alike letters), written in Muaalem's phonetic script. A held vowel is
allowed for every variant (short, +1 or +2 madd signs), so holding the sound is never an error.
Score of a variant = CTC forward probability under Muaalem's phoneme head.

Usage (from the project root):
    python docs/research/phase3/muaalem_variants.py DATA_DIR OUT_JSON
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from align_check import PAIRS
from letters_test import LETTERS, VOWELS, decode, pick
from words_check import ctc_logprob

PER_CLASS = 10
HOLD = {"َ": "ا", "ِ": "ۦ", "ُ": "ۥ"}
MARGINS = [0.0, 2.0, 4.0]


def forms(letter: str, vowel: str | None) -> list[str]:
    if vowel is None:
        return [letter]
    h = HOLD[vowel]
    return [letter + vowel, letter + vowel + h, letter + vowel + h + h]


def family(lp: np.ndarray, seqs: list[str], vocab: dict[str, int]) -> float:
    return float(np.logaddexp.reduce([ctc_logprob(lp, [vocab[c] for c in s], 0) for s in seqs]))


def decide(lp: np.ndarray, letter: str, vowel: str, vocab: dict[str, int]) -> float:
    correct = family(lp, forms(letter, vowel), vocab)
    errors = [family(lp, forms(letter, v), vocab) for v in HOLD if v != vowel]
    errors.append(family(lp, forms(letter, None), vocab))
    for a, b in PAIRS:
        other = b if a == letter else a if b == letter else None
        if other:
            errors.append(family(lp, forms(other, vowel), vocab))
    return correct - max(errors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    from quran_muaalem import Muaalem  # noqa: PLC0415

    m = Muaalem(device="cpu", dtype=torch.float32)
    vocab = {c: i for i, c in m.multi_level_tokenizer.id_to_vocab["phonemes"].items()}

    genuine, swap_l, swap_v, rows = [], [], [], []
    for folder in sorted(p for p in args.data.iterdir() if p.is_dir()):
        letter_name, vowel_name = folder.name.split(". ", 1)[1].rsplit("_", 1)
        letter, vowel = LETTERS[letter_name], VOWELS[vowel_name]
        for i, path in enumerate(pick(folder, PER_CLASS)):
            wave = decode(path)
            feats = m.processor([wave], sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                outs = m.model(
                    **{k: v.to(torch.float32) for k, v in feats.items()}, return_dict=False
                )[0]
            lp = torch.log_softmax(outs["phonemes"][0], -1).numpy()
            g = decide(lp, letter, vowel, vocab)
            genuine.append(g)
            rows.append(
                {"item": folder.name.split(". ", 1)[1], "clip": i + 1, "margin": round(g, 3)}
            )
            for a, b in PAIRS:
                other = b if a == letter else a if b == letter else None
                if other:
                    swap_l.append(decide(lp, other, vowel, vocab))
            for v in HOLD:
                if v != vowel:
                    swap_v.append(decide(lp, letter, v, vocab))
        sys.stdout.write(f"{folder.name}\n")
        sys.stdout.flush()

    g, sl, sv = np.array(genuine), np.array(swap_l), np.array(swap_v)
    summary = {
        "model": "Muaalem",
        "clips": len(g),
        "swap_letter_trials": len(sl),
        "swap_vowel_trials": len(sv),
        "margins": {},
    }
    for t in MARGINS:
        summary["margins"][str(t)] = {
            "correct_passed": round(100 * float((g >= t).mean()), 1),
            "lookalike_passed": round(100 * float((sl >= t).mean()), 1),
            "other_vowel_passed": round(100 * float((sv >= t).mean()), 1),
        }
    args.out.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
