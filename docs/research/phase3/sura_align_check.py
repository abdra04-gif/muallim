# ruff: noqa: E501, PLR0915
"""Part 7 of FR-70 before code: a whole sura in one recording, ayahs found by alignment, each ayah checked.

Material: EveryAyah ayah files of short suras (sura_ayahs_check.py), joined per sura and reciter
into one recording, as if the learner read the sura at once. MostafaMaroof hears the whole recording;
CTC Viterbi alignment of the joined correct readings (Hafs, with a stop at each ayah) finds where each
ayah starts; each ayah is then checked by the bot's `decide` on its own stretch of frames. Measured:
(1) the answers (the recordings are correct — every «error» is a false alarm); (2) how far the found
ayah starts are from the true ones (the file joins), in ms; (3) time of the model, the alignment and
the decisions.

Usage (from the project root, with the bot's phonetiser and transformers installed):
    python docs/research/phase3/sura_align_check.py EVERYAYAH_DIR OUT_JSON
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from letters_test import decode  # noqa: E402

from muallim.domain.card_check import decide  # noqa: E402
from muallim.domain.policy import CardPolicy  # noqa: E402
from muallim.infrastructure.asr.chunks import quiet_cuts  # noqa: E402
from muallim.infrastructure.asr.ctc import ctc_logprob, prepare  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402
from muallim.infrastructure.asr.phonetizer import _references  # noqa: E402

MAROOF = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
SR = 16000


def viterbi_starts(lp: np.ndarray, target: list[int], blank: int, starts: list[int]) -> list[int]:
    """CTC Viterbi: frame where each token of ``target`` is first emitted; returns frames of ``starts``."""
    ext = np.full(2 * len(target) + 1, blank)
    ext[1::2] = target
    n, t_len = len(ext), lp.shape[0]
    skip = np.zeros(n, dtype=bool)
    skip[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])
    delta = np.full(n, -np.inf)
    delta[0], delta[1] = lp[0, ext[0]], lp[0, ext[1]]
    back = np.zeros((t_len, n), dtype=np.int32)
    idx = np.arange(n)
    for f in range(1, t_len):
        stay = delta
        one = np.concatenate(([-np.inf], delta[:-1]))
        two = np.where(skip, np.concatenate(([-np.inf, -np.inf], delta[:-2])), -np.inf)
        cand = np.stack([stay, one, two])
        best = cand.argmax(0)
        back[f] = idx - best
        delta = cand[best, idx] + lp[f, ext]
    s = n - 1 if delta[-1] >= delta[-2] else n - 2
    first = {}
    for f in range(t_len - 1, -1, -1):
        if s % 2 == 1:
            first[s // 2] = f
        s = back[f, s] if f > 0 else s
    return [first.get(k, 0) for k in starts]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument(
        "--before", type=int, default=5, help="frames before the ayah's first sound"
    )
    parser.add_argument(
        "--cut", type=int, default=0, help="frames dropped before the next ayah's first sound"
    )
    args = parser.parse_args()
    import torch  # noqa: PLC0415
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from quran_transcript import Aya  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    mv = json.loads(Path(hf_hub_download(MAROOF, "vocab.json")).read_text(encoding="utf-8"))
    model = Wav2Vec2ForCTC.from_pretrained(MAROOF).eval()
    blank = mv["[PAD]"]
    policy = CardPolicy()
    rules = policy.rules_for(100)
    rows, outcomes, offsets, timing = [], Counter(), [], []
    for reciter_dir in sorted(p for p in args.audio.iterdir() if p.is_dir()):
        suras = sorted({p.stem[:3] for p in reciter_dir.glob("*.mp3")})
        for sura in suras:
            files = sorted(reciter_dir.glob(f"{sura}*.mp3"))
            waves = [decode(f) for f in files]
            true_starts = np.cumsum([0] + [len(w) for w in waves[:-1]]) / SR
            wave = np.concatenate(waves)
            t0 = time.perf_counter()
            # the bot's sura flow: cut at quiet places (6–10 s pieces), the model on each, logits joined
            pieces = quiet_cuts(wave, SR) if args.chunks else [(0, len(wave))]
            parts = []
            for s, e in pieces:
                w = wave[s:e]
                norm = (w - w.mean()) / (w.std() + 1e-7)
                with torch.no_grad():
                    parts.append(
                        torch.log_softmax(
                            model(torch.from_numpy(norm).unsqueeze(0)).logits[0], -1
                        ).numpy()
                    )
            lp = prepare(np.concatenate(parts), mv, long_is_short=False)
            t_model = time.perf_counter() - t0
            frame_s = len(wave) / SR / lp.shape[0]
            texts = [Aya(int(sura), int(f.stem[3:])).get().uthmani for f in files]
            refs = [dict(_references(t)[1]) for t in texts]
            tokens, starts = [], []
            for r in refs:
                starts.append(len(tokens))
                tokens.extend(to_maroof(r["waqf"]))
            t1 = time.perf_counter()
            found = viterbi_starts(lp, [mv[t] for t in tokens], blank, starts)
            t_align = time.perf_counter() - t1
            t2 = time.perf_counter()
            bounds = [*found, lp.shape[0]]
            for k, (f, r) in enumerate(zip(files, refs, strict=True)):
                # the ayah's stretch: a little silence before its first sound, up to the next ayah's
                # first sound (a margin after it would add the next ayah's first consonant)
                a, b = max(0, bounds[k] - args.before), max(bounds[k] + 1, bounds[k + 1] - args.cut)
                seg = lp[a:b]
                cache: dict[str, float] = {}

                def score(v: str, seg: np.ndarray = seg, cache: dict[str, float] = cache) -> float:
                    if v not in cache:
                        try:
                            toks = to_maroof(v)
                        except ValueError:
                            cache[v] = -np.inf
                        else:
                            cache[v] = ctc_logprob(seg, [mv[t] for t in toks], blank)
                    return cache[v]

                d = decide(
                    (r["wasl"], r["waqf"]), score, policy, separate_syllables=False, rules=rules
                )
                outcomes[str(d.outcome)] += 1
                off = abs(bounds[k] * frame_s - true_starts[k]) * 1000
                offsets.append(off)
                rows.append(
                    {
                        "reciter": reciter_dir.name,
                        "where": f"{int(sura)}:{int(f.stem[3:])}",
                        "outcome": str(d.outcome),
                        "kind": str(d.kind),
                        "margin": d.margin,
                        "start_offset_ms": round(off),
                    }
                )
            t_decide = time.perf_counter() - t2
            timing.append(
                {
                    "reciter": reciter_dir.name,
                    "sura": int(sura),
                    "audio_s": round(len(wave) / SR, 1),
                    "model_s": round(t_model, 2),
                    "align_s": round(t_align, 2),
                    "decide_s": round(t_decide, 2),
                }
            )
            sys.stdout.write(f"{reciter_dir.name} {int(sura)}: {timing[-1]}\n")
            sys.stdout.flush()
    o = np.array(offsets)
    summary = {
        "ayahs": len(rows),
        "outcomes": dict(outcomes),
        "start_offset_ms": {
            "median": round(float(np.median(o))),
            "p90": round(float(np.percentile(o, 90))),
            "max": round(float(o.max())),
        },
        "timing": timing,
    }
    text = json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1, default=str)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(
        json.dumps({k: v for k, v in summary.items() if k != "timing"}, ensure_ascii=False) + "\n"
    )


if __name__ == "__main__":
    main()
