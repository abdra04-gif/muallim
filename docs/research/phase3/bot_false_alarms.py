# ruff: noqa: E501, PLC0206
"""Does the bot's own check scold correct whole ayahs? (FR-70, ADR-0088, lessons 42+ and suras)

The 200 cached correct ayahs of §11.8e, checked by the bot's code as it will run: accepted readings
from the bot's phonetiser (Hafs, with and without a stop; optionally also word by word with a stop —
the reading MostafaMaroof was trained on), error variants built from them by `domain.card_check.decide`
with the rules of lessons 42+, thresholds of `CardPolicy`. The recordings are correct, so every
«error» is a false alarm and every «again» a needless repeat.

Usage (from the project root, with the bot's phonetiser installed):
    python docs/research/phase3/bot_false_alarms.py WAV_DIR LOGPROBS.npz OUT_JSON [--limit N]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from word_by_word import word_by_word  # noqa: E402

from muallim.domain.card_check import decide  # noqa: E402
from muallim.domain.policy import CardPolicy  # noqa: E402
from muallim.infrastructure.asr.ctc import ctc_logprob, prepare  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402
from muallim.infrastructure.asr.phonetizer import _references  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    mv = json.loads(
        Path(hf_hub_download("MostafaMaroof/wav2vec2-arabic-phoneme-asr", "vocab.json")).read_text(
            encoding="utf-8"
        )
    )
    lps = np.load(args.cache)
    blank = mv["[PAD]"]
    policy = CardPolicy()
    rules = policy.rules_for(70)
    results: dict[str, Counter[str]] = {"book": Counter(), "book_or_word_by_word": Counter()}
    kinds: dict[str, Counter[str]] = {"book": Counter(), "book_or_word_by_word": Counter()}
    done = 0
    for line in (args.wavs / "refs_ayah.tsv").read_text(encoding="utf-8").splitlines():
        pid, _phon, _t, uthmani, _w = line.split("\t")
        if pid not in lps.files or done >= args.limit:
            continue
        lp = prepare(lps[pid], mv, long_is_short=False)
        refs = dict(_references(uthmani)[1])
        extra = word_by_word(uthmani)
        cache: dict[str, float] = {}

        def score(variant: str, lp: np.ndarray = lp, cache: dict[str, float] = cache) -> float:
            if variant not in cache:
                try:
                    toks = to_maroof(variant)
                except ValueError:
                    cache[variant] = -np.inf
                else:
                    cache[variant] = ctc_logprob(lp, [mv[t] for t in toks], blank)
            return cache[variant]

        done += 1
        for name in results:
            if name == "book":
                s = score
            else:
                wbw = ctc_logprob(lp, [mv[t] for t in extra], blank)

                def s(
                    variant: str,
                    base: float = wbw,
                    ref: str = refs["wasl"],
                    ref2: str = refs["waqf"],
                ) -> float:
                    v = score(variant)
                    return float(np.logaddexp(v, base)) if variant in (ref, ref2) else v

            d = decide(
                (refs["wasl"], refs["waqf"]), s, policy, separate_syllables=False, rules=rules
            )
            results[name][str(d.outcome)] += 1
            if str(d.outcome) != "passed":
                kinds[name][str(d.kind)] += 1
        sys.stdout.write(f"{done}\n")
        sys.stdout.flush()
    out = {
        name: {
            "ayahs": done,
            **{k: round(100 * v / done, 1) for k, v in c.items()},
            "by_kind": dict(kinds[name]),
        }
        for name, c in results.items()
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
