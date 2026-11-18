"""Phase 3, step 4: run the letter classifier on any recordings, e.g. Telegram voice messages.

Input: a CSV with columns ``file`` (path to an audio file, relative to the CSV) and ``text``
(the vowelled letter that should have been read, e.g. ``بَ``). Output: one row per file with
the expected item, the classifier's best guess, the probability it gives to the expected item,
and the verdict the bot would give at a threshold of 0.3:

    accept      the expected item has probability ≥ 0.3
    not sure    it is between 0.1 and 0.3: ask the learner to say it again
    reject      it is below 0.1

Usage:
    python check_recordings.py CLASSIFIER_NPZ RECORDINGS_CSV OUT_CSV
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from features import MODEL
from letters_test import HAMZA, HAMZA_FORMS, LETTERS, VOWELS, decode

LETTER_LIST = list(LETTERS.values())
VOWEL_LIST = list(VOWELS.values())
ACCEPT, UNSURE = 0.3, 0.1


def class_of(text: str) -> int:
    """``بَ`` → class index; the first letter and the first vowel sign count."""
    letter = next(
        (HAMZA_FORMS.get(ch, ch) for ch in text if HAMZA_FORMS.get(ch, ch) in LETTER_LIST), ""
    )
    vowel = next((ch for ch in text if ch in VOWEL_LIST), "")
    if not letter or not vowel:
        msg = f"not a single vowelled letter: {text!r}"
        raise ValueError(msg)
    return LETTER_LIST.index(letter) * len(VOWEL_LIST) + VOWEL_LIST.index(vowel)


def name_of(index: int) -> str:
    letter = LETTER_LIST[index // len(VOWEL_LIST)]
    return ("ا" if letter == HAMZA else letter) + VOWEL_LIST[index % len(VOWEL_LIST)]


def main() -> None:
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("classifier", type=Path)
    parser.add_argument("recordings", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    saved = np.load(args.classifier)
    weight = torch.from_numpy(saved["weight"].astype(np.float32))
    bias, mean, std = (torch.from_numpy(saved[k]) for k in ("bias", "mean", "std"))
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    depth = model.config.num_hidden_layers
    layers = [depth // 2, 3 * depth // 4, depth]

    with args.recordings.open(encoding="utf-8-sig", newline="") as f:
        items = list(csv.DictReader(f))
    rows, verdicts = [], {"accept": 0, "not sure": 0, "reject": 0}
    top_right = 0
    for item in items:
        expected = class_of(item["text"])
        wave = decode(args.recordings.parent / item["file"])
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)
        with torch.no_grad():
            hidden = model(
                torch.from_numpy(norm).unsqueeze(0), output_hidden_states=True
            ).hidden_states
        emb = torch.cat([hidden[i][0].mean(dim=0) for i in layers])
        probs = torch.softmax(((emb - mean) / std) @ weight + bias, dim=0)
        p_expected, best = float(probs[expected]), int(probs.argmax())
        verdict = (
            "accept" if p_expected >= ACCEPT else "not sure" if p_expected >= UNSURE else "reject"
        )
        verdicts[verdict] += 1
        top_right += best == expected
        rows.append({
            "file": item["file"], "expected": name_of(expected), "best_guess": name_of(best),
            "p_expected": round(p_expected, 3), "p_best": round(float(probs[best]), 3),
            "verdict": verdict,
        })  # fmt: skip
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sys.stdout.write(
        f"{len(rows)} recordings; best guess = expected in {top_right}; verdicts {verdicts}\n"
    )


if __name__ == "__main__":
    main()
