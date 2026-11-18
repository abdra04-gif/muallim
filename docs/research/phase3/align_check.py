# ruff: noqa: E501, PLR0917
"""Phase 3, step 3 prototype: check each expected sound (forced alignment + GOP).

The bot knows what should be read. Instead of asking the model "what was said?", we
1. turn the expected syllable into the model's sound symbols (letter, vowel);
2. let CTC forced alignment find, frame by frame, where each expected sound is in the audio;
3. for each expected sound, compare its probability on its own frames with the best competing
   sound of the same kind (another letter / another vowel): this is the GOP score;
4. accept the syllable when every sound beats its competitors.

No training. Same 840 recordings as step 1 (10 per syllable). Also scores "swap" trials: the
same audio checked against a look-alike letter or another vowel, to see how often errors slip.

Usage (from the project root):
    python docs/research/phase3/align_check.py DATA_DIR OUT_DIR
Writes OUT_DIR/align.json (summary) and OUT_DIR/align_clips.npz (per-clip frames for pictures).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from letters_test import LETTERS, MAROOF_LETTERS, VOWELS, decode, pick

MODEL = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
PER_CLASS = 10
# Confusable pairs, both directions (same list as candidates.py).
PAIRS = [("د", "ت"), ("ص", "س"), ("ض", "د"), ("ط", "ت"), ("ظ", "ز"), ("ث", "س"), ("ح", "ه"),
         ("ع", "ء"), ("ق", "ك"), ("ذ", "ز")]  # fmt: skip
VOWEL_SYMBOLS = {"َ": ("a", "A", "aa", "AA"), "ِ": ("i", "I", "ii", "II"), "ُ": ("u", "U", "uu", "UU")}
BLANKS = ("[PAD]", "sil", "|")
THRESHOLDS = [-1.0, 0.0, 1.0]


def classes(vocab: dict[str, int]) -> tuple[list[str], list[list[int]], int, int]:
    """Merge the model's symbols into units: 28 letters (plain + doubled), 3 vowels, blank."""
    letter_syms: dict[str, list[str]] = {}
    for sym, letter in MAROOF_LETTERS.items():
        letter_syms.setdefault(letter, []).append(sym)
        if sym + sym in vocab:
            letter_syms[letter].append(sym + sym)
    names = list(letter_syms) + list(VOWEL_SYMBOLS) + ["∅"]
    groups = [[vocab[s] for s in letter_syms[n] if s in vocab] for n in letter_syms]
    groups += [[vocab[s] for s in VOWEL_SYMBOLS[v] if s in vocab] for v in VOWEL_SYMBOLS]
    groups.append([vocab[s] for s in BLANKS if s in vocab])
    return names, groups, len(letter_syms), len(VOWEL_SYMBOLS)


def merge(logp: np.ndarray, groups: list[list[int]]) -> np.ndarray:
    """Frame log-probabilities of every unit = log of the summed probability of its symbols."""
    return np.stack([np.logaddexp.reduce(logp[:, g], axis=1) for g in groups], axis=1)


def align(lp: np.ndarray, target: list[int], blank: int) -> list[tuple[int, int]]:
    """CTC Viterbi forced alignment: (start, end) frames of each target unit."""
    ext = [blank]
    for t in target:
        ext += [t, blank]
    frames, states = lp.shape[0], len(ext)
    score = np.full((frames, states), -np.inf)
    back = np.zeros((frames, states), dtype=int)
    score[0, 0] = lp[0, ext[0]]
    score[0, 1] = lp[0, ext[1]]
    for f in range(1, frames):
        for s in range(states):
            options = [(score[f - 1, s], s)]
            if s >= 1:
                options.append((score[f - 1, s - 1], s - 1))
            if s >= 2 and ext[s] != blank and ext[s] != ext[s - 2]:
                options.append((score[f - 1, s - 2], s - 2))
            best, prev = max(options)
            score[f, s] = best + lp[f, ext[s]]
            back[f, s] = prev
    s = states - 1 if score[-1, states - 1] >= score[-1, states - 2] else states - 2
    path = [s]
    for f in range(frames - 1, 0, -1):
        s = back[f, s]
        path.append(s)
    path.reverse()
    spans = []
    for k in range(len(target)):
        own = [f for f, st in enumerate(path) if st == 2 * k + 1]
        spans.append((own[0], own[-1] + 1) if own else (0, 0))
    return spans


def gop(lp: np.ndarray, span: tuple[int, int], unit: int, rivals: range) -> float:
    """Mean over the unit's frames of log P(expected) − max log P(competitor of the same kind)."""
    a, b = span
    if b <= a:
        return -9.0
    seg = lp[a:b]
    others = [r for r in rivals if r != unit]
    return float(np.mean(seg[:, unit] - seg[:, others].max(axis=1)))


def check(lp: np.ndarray, letter: int, vowel: int, n_letters: int, n_vowels: int, blank: int):
    spans = align(lp, [letter, vowel], blank)
    g_letter = gop(lp, spans[0], letter, range(n_letters))
    g_vowel = gop(lp, spans[1], vowel, range(n_letters, n_letters + n_vowels))
    return spans, g_letter, g_vowel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    vocab = json.loads(Path(hf_hub_download(MODEL, "vocab.json")).read_text(encoding="utf-8"))
    names, groups, n_letters, n_vowels = classes(vocab)
    blank = len(names) - 1
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    vowel_list = list(VOWEL_SYMBOLS)

    rows, keep = [], {}
    for folder in sorted(p for p in args.data.iterdir() if p.is_dir()):
        letter_name, vowel_name = folder.name.split(". ", 1)[1].rsplit("_", 1)
        letter = names.index(LETTERS[letter_name])
        vowel = n_letters + vowel_list.index(VOWELS[vowel_name])
        for i, path in enumerate(pick(folder, PER_CLASS)):
            wave = decode(path)
            norm = (wave - wave.mean()) / (wave.std() + 1e-7)
            with torch.no_grad():
                logits = model(torch.from_numpy(norm).unsqueeze(0)).logits[0]
            lp = merge(torch.log_softmax(logits, -1).numpy(), groups)
            spans, gl, gv = check(lp, letter, vowel, n_letters, n_vowels, blank)
            row = {"item": folder.name.split(". ", 1)[1], "clip": i + 1, "file": str(path),
                   "letter": names[letter], "vowel": names[vowel], "spans": spans,
                   "gop_letter": round(gl, 3), "gop_vowel": round(gv, 3)}  # fmt: skip
            # Swap trials: the same audio checked as if a look-alike letter or another vowel was asked.
            subs = [b for a, b in PAIRS if a == names[letter]] + [
                a for a, b in PAIRS if b == names[letter]
            ]
            row["swap_letter"] = [
                round(min(check(lp, names.index(s), vowel, n_letters, n_vowels, blank)[1:]), 3)
                for s in subs
                if s in names
            ]
            row["swap_vowel"] = [
                round(min(check(lp, letter, n_letters + j, n_letters, n_vowels, blank)[1:]), 3)
                for j in range(n_vowels)
                if n_letters + j != vowel
            ]
            rows.append(row)
            keep[f"{row['item']}-{row['clip']}"] = lp.astype(np.float16)
        sys.stdout.write(f"{folder.name}\n")
        sys.stdout.flush()

    genuine = np.array([min(r["gop_letter"], r["gop_vowel"]) for r in rows])
    swap_l = np.array([v for r in rows for v in r["swap_letter"]])
    swap_v = np.array([v for r in rows for v in r["swap_vowel"]])
    summary = {"clips": len(rows), "swap_letter_trials": len(swap_l), "swap_vowel_trials": len(swap_v),
               "names": names, "thresholds": {}}  # fmt: skip
    for t in THRESHOLDS:
        summary["thresholds"][str(t)] = {
            "correct_passed": round(100 * float((genuine > t).mean()), 1),
            "lookalike_passed": round(100 * float((swap_l > t).mean()), 1),
            "other_vowel_passed": round(100 * float((swap_v > t).mean()), 1),
        }
    (args.out / "align.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    np.savez_compressed(args.out / "align_clips.npz", **keep)
    sys.stdout.write(json.dumps(summary["thresholds"], ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
