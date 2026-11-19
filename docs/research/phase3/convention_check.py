# ruff: noqa: E501
"""Which differences between our transcription and the dataset one does MostafaMaroof accept?

For each of the 200 cached ayahs: align the dataset transcription with ours (to_maroof.py), and for
every differing place make the dataset transcription with only that place changed to ours. The model
scores both; margin = ours − dataset. A difference the model accepts (margin near 0 or above) is only
notation or a reading the model can hear; one it rejects (well below 0) is a convention it was trained on.

Usage (from the project root):
    python docs/research/phase3/convention_check.py WAV_DIR LOGPROBS.npz OUT_JSON
"""

import argparse
import difflib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from to_maroof import plain, prepare, references
from words_check import ctc_logprob


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    mv = json.loads(
        Path(hf_hub_download("MostafaMaroof/wav2vec2-arabic-phoneme-asr", "vocab.json")).read_text(
            encoding="utf-8"
        )
    )
    lps = np.load(args.cache)
    blank = mv["[PAD]"]
    by_kind: dict[str, list[float]] = defaultdict(list)
    for line in (args.wavs / "refs_ayah.tsv").read_text(encoding="utf-8").splitlines():
        pid, phon, _t, uthmani, _w = line.split("\t")
        if pid not in lps.files:
            continue
        gold = plain(phon.split())
        ours = references(uthmani)["waqf"]
        if any(t not in mv for t in ours + gold):
            continue
        lp = prepare(lps[pid], mv)
        base = ctc_logprob(lp, [mv[t] for t in gold], blank)
        sm = difflib.SequenceMatcher(None, gold, ours, autojunk=False)
        for op, a1, a2, b1, b2 in sm.get_opcodes():
            if op == "equal":
                continue
            kind = f"{' '.join(gold[a1:a2]) or '∅'} → {' '.join(ours[b1:b2]) or '∅'}"
            alt = gold[:a1] + ours[b1:b2] + gold[a2:]
            by_kind[kind].append(ctc_logprob(lp, [mv[t] for t in alt], blank) - base)

    rows = sorted(by_kind.items(), key=lambda kv: -len(kv[1]))
    out = [
        {
            "difference": k,
            "count": len(v),
            "median_margin": round(float(np.median(v)), 2),
            "model_rejects_pct": round(100 * float((np.array(v) < -2).mean()), 1),
        }
        for k, v in rows
        if len(v) >= 3
    ]
    allv = np.concatenate([np.array(v) for v in by_kind.values()])
    summary = {
        "places": len(allv),
        "accepted_pct": round(100 * float((allv >= -2).mean()), 1),
        "by_difference": out[:40],
    }
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
