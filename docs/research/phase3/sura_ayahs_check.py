# ruff: noqa: E501, PLR0915
"""The bot's card check on suras read with full tajwid (FR-70, ADR-0088, lessons 97–125).

Material: whole ayahs of short suras (1, 103, 108, 110–114) from EveryAyah (the source the bot
already uses for reference recordings, SRC-145): Mishary al-Afasy (fast, with tajwid) and Mahmoud
Khalil al-Husary «Muallim» (slow teaching recitation). Every recording is correct, so every «error»
is a false alarm and every «again» a needless repeat. Each ayah is checked by the bot's code
(`domain.card_check.decide`, rules of lessons 42+, `CardPolicy` thresholds) with the accepted
readings: the book's (Hafs, with and without a stop) — and, as an option, also word by word with a
stop (the reading MostafaMaroof was trained on, `word_by_word.py`).

Usage (from the project root, with the bot's phonetiser and transformers installed):
    python docs/research/phase3/sura_ayahs_check.py EVERYAYAH_DIR OUT_JSON
EVERYAYAH_DIR holds <reciter>/<sss><aaa>.mp3.
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

from letters_test import decode  # noqa: E402
from word_by_word import word_by_word  # noqa: E402

from muallim.domain.card_check import decide  # noqa: E402
from muallim.domain.policy import CardPolicy  # noqa: E402
from muallim.infrastructure.asr.ctc import ctc_logprob, prepare  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402
from muallim.infrastructure.asr.phonetizer import _references  # noqa: E402

MAROOF = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    import torch  # noqa: PLC0415
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from quran_transcript import Aya  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    mv = json.loads(Path(hf_hub_download(MAROOF, "vocab.json")).read_text(encoding="utf-8"))
    inv = {i: t for t, i in mv.items()}
    model = Wav2Vec2ForCTC.from_pretrained(MAROOF).eval()
    blank = mv["[PAD]"]
    policy = CardPolicy()
    rules = policy.rules_for(100)
    summary: dict[str, dict[str, Counter[str]]] = {}
    rows = []
    for reciter_dir in sorted(p for p in args.audio.iterdir() if p.is_dir()):
        reciter = reciter_dir.name
        summary[reciter] = {"book": Counter(), "book_or_word_by_word": Counter()}
        for mp3 in sorted(reciter_dir.glob("*.mp3")):
            sura, aya = int(mp3.stem[:3]), int(mp3.stem[3:])
            text = Aya(sura, aya).get().uthmani
            wave = decode(mp3)
            norm = (wave - wave.mean()) / (wave.std() + 1e-7)
            with torch.no_grad():
                logits = model(torch.from_numpy(norm).unsqueeze(0)).logits[0]
            raw = torch.log_softmax(logits, -1).numpy()
            greedy, prev = [], None
            for i in raw.argmax(-1).tolist():
                if i != prev and inv[i] not in ("[PAD]", "|", "sil"):
                    greedy.append(inv[i])
                prev = i
            lp = prepare(raw, mv, long_is_short=False)
            refs = dict(_references(text)[1])
            words = word_by_word(text)
            wbw = ctc_logprob(lp, [mv[t] for t in words], blank)
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

            def with_words(
                v: str, base: float = wbw, accepted: tuple[str, ...] = (refs["wasl"], refs["waqf"])
            ) -> float:
                s = score(v)
                return float(np.logaddexp(s, base)) if v in accepted else s

            row = {
                "reciter": reciter,
                "where": f"{sura}:{aya}",
                "text": text,
                "greedy": " ".join(greedy),
            }
            for name, fn in (("book", score), ("book_or_word_by_word", with_words)):
                d = decide(
                    (refs["wasl"], refs["waqf"]), fn, policy, separate_syllables=False, rules=rules
                )
                summary[reciter][name][str(d.outcome)] += 1
                row[name] = {
                    "outcome": str(d.outcome),
                    "kind": str(d.kind),
                    "margin": d.margin,
                    "margin_other": d.margin_other,
                }
            rows.append(row)
            sys.stdout.write(
                f"{reciter} {sura}:{aya} {row['book']['outcome']} / {row['book_or_word_by_word']['outcome']}\n"
            )
            sys.stdout.flush()
    out = {
        "summary": {r: {k: dict(v) for k, v in s.items()} for r, s in summary.items()},
        "rows": rows,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(out["summary"], ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
