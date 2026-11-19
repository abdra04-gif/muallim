# ruff: noqa: E501, PERF401, RUF005, S311, E741, PLR0912
"""The whole chain on a teacher's voice: card text → to_maroof → card variants → the learner's answer.

Material: the bot's library recordings of three syllables in a row (رَ رِ رُ, …) by Muhammad Farouk
ar-Rai («Nooraniyya», SRC-144; curriculum/audio/library), 28 letters — the content of lessons 3–30.
Each recording is checked against cards (thresholds of ADR-0087 point 4):
    own card                 — should be «passed»;
    last vowel wrong         — the card's last vowel replaced by each other vowel, as if the learner read
                               the last syllable wrong — should be «error»;
    middle vowel wrong       — the same for the middle syllable — should be «error»;
    look-alike / unrelated   — a card of a look-alike / another letter — should be «error».
Rivals of the correct reading: per syllable another vowel, no vowel, a look-alike letter, and «another
syllable» (any other, not look-alike, letter). The last syllable has its own rule (--last):
    strict  — like every other syllable;
    soft    — a stop on it (no vowel) is a reading; another vowel is an «error» only when it wins by more
              than LAST_ERROR, otherwise «passed» with a hint to say the last vowel clearly.

Usage (from the project root):
    python docs/research/phase3/library_check.py OUT_JSON [--last strict|soft] [--last-error -4]
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
from error_rules import LOOKALIKE  # noqa: E402
from letters_test import decode  # noqa: E402
from to_maroof import LETTER, prepare, references  # noqa: E402
from words_check import ctc_logprob  # noqa: E402

MAROOF = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
PASS, ERROR, AGAIN_OTHER, WRONG_OTHER = 0.0, -4.0, -3.0, -6.0
CONSONANTS = sorted(set(LETTER.values()))
VOWELS = ("a", "i", "u")


def near(a: str, b: str) -> bool:
    return b in LOOKALIKE.get(a, ()) or a in LOOKALIKE.get(b, ())


def answer(
    lp: np.ndarray, tokens: list[str], mv: dict[str, int], last: str, last_error: float
) -> dict:
    blank = mv["[PAD]"]

    def score(seq: list[str]) -> float:
        return ctc_logprob(lp, [mv[t] for t in seq], blank)

    good = score(tokens)
    body, tail, other = [], [], []
    for k in range(0, len(tokens), 2):  # consonant, vowel, consonant, vowel …
        c, v = tokens[k], tokens[k + 1]
        is_last = k + 2 >= len(tokens) and len(tokens) > 2 and last in ("soft", "clear")
        group = tail if is_last else body
        for o in VOWELS:
            if o != v:
                group.append(("vowel", tokens[: k + 1] + [o] + tokens[k + 2 :]))
        if not is_last:
            body.append(("no vowel", tokens[: k + 1] + tokens[k + 2 :]))
        for o in LOOKALIKE.get(c, ()):
            body.append((f"letter {o}", tokens[:k] + [o] + tokens[k + 1 :]))
        for o in CONSONANTS:
            if o != c and not near(c, o):
                for w in VOWELS:
                    other.append(tokens[:k] + [o, w] + tokens[k + 2 :])
    lab, best = max(((lab, score(s)) for lab, s in body), key=lambda x: x[1])
    m = good - best
    mo = good - max(score(s) for s in other)
    if mo < WRONG_OTHER:
        ans = "error"
    elif mo < AGAIN_OTHER:
        ans = "again" if m >= ERROR else "error"
    else:
        ans = "passed" if m >= PASS else "again" if m >= ERROR else "error"
    hint = False
    if tail and last == "clear" and ans != "error":
        # the vowel heard must be the right one; a vowel hardly heard is not an error — «say it again»
        mv_ = good - max(score(s) for _, s in tail)
        ms = good - score(tokens[:-1])
        if mv_ < ERROR:
            ans = "error"
        elif mv_ < PASS:
            ans = "again"
        elif ms < PASS:
            ans, hint = "again", True
    elif tail and ans != "error":
        # a stop on the last syllable is a reading: the correct reading may end without the vowel
        good_tail = float(np.logaddexp(good, score(tokens[:-1])))
        mt = good_tail - max(score(s) for _, s in tail)
        if mt < last_error:
            ans = "error"
        elif mt < 0:
            hint = True
    return {
        "answer": ans,
        "hint_last_vowel": hint,
        "margin": round(m, 2),
        "rival": lab,
        "margin_other": round(mo, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--last", choices=("strict", "soft", "clear"), default="clear")
    parser.add_argument("--last-error", type=float, default=-4.0)
    args = parser.parse_args()
    import torch  # noqa: PLC0415
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    mv = json.loads(Path(hf_hub_download(MAROOF, "vocab.json")).read_text(encoding="utf-8"))
    model = Wav2Vec2ForCTC.from_pretrained(MAROOF).eval()
    lib = ROOT / "curriculum" / "audio" / "library"
    entries = yaml.safe_load((lib / "sounds.yaml").read_text(encoding="utf-8"))
    triples = [
        e
        for e in entries
        if len(e["text"].split()) == 3 and all(len(w) == 2 for w in e["text"].split())
    ]
    cards = {e["text"]: references(e["text"])["wasl"] for e in triples}
    by_letter = {toks[0]: text for text, toks in cards.items()}
    rng = random.Random(0)

    kinds = ("own", "last_vowel_wrong", "middle_vowel_wrong", "lookalike", "unrelated")
    trials: dict[str, list[dict]] = {k: [] for k in kinds}
    for e in triples:
        wave = decode(lib / e["file"])
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)
        with torch.no_grad():
            logits = model(torch.from_numpy(norm).unsqueeze(0)).logits[0]
        lp = prepare(torch.log_softmax(logits, -1).numpy(), mv, held_is_short=True)
        own = cards[e["text"]]

        def check(card: list[str], kind: str, lp: np.ndarray = lp, said: str = e["text"]) -> None:
            trials[kind].append(
                {
                    "said": said,
                    "card": " ".join(card),
                    **answer(lp, card, mv, args.last, args.last_error),
                }
            )

        check(own, "own")
        for pos, kind in ((5, "last_vowel_wrong"), (3, "middle_vowel_wrong")):
            for o in VOWELS:
                if o != own[pos]:
                    check(own[:pos] + [o] + own[pos + 1 :], kind)
        c = own[0]
        look = [by_letter[o] for o in LOOKALIKE.get(c, ()) if o in by_letter]
        if look:
            check(cards[look[0]], "lookalike")
        far = [t for l, t in by_letter.items() if l != c and not near(c, l)]
        check(cards[rng.choice(far)], "unrelated")

    def share(rows: list[dict]) -> dict[str, str]:
        got = [r["answer"] for r in rows]
        out = {a: f"{got.count(a)} of {len(got)}" for a in ("passed", "again", "error")}
        out["passed_with_hint"] = str(
            sum(r["answer"] == "passed" and r["hint_last_vowel"] for r in rows)
        )
        return out

    summary = {
        "recordings": len(triples),
        "last": args.last,
        "last_error": args.last_error,
        **{k: share(v) for k, v in trials.items()},
    }
    text = json.dumps({"summary": summary, "trials": trials}, ensure_ascii=False, indent=1)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
