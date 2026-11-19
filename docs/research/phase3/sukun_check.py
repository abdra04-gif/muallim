# ruff: noqa: E501
"""Sukun on whole ayahs with MostafaMaroof: does the correct reading beat the typical sukun errors?

MostafaMaroof has no sukun symbol: a letter with sukun is simply a consonant with no vowel after it
(قَدْ = q a d). So every check of sukun is "the correct reading against a variant with an error":
    vowel a / i / u  — a vowel added after the sukun letter (قَدْ → قَدَ / قَدِ / قَدُ), every vowel, not only fatha;
    drop             — the sukun letter is not read at all (نَسْتَعِينُ → نَتَعِينُ).
Split by where the sukun is (inside the phrase / the last letter, i.e. the stop) and by whether the
letter is a qalqala letter (ق ط ب ج د — a light echo is correct there and could sound like a vowel).
All positions of every ayah, no sampling. The recordings are correct, so the correct reading should win.

Usage (from the project root):
    python docs/research/phase3/sukun_check.py WAV_DIR OUT_JSON [--cache LOGPROBS.npz] [--limit N]
WAV_DIR holds <id>.wav and refs_ayah.tsv (as for compare_models.py).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from error_rules import VOWELS
from letters_test import decode
from words_check import ctc_logprob

MAROOF = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
QALQALA = {"q", "T", "b", "j", "d"}


def sukun_positions(tokens: list[str]) -> list[tuple[int, str]]:
    """Single consonants with no vowel after them: ("inner" | "final")."""
    out = []
    for i, t in enumerate(tokens):
        if t in VOWELS or len(t) != 1:
            continue
        if i + 1 == len(tokens):
            out.append((i, "final"))
        elif tokens[i + 1] not in VOWELS:
            out.append((i, "inner"))
    return out


def logprobs(wavs: Path, ids: list[str], cache: Path | None) -> dict[str, np.ndarray]:
    if cache and cache.exists():
        data = np.load(cache)
        return {k: data[k] for k in data.files}
    import torch  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    model = Wav2Vec2ForCTC.from_pretrained(MAROOF).eval()
    out = {}
    for n, pid in enumerate(ids, 1):
        wave = decode(wavs / f"{pid}.wav")
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)
        with torch.no_grad():
            logits = model(torch.from_numpy(norm).unsqueeze(0)).logits[0]
        out[pid] = torch.log_softmax(logits, -1).numpy().astype(np.float16)
        sys.stdout.write(f"{n}/{len(ids)}\n")
        sys.stdout.flush()
    if cache:
        np.savez_compressed(cache, **out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    mv = json.loads(Path(hf_hub_download(MAROOF, "vocab.json")).read_text(encoding="utf-8"))
    lines = (args.wavs / "refs_ayah.tsv").read_text(encoding="utf-8").splitlines()[: args.limit]
    rows = [line.split("\t") for line in lines]
    rows = [r for r in rows if all(t in mv for t in r[1].split())]
    lps = logprobs(args.wavs, [r[0] for r in rows], args.cache)
    blank = mv["[PAD]"]

    margins: dict[str, list[float]] = {}
    for pid, phon, *_ in rows:
        tokens = phon.split()
        lp = lps[pid].astype(np.float32)
        lp[:, blank] = np.logaddexp.reduce(lp[:, [blank, mv["|"], mv["sil"]]], axis=1)
        good = ctc_logprob(lp, [mv[t] for t in tokens], blank)
        for i, where in sukun_positions(tokens):
            kind = "qalqala" if tokens[i] in QALQALA else "other"
            emph = tokens[i] in {"S", "D", "T", "Z", "q"}
            for v in ("a", "i", "u"):
                vv = v.upper() if emph else v
                err = [*tokens[: i + 1], vv, *tokens[i + 1 :]]
                d = good - ctc_logprob(lp, [mv[t] for t in err], blank)
                margins.setdefault(f"vowel_{v}|{where}|{kind}", []).append(d)
            if where == "inner":
                err = tokens[:i] + tokens[i + 1 :]
                d = good - ctc_logprob(lp, [mv[t] for t in err], blank)
                margins.setdefault(f"drop|{where}|{kind}", []).append(d)

    def stats(v: list[float]) -> dict[str, float]:
        a = np.array(v)
        return {
            "pairs": len(a),
            "correct_wins": round(100 * float((a > 0).mean()), 1),
            "error_ahead_by_4": round(100 * float((a < -4).mean()), 1),
        }

    summary = {"ayahs": len(rows), "by_case": {k: stats(v) for k, v in sorted(margins.items())}}
    for rule in ("vowel_a", "vowel_i", "vowel_u", "drop"):
        allv = [d for k, v in margins.items() if k.startswith(rule + "|") for d in v]
        summary[rule] = stats(allv)
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
