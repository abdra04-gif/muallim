# ruff: noqa: E501, PLR0912, PLR0915
"""Book text → MostafaMaroof sounds (ADR-0087): the bot's own phonetiser, then a symbol table.

Why not the phonetiser MostafaMaroof was trained with (Nawar Halabi's, used by IqraEval): its
transcriptions do not follow the reading the book teaches (Hafs) — رَسُولٍۢ كَرِيمٍۢ is written without
the tanwin, إِن يَثْقَفُوكُمْ without the merge. The bot's phonetiser (quran_transcript, `_references`)
already reads every card of the book by Hafs, with and without a stop; here its symbols are rewritten
in MostafaMaroof's alphabet:
    letter                     → its symbol; the same letter repeated (shadda, merge, ghunna) → doubled symbol (bb)
    vowel + madd signs         → long vowel (aa ii uu), whatever the count — the model has no lengths
    ں / ۾ (hidden nun / mim)   → n / m;  ڇ (qalqala), ۜ (sakt) → nothing
    و / ي held at a stop (لَوْ)  → single
    vowels are written plain (a i u); when scoring, the model's heavy vowel (A I U, after ص ض ط ظ ق
    and خ غ in its training data) is added to the plain one — `prepare` — so no guessing is needed

Checks (from the project root):
    python docs/research/phase3/to_maroof.py WAV_DIR OUT_JSON [--cache LOGPROBS.npz] [--cards OUT_TSV]
    1. agreement with the dataset transcription on whole ayahs (refs_ayah.tsv);
    2. which the model prefers on the 200 cached ayahs: the dataset transcription or ours;
    3. every card of lessons 1–41 converts (and a TSV for a person to look through).
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "src"))
from words_check import ctc_logprob  # noqa: E402

LETTER = {
    "ء": "<", "ب": "b", "ت": "t", "ث": "^", "ج": "j", "ح": "H", "خ": "x", "د": "d", "ذ": "*", "ر": "r",
    "ز": "z", "س": "s", "ش": "$", "ص": "S", "ض": "D", "ط": "T", "ظ": "Z", "ع": "E", "غ": "g", "ف": "f",
    "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
    "ں": "n", "۾": "m", "ٲ": "<",
}  # fmt: skip
VOWEL = {"َ": "a", "ُ": "u", "ِ": "i", "۪": "a", "ؙ": "u"}
MADD = {"ا": "a", "ۥ": "u", "ۦ": "i", "ـ": "a"}
DROP = {"ڇ", "ۜ"}
HIDDEN = {"ں", "۾"}
LESSONS = {f"L{n:03d}" for n in range(1, 42)}
LETTERS_ONLY = re.compile(r"[^ء-غف-يٱ]")  # keep the letters, drop the signs


def to_maroof(phonetic: str) -> list[str]:
    out: list[str] = []
    chars = [c for c in phonetic if c not in DROP]
    i = 0
    while i < len(chars):
        c = chars[i]
        if c in LETTER:
            j = i
            while j < len(chars) and chars[j] == c:
                j += 1
            sym = LETTER[c]
            vowel_next = j < len(chars) and chars[j] in VOWEL
            # a hidden nun / mim (ikhfa) is held long with ghunna, and و / ي after a fatha at a stop
            # (لَوْ, madd lin) is held long — one sound for the model; a doubled letter has a vowel after it
            held = c in HIDDEN or (c in "وي" and not vowel_next)
            out.append(sym * 2 if j - i >= 2 and not held else sym)
            i = j
        elif c in VOWEL:
            v = VOWEL[c]
            j = i + 1
            while j < len(chars) and chars[j] in MADD:
                j += 1
            out.append(v * 2 if j > i + 1 else v)
            i = j
        elif c in MADD:  # a madd sign with no vowel before it — a long vowel
            v = MADD[c]
            j = i
            while j < len(chars) and chars[j] in MADD:
                j += 1
            out.append(v * 2)
            i = j
        else:
            raise ValueError(f"unknown symbol {c!r} in {phonetic!r}")
    return out


def references(text: str) -> dict[str, list[str]]:
    """Both readings the bot accepts. A card of separate syllables (بُ · رَ رِ رُ) is read with every
    vowel: a stop would drop the last one, and «no vowel» is one of the errors we look for."""
    from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    refs = {name: to_maroof(ph) for name, ph in _references(text)[1]}
    if all(len(LETTERS_ONLY.sub("", w)) == 1 for w in text.split()):
        refs["waqf"] = refs["wasl"]
    return refs


def prepare(lp: np.ndarray, vocab: dict[str, int], *, held_is_short: bool = False) -> np.ndarray:
    """Model output for scoring: word gap and silence count as blank; a heavy vowel (A, after ص ض ط ظ ق
    and خ غ in the training data) and a plain one (a) are one sound — the reading is the same vowel."""
    lp = lp.astype(np.float32).copy()
    blank = vocab["[PAD]"]
    lp[:, blank] = np.logaddexp.reduce(lp[:, [blank, vocab["|"], vocab["sil"]]], axis=1)
    for low in ("a", "i", "u", "aa", "ii", "uu"):
        lp[:, vocab[low]] = np.logaddexp(lp[:, vocab[low]], lp[:, vocab[low.upper()]])
    if held_is_short:  # lessons 3–30: a held vowel on a syllable is not an error (ADR-0086 point 4)
        for short in ("a", "i", "u"):
            lp[:, vocab[short]] = np.logaddexp(lp[:, vocab[short]], lp[:, vocab[short * 2]])
            lp[:, vocab[short * 2]] = -np.inf
    return lp


def plain(tokens: list[str]) -> list[str]:
    """A dataset transcription with heavy vowels written as plain ones (matches `prepare`)."""
    return [t.lower() if t in {"A", "I", "U", "AA", "II", "UU"} else t for t in tokens]


def edit_distance(a: list[str], b: list[str]) -> int:
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (x != y))
    return d[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--cards", type=Path)
    args = parser.parse_args()
    import difflib  # noqa: PLC0415
    from collections import Counter  # noqa: PLC0415

    import yaml  # noqa: PLC0415
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    mv = json.loads(
        Path(hf_hub_download("MostafaMaroof/wav2vec2-arabic-phoneme-asr", "vocab.json")).read_text(
            encoding="utf-8"
        )
    )
    rows = [
        line.split("\t")
        for line in (args.wavs / "refs_ayah.tsv").read_text(encoding="utf-8").splitlines()
    ]

    # 1. agreement with the dataset transcription
    errs = toks = failed = 0
    diffs: Counter[str] = Counter()
    ours: dict[str, list[str]] = {}
    for pid, phon, _text, uthmani, _where in rows:
        try:
            ref = references(uthmani)["waqf"]
        except Exception:  # noqa: BLE001
            failed += 1
            continue
        gold = plain(phon.split())
        ours[pid] = ref
        errs += edit_distance(ref, gold)
        toks += len(gold)
        for op, a1, a2, b1, b2 in difflib.SequenceMatcher(
            None, gold, ref, autojunk=False
        ).get_opcodes():
            if op != "equal":
                diffs[f"{' '.join(gold[a1:a2]) or '∅'} → {' '.join(ref[b1:b2]) or '∅'}"] += 1
    agreement = {
        "ayahs": len(ours),
        "phonetiser_failed": failed,
        "token_difference_pct": round(100 * errs / toks, 2),
        "exact_match_pct": round(
            100 * sum(ours[p] == plain(ph.split()) for p, ph, *_ in rows if p in ours) / len(ours),
            1,
        ),
        "top_differences": diffs.most_common(25),
    }

    # 2. what the model prefers
    preference = {}
    if args.cache and args.cache.exists():
        lps = np.load(args.cache)
        blank = mv["[PAD]"]
        d = []
        for pid, phon, *_ in rows:
            if pid not in lps.files or pid not in ours or any(t not in mv for t in ours[pid]):
                continue
            lp = prepare(lps[pid], mv)
            d.append(
                ctc_logprob(lp, [mv[t] for t in ours[pid]], blank)
                - ctc_logprob(lp, [mv[t] for t in plain(phon.split())], blank)
            )
        a = np.array(d)
        preference = {
            "ayahs": len(a),
            "ours_preferred_pct": round(100 * float((a > 0).mean()), 1),
            "median_ours_minus_dataset": round(float(np.median(a)), 2),
            "ours_behind_by_more_than_4_pct": round(100 * float((a < -4).mean()), 1),
        }

    # 3. every card of lessons 1–41
    course = yaml.safe_load((ROOT / "curriculum" / "course.ru.yaml").read_text(encoding="utf-8"))
    lessons = course["lessons"] if isinstance(course, dict) else course
    cards, bad, unknown = [], [], Counter()
    for lesson in lessons:
        if lesson.get("id") not in LESSONS:
            continue
        for item in lesson.get("items", []):
            text = item.get("text", "")
            # rule cards are text; alphabet cards are «look at the letters and their names» (the book
            # teaches sounds, not names) — the bot does not check them by voice (domain/curriculum.py)
            if item.get("kind") in ("rule", "alphabet") or not text:
                continue
            try:
                refs = references(text)
            except Exception as e:  # noqa: BLE001
                bad.append([item["id"], text, str(e)[:80]])
                continue
            for toks_ in refs.values():
                unknown.update(t for t in toks_ if t not in mv)
            cards.append([item["id"], text, " ".join(refs["wasl"]), " ".join(refs["waqf"])])
    if args.cards:
        args.cards.write_text(
            "id\ttext\twasl\twaqf\n" + "\n".join("\t".join(c) for c in cards) + "\n",
            encoding="utf-8",
        )
    book = {"cards": len(cards), "failed": bad, "symbols_not_in_model": dict(unknown)}

    out = {"agreement": agreement, "model_preference": preference, "book_lessons_1_41": book}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    args.out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
