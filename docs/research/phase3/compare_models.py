# ruff: noqa: E501, S311, PLR0915, PLC0206, S112, RUF059
"""MostafaMaroof against Muaalem on whole ayahs of the Quran (card variants, ADR-0086 point 7).

Material: phrases of IqraEval Iqra_train dev (CC BY-NC 4.0) that are exactly one whole ayah, read
correctly by reciters. Each model gets its reference the way it would in the bot:
    MostafaMaroof — the Halabi phoneme transcription of the dataset;
    Muaalem      — the bot's own phonetiser on the Uthmani text (`_references`, reading with a stop).
The same kinds of errors are made on each reference (another vowel, a vowel on a sukun, no shadda,
short madd, added length, a look-alike letter), two positions per rule and ayah; the recording is
correct, so the correct reading should win.

Usage (from the project root):
    python docs/research/phase3/compare_models.py WAV_DIR OUT_JSON [--limit N]
WAV_DIR holds <id>.wav and refs_ayah.tsv (id, halabi, imlaey, uthmani, sura:aya).
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "src"))
from error_rules import RULES, variants  # noqa: E402
from letters_test import decode  # noqa: E402
from words_check import ctc_logprob  # noqa: E402

MAROOF = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
PER_RULE = 2
U_SHORT = "َِ" + "ُ"
U_MADD = {"َ": "ا", "ِ": "ۦ", "ُ": "ۥ"}
U_LOOK = {"د": "تض", "ت": "دط", "ص": "س", "س": "صث", "ض": "د", "ط": "ت", "ظ": "زذ", "ز": "ظذ", "ث": "س",
          "ح": "ه", "ه": "ح", "ع": "ء", "ء": "ع", "ق": "ك", "ك": "ق", "ذ": "زظ"}  # fmt: skip
U_LETTERS = set("ءبتثجحخدذرزسشصضطظعغفقكلمنهوي")


def muaalem_variants(s: str) -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {r: [] for r in RULES}
    for i, c in enumerate(s):
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if c in U_SHORT:
            for o in U_SHORT:
                if o != c:
                    out["vowel"].append((i, s[:i] + o + s[i + 1 :]))
            if nxt != U_MADD[c]:
                out["added_length"].append((i, s[: i + 1] + U_MADD[c] * 2 + s[i + 1 :]))
            else:
                j = i + 1
                while j < len(s) and s[j] == U_MADD[c]:
                    j += 1
                out["short_madd"].append((i, s[: i + 1] + s[j:]))
        if c in U_LETTERS:
            if nxt == c:
                out["no_shadda"].append((i, s[:i] + s[i + 1 :]))
            elif nxt in U_LETTERS:
                out["vowel_on_sukun"].append((i, s[: i + 1] + "َ" + s[i + 1 :]))
            for o in U_LOOK.get(c, ""):
                out["lookalike"].append((i, s[:i] + o + s[i + 1 :]))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from quran_muaalem import Muaalem  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    mv = json.loads(Path(hf_hub_download(MAROOF, "vocab.json")).read_text(encoding="utf-8"))
    maroof = Wav2Vec2ForCTC.from_pretrained(MAROOF).eval()
    mua = Muaalem(device="cpu", dtype=torch.float32)
    uv = {c: i for i, c in mua.multi_level_tokenizer.id_to_vocab["phonemes"].items()}
    rng_m, rng_u = random.Random(0), random.Random(0)

    pairs = {name: {r: [] for r in RULES} for name in ("maroof", "muaalem")}
    worst = {"maroof": [], "muaalem": []}
    details = []
    lines = (args.wavs / "refs_ayah.tsv").read_text(encoding="utf-8").splitlines()[: args.limit]
    for n, line in enumerate(lines, 1):
        pid, phon, text, uthmani, where = line.split("\t")
        tokens = phon.split()
        try:
            ref_u = dict(_references(uthmani)[1])["waqf"]
        except Exception:  # noqa: BLE001 — the phonetiser fails on a few texts; skip them
            continue
        if any(t not in mv for t in tokens) or any(c not in uv for c in ref_u):
            continue
        wave = decode(args.wavs / f"{pid}.wav")
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)
        with torch.no_grad():
            lp_m = torch.log_softmax(
                maroof(torch.from_numpy(norm).unsqueeze(0)).logits[0], -1
            ).numpy()
            feats = mua.processor([wave], sampling_rate=16000, return_tensors="pt")
            outs = mua.model(
                **{k: v.to(torch.float32) for k, v in feats.items()}, return_dict=False
            )[0]
            lp_u = torch.log_softmax(outs["phonemes"][0], -1).numpy()
        blank_m = mv["[PAD]"]
        lp_m[:, blank_m] = np.logaddexp.reduce(lp_m[:, [blank_m, mv["|"], mv["sil"]]], axis=1)
        good_m = ctc_logprob(lp_m, [mv[t] for t in tokens], blank_m)
        good_u = ctc_logprob(lp_u, [uv[c] for c in ref_u], 0)
        low = {"maroof": (99.0, ""), "muaalem": (99.0, "")}
        for rule, cands in variants(tokens).items():
            for _pos, err in rng_m.sample(cands, min(PER_RULE, len(cands))):
                if any(t not in mv for t in err):
                    continue
                d = good_m - ctc_logprob(lp_m, [mv[t] for t in err], blank_m)
                pairs["maroof"][rule].append(d)
                if d < low["maroof"][0]:
                    low["maroof"] = (d, rule)
        for rule, cands in muaalem_variants(ref_u).items():
            for _pos, err in rng_u.sample(cands, min(PER_RULE, len(cands))):
                if any(c not in uv for c in err):
                    continue
                d = good_u - ctc_logprob(lp_u, [uv[c] for c in err], 0)
                pairs["muaalem"][rule].append(d)
                if d < low["muaalem"][0]:
                    low["muaalem"] = (d, rule)
        worst["maroof"].append(low["maroof"][0])
        worst["muaalem"].append(low["muaalem"][0])
        details.append(
            {
                "id": pid,
                "where": where,
                "text": uthmani,
                "maroof": [round(low["maroof"][0], 2), low["maroof"][1]],
                "muaalem": [round(low["muaalem"][0], 2), low["muaalem"][1]],
            }
        )
        sys.stdout.write(f"{n}/{len(lines)}\n")
        sys.stdout.flush()

    summary = {"ayahs": len(details), "pair_accuracy": {}, "false_alarm_ayahs": {}}
    for name in pairs:
        summary["pair_accuracy"][name] = {
            r: {
                "pairs": len(v),
                "correct_wins": round(100 * float((np.array(v) > 0).mean()), 1) if v else None,
            }
            for r, v in pairs[name].items()
        }
        w = np.array(worst[name])
        summary["false_alarm_ayahs"][name] = {
            str(t): round(100 * float((w <= t).mean()), 1) for t in (0.0, -2.0, -4.0)
        }
    args.out.write_text(
        json.dumps({"summary": summary, "ayahs": details}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
