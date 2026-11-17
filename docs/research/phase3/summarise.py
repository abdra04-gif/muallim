"""Phase 3: turn ``results/letters_*.csv`` into Markdown tables (stdout).

Usage: python summarise.py RESULTS_DIR > summary.md
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ["muaalem", "maroof", "espeak", "tarteel", "whisper"]
EMPHATIC = {"ص", "ض", "ط", "ظ"}
NAMES = {"َ": "a", "ِ": "i", "ُ": "u", "": "none"}


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "—"


def scored(row: dict[str, str]) -> bool:
    """The universal phone model has no symbols for the four emphatic letters."""
    return not (row["system"] == "espeak" and row["expected_letter"] in EMPHATIC)


def load(folder: Path) -> dict[str, list[dict[str, str]]]:
    rows: dict[str, list[dict[str, str]]] = {}
    for path in sorted(folder.glob("letters_*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            data = list(csv.DictReader(f))
        if data:  # a run that has only just started has no rows yet
            rows[data[0]["system"]] = data
    return rows


def main() -> None:
    rows = load(Path(sys.argv[1]))
    systems = [s for s in ORDER if s in rows]
    out = sys.stdout.write

    out("### Overall\n\n")
    out("| System | Model | Clips | Letter right | Vowel right | Both right | No letter found |")
    out(" Seconds per clip | Speed (compute ÷ audio) |\n|---|---|---|---|---|---|---|---|---|\n")
    for s in systems:
        data = rows[s]
        use = [r for r in data if scored(r)]
        letter = sum(r["got_letter"] == r["expected_letter"] for r in use)
        vowel = sum(r["got_vowel"] == r["expected_vowel"] for r in data)
        both = sum(
            r["got_letter"] == r["expected_letter"] and r["got_vowel"] == r["expected_vowel"]
            for r in use
        )
        empty = sum(not r["got_letter"] for r in data)
        compute = sum(float(r["compute_s"]) for r in data)
        audio = sum(float(r["audio_s"]) for r in data)
        out(
            f"| {s} | `{data[0]['model']}` | {len(data)} | {pct(letter, len(use))} |"
            f" {pct(vowel, len(data))} | {pct(both, len(use))} | {pct(empty, len(data))} |"
            f" {compute / len(data):.2f} | {compute / audio:.2f} |\n"
        )

    out("\n### Letter right, by letter (30 clips each)\n\n| Letter | " + " | ".join(systems))
    out(" |\n|---|" + "---|" * len(systems) + "\n")
    letters = list(dict.fromkeys(r["expected_letter"] for r in rows[systems[0]]))
    for letter in letters:
        cells = []
        for s in systems:
            use = [r for r in rows[s] if r["expected_letter"] == letter and scored(r)]
            cells.append(pct(sum(r["got_letter"] == letter for r in use), len(use)))
        out(f"| {letter} | " + " | ".join(cells) + " |\n")

    out("\n### Vowel right, by vowel (280 clips each)\n\n| Vowel | " + " | ".join(systems))
    out(" |\n|---|" + "---|" * len(systems) + "\n")
    for vowel, name in list(NAMES.items())[:3]:
        cells = []
        for s in systems:
            use = [r for r in rows[s] if r["expected_vowel"] == vowel]
            cells.append(pct(sum(r["got_vowel"] == vowel for r in use), len(use)))
        out(f"| {name} | " + " | ".join(cells) + " |\n")

    out("\n### Most frequent wrong letters (expected → heard, count)\n\n")
    for s in systems:
        wrong: Counter[tuple[str, str]] = Counter()
        for r in rows[s]:
            if scored(r) and r["got_letter"] != r["expected_letter"]:
                wrong[(r["expected_letter"], r["got_letter"] or "∅")] += 1
        top = ", ".join(f"{a}→{b} ×{n}" for (a, b), n in wrong.most_common(12))
        out(f"- **{s}:** {top}\n")

    out("\n### What the universal phone model writes for the emphatic letters\n\n")
    seen: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows.get("espeak", []):
        if r["expected_letter"] in EMPHATIC:
            seen[r["expected_letter"]][r["output"].split(" ")[0] if r["output"] else "∅"] += 1
    for letter, counts in seen.items():
        out(f"- {letter}: " + ", ".join(f"`{k}` ×{n}" for k, n in counts.most_common(6)) + "\n")


if __name__ == "__main__":
    main()
