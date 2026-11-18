# ruff: noqa: E501, S311
"""Phase 3, step 5: the card-variants check on whole phrases (stage II of the book: words and lines).

Material: correct readings with their phoneme transcription (IqraEval Iqra_train dev, CC BY-NC 4.0,
same Halabi-style symbols as the MostafaMaroof model). For every phrase the rules of
`error_rules.py` create error variants (another vowel, a vowel on a sukun, no shadda, short madd,
an added length, a look-alike letter). The model scores the recording under the correct reading and
under each error variant (CTC forward probability). Since the recording is correct, the correct
reading should win:

    pair accuracy per rule   share of (correct, error) pairs where the correct reading wins
    false alarm per phrase   share of phrases where at least one error variant beats the correct one
                              (the bot would scold a correct learner)

Usage (from the project root):
    python docs/research/phase3/words_check.py WAV_DIR OUT_JSON
WAV_DIR holds <id>.wav and refs.tsv (id, phonemes, vowelled text).
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from error_rules import RULES, variants
from letters_test import decode

MODEL = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
PER_RULE = 2


def ctc_logprob(lp: np.ndarray, target: list[int], blank: int) -> float:
    """log P(target | audio) under CTC, forward algorithm vectorised over states."""
    ext = np.full(2 * len(target) + 1, blank)
    ext[1::2] = target
    n = len(ext)
    skip = np.zeros(n, dtype=bool)
    skip[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])
    alpha = np.full(n, -np.inf)
    alpha[0], alpha[1] = lp[0, ext[0]], lp[0, ext[1]]
    for f in range(1, lp.shape[0]):
        a1 = np.concatenate(([-np.inf], alpha[:-1]))
        a2 = np.concatenate(([-np.inf, -np.inf], alpha[:-2]))
        a2 = np.where(skip, a2, -np.inf)
        alpha = np.logaddexp(np.logaddexp(alpha, a1), a2) + lp[f, ext]
    return float(np.logaddexp(alpha[-1], alpha[-2]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    vocab = json.loads(Path(hf_hub_download(MODEL, "vocab.json")).read_text(encoding="utf-8"))
    blank = vocab["[PAD]"]
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    rng = random.Random(0)

    pairs: dict[str, list[float]] = {r: [] for r in RULES}
    phrases, examples = [], []
    for line in (args.wavs / "refs.tsv").read_text(encoding="utf-8").splitlines():
        pid, phon, text = line.split("\t")
        tokens = phon.split()
        if any(t not in vocab for t in tokens):
            continue
        wave = decode(args.wavs / f"{pid}.wav")
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)
        with torch.no_grad():
            lp = torch.log_softmax(model(torch.from_numpy(norm).unsqueeze(0)).logits[0], -1).numpy()
        # word boundary "|" and "sil" are pauses, not sounds: fold them into the blank (as align_check.py)
        lp[:, blank] = np.logaddexp.reduce(lp[:, [blank, vocab["|"], vocab["sil"]]], axis=1)
        correct = ctc_logprob(lp, [vocab[t] for t in tokens], blank)
        worst = None
        for rule, cands in variants(tokens).items():
            for pos, err in rng.sample(cands, min(PER_RULE, len(cands))):
                if any(t not in vocab for t in err):
                    continue
                margin = correct - ctc_logprob(lp, [vocab[t] for t in err], blank)
                pairs[rule].append(margin)
                if worst is None or margin < worst[0]:
                    worst = (margin, rule, pos, " ".join(err))
        phrases.append(worst[0] if worst else 99.0)
        if worst and len(examples) < 40:
            examples.append(
                {
                    "id": pid,
                    "text": text,
                    "correct": phon,
                    "rival_rule": worst[1],
                    "rival_pos": worst[2],
                    "rival": worst[3],
                    "margin": round(worst[0], 2),
                }
            )
        sys.stdout.write(f"{len(phrases)}\r")
        sys.stdout.flush()

    m = np.array(phrases)
    summary = {
        "phrases": len(phrases),
        "pair_accuracy": {
            r: {
                "pairs": len(v),
                "correct_wins": round(100 * float((np.array(v) > 0).mean()), 1) if v else None,
            }
            for r, v in pairs.items()
        },
        "false_alarm_phrases": {
            str(t): round(100 * float((m <= t).mean()), 1) for t in (0.0, -2.0, -4.0)
        },
    }
    args.out.write_text(
        json.dumps({"summary": summary, "examples": examples}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    sys.stdout.write("\n" + json.dumps(summary, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
