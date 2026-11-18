"""Phase 3, step 5: one JSON with everything the presentation demo shows, per recording.

For each of the 840 recordings of step 1: what the student was asked to read, what each of the
five systems wrote, what the bot would tell the student today (its own ``assess`` and grading
policy run on the bot model's output), and what the trained classifier decided (probability of
the expected item, out-of-speaker). No names, no audio.

Usage:
    python demo_data.py DATA_DIR RESULTS_DIR PROBS_NPY OUT_JSON
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from letters_test import ALIF_TEXT, HAMZA, LETTERS, VOWELS, pick

SYSTEMS = ["muaalem", "maroof", "espeak", "tarteel", "whisper"]
LETTER_LIST = list(LETTERS.values())
VOWEL_LIST = list(VOWELS.values())
ACCEPT, UNSURE = 0.3, 0.1


def main() -> None:
    from muallim.domain.assessment import assess_variants  # noqa: PLC0415
    from muallim.domain.policy import GradingPolicy  # noqa: PLC0415

    # The bot's own reference builder: the same two accepted readings (joined and with a stop).
    from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    data_dir, results, probs_path, out = (Path(a) for a in sys.argv[1:5])
    probs = np.load(probs_path).astype(np.float32)
    policy = GradingPolicy()
    rows: dict[str, dict[str, dict[str, str]]] = {}
    for system in SYSTEMS:
        with (results / f"letters_{system}.csv").open(encoding="utf-8-sig", newline="") as f:
            rows[system] = {r["clip"]: r for r in csv.DictReader(f)}

    items, offset = [], 0
    for folder in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        number, name = folder.name.split(". ", 1)
        letter_name, vowel_name = name.rsplit("_", 1)
        letter, vowel = LETTERS[letter_name], VOWELS[vowel_name]
        text = ALIF_TEXT[vowel] if letter == HAMZA else letter + vowel
        _, references = _references(text)
        reference = " / ".join(ref for _, ref in references)
        every = sorted(folder.glob("*.wav"))
        expected_class = LETTER_LIST.index(letter) * len(VOWEL_LIST) + VOWEL_LIST.index(vowel)
        clips = []
        for index, path in enumerate(pick(folder, 10)):
            clip = f"{number}-{index:02d}"
            p = probs[offset + every.index(path)]
            p_expected = float(p[expected_class])
            best = int(p.argmax())
            best_text = LETTER_LIST[best // 3] + VOWEL_LIST[best % 3]
            heard = rows["muaalem"][clip]["output"]
            judged = assess_variants(references, heard)[0].assessment
            verdict = policy.verdict(judged)
            clips.append({
                "clip": index + 1,
                "out": {s: rows[s][clip]["output"].strip() for s in SYSTEMS},
                "ok": {
                    s: rows[s][clip]["got_letter"] == letter and rows[s][clip]["got_vowel"] == vowel
                    for s in SYSTEMS
                },
                "bot": {
                    "score": judged.score,
                    "verdict": str(verdict),
                    "errors": [e.kind.value for e in judged.errors],
                },
                "cls": {
                    "p": round(p_expected, 3),
                    "best": "ا" + best_text[1] if best_text[0] == HAMZA else best_text,
                    "decision": "accept" if p_expected >= ACCEPT
                    else "again" if p_expected >= UNSURE else "error",
                },
            })  # fmt: skip
        items.append({"name": name, "text": text, "reference": reference, "clips": clips})
        offset += len(every)
    out.write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sys.stdout.write(f"{len(items)} items, {offset} clips indexed\n")


if __name__ == "__main__":
    main()
