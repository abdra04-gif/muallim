"""Phase 3, step 3: build the candidate checkers and compare them on speakers they never heard.

Input: the feature files written by ``features.py``. Four ways to decide which letter and vowel
a clip holds are compared on the same clips:

  free         read the model's ordinary transcription (what Phase 3 step 1 measured)
  constrained  let the same model choose only among the 28 letters and 3 vowels
  template     compare the clip with the average of other speakers' clips of each class
  classifier   a small trained layer on top of the model's inner representation

``template`` and ``classifier`` are trained on four fifths of the speakers and tested on the
remaining fifth, five times, so every clip is judged by a model that never heard its speaker.

Usage:
    python candidates.py FEATURE_DIR OUT_DIR
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from letters_test import (
    LETTERS,
    MAROOF_LETTERS,
    MAROOF_VOWELS,
    VOWELS,
    halve,
    parse_maroof,
)

FOLDS = 5
LETTER_LIST = list(LETTERS.values())
VOWEL_LIST = list(VOWELS.values())
# Pairs a beginner confuses; (expected, impostor) in both directions.
PAIRS = [("د", "ت"), ("ص", "س"), ("ض", "د"), ("ط", "ت"), ("ظ", "ز"), ("ث", "س"), ("ح", "ه"),
         ("ع", "ء"), ("ق", "ك"), ("ذ", "ز")]  # fmt: skip
THRESHOLDS = [0.0, 0.5, 0.7, 0.9]
ACCEPT_AT = [0.1, 0.3, 0.5]


def load(folder: Path) -> dict[str, np.ndarray]:
    parts: dict[str, list[np.ndarray]] = {k: [] for k in ("emb", "ctc", "greedy", "speaker")}
    letter, vowel = [], []
    for path in sorted(folder.glob("[0-9][0-9].npz")):
        data = np.load(path)
        letter_name, vowel_name = str(data["name"]).rsplit("_", 1)
        count = len(data["greedy"])
        letter += [LETTER_LIST.index(LETTERS[letter_name])] * count
        vowel += [VOWEL_LIST.index(VOWELS[vowel_name])] * count
        for key, values in parts.items():
            values.append(data[key])
    out = {key: np.concatenate(values) for key, values in parts.items()}
    out["emb"] = out["emb"].astype(np.float32).reshape(len(letter), -1)
    out["letter"], out["vowel"] = np.asarray(letter), np.asarray(vowel)
    out["cls"] = out["letter"] * len(VOWEL_LIST) + out["vowel"]
    speakers = sorted(set(out["speaker"].tolist()))
    out["fold"] = np.asarray([speakers.index(s) % FOLDS for s in out["speaker"].tolist()])
    out["speakers"] = np.asarray(len(speakers))
    return out


def free(data: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    letters, vowels = [], []
    for text in data["greedy"].tolist():
        letter, vowel = parse_maroof(text)
        letters.append(LETTER_LIST.index(letter) if letter in LETTER_LIST else -1)
        vowels.append(VOWEL_LIST.index(vowel) if vowel in VOWEL_LIST else -1)
    return np.asarray(letters), np.asarray(vowels)


def constrained(
    data: dict[str, np.ndarray], vocab: dict[str, int]
) -> tuple[np.ndarray, np.ndarray]:
    """Best score of any symbol of each letter (and vowel) anywhere in the clip."""

    def scores(table: dict[str, str], targets: list[str]) -> np.ndarray:
        columns = []
        for target in targets:
            ids = [i for symbol, i in vocab.items() if table.get(halve(symbol)) == target]
            columns.append(data["ctc"][:, ids].max(axis=1))
        return np.stack(columns, axis=1)

    letter_scores = scores(MAROOF_LETTERS, LETTER_LIST)
    vowel_scores = scores(MAROOF_VOWELS, VOWEL_LIST)
    return letter_scores.argmax(axis=1), vowel_scores.argmax(axis=1)


def standardise(
    train: np.ndarray, test: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean, std = train.mean(axis=0), train.std(axis=0) + 1e-6
    return (train - mean) / std, (test - mean) / std, mean, std


def template(
    train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray, classes: int
) -> np.ndarray:
    centres = np.stack([train_x[train_y == c].mean(axis=0) for c in range(classes)])
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    test = test_x / np.linalg.norm(test_x, axis=1, keepdims=True)
    return (test @ centres.T).argmax(axis=1)


def fit(
    train_x: np.ndarray, train_y: np.ndarray, classes: int
) -> tuple[torch.Tensor, torch.Tensor]:
    """Plain softmax regression with weight decay; nothing else is tuned."""
    x, y = torch.from_numpy(train_x), torch.from_numpy(train_y)
    weight = torch.zeros(x.shape[1], classes, requires_grad=True)
    bias = torch.zeros(classes, requires_grad=True)
    optimiser = torch.optim.LBFGS([weight, bias], max_iter=200, line_search_fn="strong_wolfe")

    def closure() -> torch.Tensor:
        optimiser.zero_grad()
        loss = torch.nn.functional.cross_entropy(x @ weight + bias, y) + 1e-3 * (weight**2).sum()
        loss.backward()
        return loss

    optimiser.step(closure)
    return weight.detach(), bias.detach()


def cross_validate(data: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Out-of-speaker class probabilities of the classifier and class picks of the template."""
    classes = len(LETTER_LIST) * len(VOWEL_LIST)
    probs = np.zeros((len(data["cls"]), classes), dtype=np.float32)
    picks = np.zeros(len(data["cls"]), dtype=np.int64)
    for fold in range(FOLDS):
        test = data["fold"] == fold
        train_x, test_x, _, _ = standardise(data["emb"][~test], data["emb"][test])
        weight, bias = fit(train_x, data["cls"][~test], classes)
        logits = torch.from_numpy(test_x) @ weight + bias
        probs[test] = torch.softmax(logits, dim=1).numpy()
        picks[test] = template(train_x, data["cls"][~test], test_x, classes)
        sys.stdout.write(f"fold {fold + 1}/{FOLDS}\n")
        sys.stdout.flush()
    return probs, picks


def score(letter: np.ndarray, vowel: np.ndarray, data: dict[str, np.ndarray]) -> dict[str, float]:
    right_letter, right_vowel = letter == data["letter"], vowel == data["vowel"]
    return {
        "letter": round(100 * float(right_letter.mean()), 1),
        "vowel": round(100 * float(right_vowel.mean()), 1),
        "both": round(100 * float((right_letter & right_vowel).mean()), 1),
    }


def by_letter(letter: np.ndarray, data: dict[str, np.ndarray]) -> dict[str, float]:
    return {
        name: round(100 * float((letter[data["letter"] == i] == i).mean()), 1)
        for i, name in enumerate(LETTER_LIST)
    }


def not_sure(probs: np.ndarray, data: dict[str, np.ndarray]) -> list[dict[str, float]]:
    """Answer only when the classifier is confident enough; otherwise say "not sure"."""
    top, pick = probs.max(axis=1), probs.argmax(axis=1)
    rows = []
    for threshold in THRESHOLDS:
        answered = top >= threshold
        rows.append({
            "threshold": threshold,
            "answered": round(100 * float(answered.mean()), 1),
            "right_when_answered": round(100 * float((pick == data["cls"])[answered].mean()), 1),
        })  # fmt: skip
    return rows


def impostors(data: dict[str, np.ndarray]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Wrong "expected" classes to test against: (clip index, claimed class) per kind."""
    index = np.arange(len(data["cls"]))
    vowels = len(VOWEL_LIST)
    other_vowel = [
        (index, data["letter"] * vowels + (data["vowel"] + shift) % vowels) for shift in (1, 2)
    ]
    pair_index, pair_claim = [], []
    for a, b in PAIRS + [(b, a) for a, b in PAIRS]:
        said = data["letter"] == LETTER_LIST.index(a)
        pair_index.append(index[said])
        pair_claim.append(LETTER_LIST.index(b) * vowels + data["vowel"][said])
    rng = np.random.default_rng(0)
    shift = rng.integers(1, len(LETTER_LIST), size=len(index))
    random_claim = ((data["letter"] + shift) % len(LETTER_LIST)) * vowels + data["vowel"]
    return {
        "other_vowel": (
            np.concatenate([i for i, _ in other_vowel]),
            np.concatenate([c for _, c in other_vowel]),
        ),
        "confusable_letter": (np.concatenate(pair_index), np.concatenate(pair_claim)),
        "random_letter": (index, random_claim),
    }


def verification(
    data: dict[str, np.ndarray], probs: np.ndarray, free_cls: np.ndarray
) -> dict[str, dict[str, float]]:
    """The bot's real question: the expected item is known — was it read? Accept or reject."""
    index = np.arange(len(data["cls"]))
    trials = {"genuine": (index, data["cls"]), **impostors(data)}
    out: dict[str, dict[str, float]] = {"free transcription": {}}
    for threshold in ACCEPT_AT:
        out[f"classifier, accept at {threshold}"] = {}
    for kind, (clip, claim) in trials.items():
        out["free transcription"][kind] = round(100 * float((free_cls[clip] == claim).mean()), 1)
        for threshold in ACCEPT_AT:
            accepted = probs[clip, claim] >= threshold
            out[f"classifier, accept at {threshold}"][kind] = round(100 * float(accepted.mean()), 1)
    return out


def pair_check(data: dict[str, np.ndarray], probs: np.ndarray) -> list[dict[str, object]]:
    """Per confusable pair, at threshold 0.3: genuine readings of A accepted as A, and readings
    of B wrongly accepted as A. If students asked for A often say B, the two cannot be told
    apart and the second figure is high."""
    vowels = len(VOWEL_LIST)
    rows = []
    for a, b in PAIRS + [(b, a) for a, b in PAIRS]:
        ia, ib = LETTER_LIST.index(a), LETTER_LIST.index(b)
        said_a, said_b = data["letter"] == ia, data["letter"] == ib
        genuine = probs[said_a, ia * vowels + data["vowel"][said_a]] >= ACCEPT_AT[1]
        impostor = probs[said_b, ia * vowels + data["vowel"][said_b]] >= ACCEPT_AT[1]
        rows.append({
            "expected": a, "said_instead": b,
            "correct_accepted": round(100 * float(genuine.mean()), 1),
            "substitute_accepted": round(100 * float(impostor.mean()), 1),
        })  # fmt: skip
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    data = load(args.features)
    vocab = json.loads((args.features / "vocab.json").read_text(encoding="utf-8"))
    vowels = len(VOWEL_LIST)

    free_letter, free_vowel = free(data)
    con_letter, con_vowel = constrained(data, vocab)
    probs, picks = cross_validate(data)
    # Out-of-speaker probabilities for every clip, in feature-file order (for the demo).
    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "classifier_probs.npy", probs.astype(np.float16))
    cls_pick = probs.argmax(axis=1)
    free_cls = np.where(
        (free_letter >= 0) & (free_vowel >= 0), free_letter * vowels + free_vowel, -1
    )
    agree = (con_letter == cls_pick // vowels) & (con_vowel == cls_pick % vowels)

    result = {
        "clips": len(data["cls"]),
        "speakers": int(data["speakers"]),
        "folds": FOLDS,
        "methods": {
            "free transcription": score(free_letter, free_vowel, data),
            "constrained choice": score(con_letter, con_vowel, data),
            "template comparison": score(picks // vowels, picks % vowels, data),
            "trained classifier": score(cls_pick // vowels, cls_pick % vowels, data),
        },
        "letters": {
            "free transcription": by_letter(free_letter, data),
            "constrained choice": by_letter(con_letter, data),
            "trained classifier": by_letter(cls_pick // vowels, data),
        },
        "not_sure": not_sure(probs, data),
        "two_signals": {
            "agree": round(100 * float(agree.mean()), 1),
            "right_when_agree": round(100 * float((cls_pick == data["cls"])[agree].mean()), 1),
        },
        "verification": verification(data, probs, free_cls),
        "pairs": pair_check(data, probs),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "candidates.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # The classifier trained on every clip, for checking new recordings later.
    train_x, _, mean, std = standardise(data["emb"], data["emb"][:1])
    weight, bias = fit(train_x, data["cls"], len(LETTER_LIST) * vowels)
    np.savez_compressed(
        args.out / "letter_classifier.npz",
        weight=weight.numpy().astype(np.float16),
        bias=bias.numpy().astype(np.float32),
        mean=mean.astype(np.float32),
        std=std.astype(np.float32),
    )
    sys.stdout.write(json.dumps(result["methods"], ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
