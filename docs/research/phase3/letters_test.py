"""Phase 3, preliminary test: single vowelled letters read by non-Arab learners.

Data: Reinjin/Pelafalan_Huruf_Hijaiyah (Hugging Face), unpacked into one folder per class,
named like ``40. sad_fathah``. Each system hears the same clips; we check whether the first
consonant and the first vowel it reports match the class the learner was asked to read.

Usage:
    python letters_test.py DATA_DIR OUT_CSV SYSTEM [--per-class 10] [--resume]
SYSTEM: muaalem | tarteel | whisper | maroof | espeak
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import torch

RATE = 16000
FATHA, KASRA, DAMMA = "َ", "ِ", "ُ"
VOWELS = {"fathah": FATHA, "kasroh": KASRA, "dommah": DAMMA}
HAMZA = "ء"
LETTERS = {
    "alif": HAMZA, "ba": "ب", "ta": "ت", "tsa": "ث", "jim": "ج", "hah": "ح", "kha": "خ",
    "dal": "د", "dzal": "ذ", "ra": "ر", "zay": "ز", "sin": "س", "shin": "ش", "sad": "ص",
    "dad": "ض", "tah": "ط", "zah": "ظ", "ain": "ع", "ghaiin": "غ", "fa": "ف", "qaf": "ق",
    "kaf": "ك", "lam": "ل", "mim": "م", "nun": "ن", "Ha": "ه", "waw": "و", "ya": "ي",
}  # fmt: skip
HAMZA_FORMS = {"أ": HAMZA, "إ": HAMZA, "ؤ": HAMZA, "ئ": HAMZA, "آ": HAMZA, "ا": HAMZA, "ٱ": HAMZA}
ALIF_TEXT = {FATHA: "أ" + FATHA, KASRA: "إ" + KASRA, DAMMA: "أ" + DAMMA}

# Halabi-style symbols of MostafaMaroof/wav2vec2-arabic-phoneme-asr → Arabic letter / vowel.
MAROOF_LETTERS = {
    "<": HAMZA, "b": "ب", "t": "ت", "^": "ث", "th": "ث", "j": "ج", "H": "ح", "x": "خ",
    "d": "د", "*": "ذ", "r": "ر", "z": "ز", "s": "س", "$": "ش", "sh": "ش", "S": "ص",
    "D": "ض", "T": "ط", "Z": "ظ", "E": "ع", "g": "غ", "f": "ف", "q": "ق", "k": "ك",
    "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "y": "ي",
}  # fmt: skip
MAROOF_VOWELS = {"a": FATHA, "A": FATHA, "i": KASRA, "I": KASRA, "u": DAMMA, "U": DAMMA}

# IPA symbols of facebook/wav2vec2-xlsr-53-espeak-cv-ft → Arabic letter / vowel (lenient).
# The four emphatic letters have no reliable symbol in this inventory and are not scored.
IPA_LETTERS = {
    "ʔ": HAMZA, "b": "ب", "t": "ت", "t̪": "ت", "θ": "ث", "dʒ": "ج", "ʒ": "ج", "ɡ": "ج",
    "ħ": "ح", "x": "خ", "χ": "خ", "d": "د", "ð": "ذ", "r": "ر", "ɾ": "ر", "ɹ": "ر",
    "z": "ز", "s": "س", "ʃ": "ش", "ʕ": "ع", "ɣ": "غ", "ʁ": "غ", "f": "ف", "q": "ق",
    "k": "ك", "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "j": "ي",
}  # fmt: skip
IPA_VOWELS = {
    "a": FATHA, "aː": FATHA, "æ": FATHA, "ɐ": FATHA, "ɑ": FATHA, "ɑː": FATHA, "ä": FATHA,
    "i": KASRA, "iː": KASRA, "ɪ": KASRA, "e": KASRA, "ɛ": KASRA, "eː": KASRA,
    "u": DAMMA, "uː": DAMMA, "ʊ": DAMMA, "o": DAMMA, "ɔ": DAMMA, "oː": DAMMA,
}  # fmt: skip
EMPHATIC = {"ص", "ض", "ط", "ظ"}

Hear = Callable[[np.ndarray, str], str]


def decode(path: Path) -> np.ndarray:
    """Any audio file → 16 kHz mono float32, the same way the bot decodes voice messages."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(RATE),
        "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout  # noqa: S603
    return np.frombuffer(raw, dtype=np.float32).copy()


def pick(folder: Path, count: int) -> list[Path]:
    """First takes only (no ``_1`` suffix), evenly spaced by name → different learners."""
    first = sorted(p for p in folder.glob("*.wav") if not p.stem.endswith("_1"))
    step = max(1, len(first) // count)
    return first[::step][:count]


def first_two(
    symbols: list[str], letters: dict[str, str], vowels: dict[str, str]
) -> tuple[str, str]:
    """First consonant in the output and the first vowel after it; '' when absent."""
    letter = vowel = ""
    for symbol in symbols:
        if not letter:
            letter = letters.get(symbol, "")
        elif symbol in vowels:
            vowel = vowels[symbol]
            break
    return letter, vowel


def parse_arabic(text: str) -> tuple[str, str]:
    chars = [HAMZA_FORMS.get(ch, ch) for ch in text]
    identity = {ch: ch for ch in LETTERS.values()}
    return first_two(chars, identity, {FATHA: FATHA, KASRA: KASRA, DAMMA: DAMMA})


def halve(symbol: str) -> str:
    """Doubled symbols of the Arabic phoneme model ('bb', 'aa') → single."""
    half = len(symbol) // 2
    return symbol[:half] if half and symbol[:half] == symbol[half:] else symbol


def muaalem() -> Hear:
    from quran_muaalem import Muaalem  # noqa: PLC0415
    from quran_transcript import MoshafAttributes, quran_phonetizer  # noqa: PLC0415

    from muallim.infrastructure.asr.muaalem import MOSHAF_PARAMS  # noqa: PLC0415
    from muallim.infrastructure.asr.script import for_phonetizer  # noqa: PLC0415

    device = "mps" if torch.backends.mps.is_available() else "cpu"  # as the bot does
    model = Muaalem(device=device, dtype=torch.float32)
    moshaf = MoshafAttributes(**MOSHAF_PARAMS)

    def hear(wave: np.ndarray, text: str) -> str:
        ref = quran_phonetizer(for_phonetizer(text), moshaf, remove_spaces=True)
        return str(model([wave], [ref], sampling_rate=RATE)[0].phonemes.text)

    return hear


def whisper(model_id: str) -> Hear:
    from transformers import pipeline  # noqa: PLC0415

    # Whisper pads every clip to 30 s, so on the CPU a one-second clip costs seconds.
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    pipe = pipeline("automatic-speech-recognition", model=model_id, device=device)
    # The Quran fine-tune ships an old generation config that rejects `language`;
    # it only knows Arabic, so it needs no hint.
    options: dict[str, Any] = (
        {} if "quran" in model_id else {"language": "arabic", "task": "transcribe"}
    )
    # Only the first letter and vowel are scored; without a cap Whisper sometimes loops
    # on a one-second clip and writes hundreds of tokens (the first full run took hours).
    options["max_new_tokens"] = 12

    def hear(wave: np.ndarray, _text: str) -> str:
        return str(pipe({"raw": wave, "sampling_rate": RATE}, generate_kwargs=options)["text"])

    return hear


def ctc(model_id: str) -> Hear:
    """Greedy CTC decoding from the model's own symbol table; symbols joined by spaces."""
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    vocab = json.loads(Path(hf_hub_download(model_id, "vocab.json")).read_text(encoding="utf-8"))
    names = {index: symbol for symbol, index in vocab.items()}
    skip = {"[PAD]", "<pad>", "<s>", "</s>", "[UNK]", "<unk>", "|", "sil"}
    model = Wav2Vec2ForCTC.from_pretrained(model_id).eval()

    def hear(wave: np.ndarray, _text: str) -> str:
        norm = (wave - wave.mean()) / (wave.std() + 1e-7)
        with torch.no_grad():
            ids = model(torch.from_numpy(norm).unsqueeze(0)).logits[0].argmax(-1).tolist()
        out, last = [], -1
        for index in ids:
            if index != last and names[index] not in skip:
                out.append(names[index])
            last = index
        return " ".join(out)

    return hear


def parse_maroof(text: str) -> tuple[str, str]:
    return first_two([halve(s) for s in text.split()], MAROOF_LETTERS, MAROOF_VOWELS)


def parse_ipa(text: str) -> tuple[str, str]:
    return first_two(text.split(), IPA_LETTERS, IPA_VOWELS)


SYSTEMS: dict[str, tuple[str, Callable[[], Hear], Callable[[str], tuple[str, str]]]] = {
    "muaalem": ("obadx/muaalem-model-v3_2", muaalem, parse_arabic),
    "tarteel": (
        "tarteel-ai/whisper-base-ar-quran",
        lambda: whisper("tarteel-ai/whisper-base-ar-quran"),
        parse_arabic,
    ),
    "whisper": ("openai/whisper-small", lambda: whisper("openai/whisper-small"), parse_arabic),
    "maroof": (
        "MostafaMaroof/wav2vec2-arabic-phoneme-asr",
        lambda: ctc("MostafaMaroof/wav2vec2-arabic-phoneme-asr"),
        parse_maroof,
    ),
    "espeak": (
        "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
        lambda: ctc("facebook/wav2vec2-xlsr-53-espeak-cv-ft"),
        parse_ipa,
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("system", choices=sorted(SYSTEMS))
    parser.add_argument("--per-class", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    model_id, build, parse = SYSTEMS[args.system]
    hear = build()
    fields = [
        "clip", "class", "system", "model", "expected_letter", "expected_vowel",
        "output", "got_letter", "got_vowel", "audio_s", "compute_s",
    ]  # fmt: skip
    # Rows are written as they come, so progress is visible; with --resume a stopped run
    # continues after the clips it already has.
    done: set[str] = set()
    if args.resume and args.out.exists():
        with args.out.open(encoding="utf-8-sig", newline="") as f:
            done = {row["clip"] for row in csv.DictReader(f)}
    count = len(done)
    with args.out.open("a" if done else "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not done:
            writer.writeheader()
        for folder in sorted(p for p in args.data.iterdir() if p.is_dir()):
            number, name = folder.name.split(". ", 1)
            letter_name, vowel_name = name.rsplit("_", 1)
            letter, vowel = LETTERS[letter_name], VOWELS[vowel_name]
            text = ALIF_TEXT[vowel] if letter == HAMZA else letter + vowel
            for index, path in enumerate(pick(folder, args.per_class)):
                if f"{number}-{index:02d}" in done:
                    continue
                wave = decode(path)
                started = time.perf_counter()
                output = hear(wave, text)
                seconds = time.perf_counter() - started
                got_letter, got_vowel = parse(output)
                writer.writerow({
                    "clip": f"{number}-{index:02d}", "class": name, "system": args.system,
                    "model": model_id, "expected_letter": letter, "expected_vowel": vowel,
                    "output": output, "got_letter": got_letter, "got_vowel": got_vowel,
                    "audio_s": round(len(wave) / RATE, 2), "compute_s": round(seconds, 3),
                })  # fmt: skip
                f.flush()
                count += 1
    sys.stdout.write(f"{args.system}: {count} clips → {args.out}\n")


if __name__ == "__main__":
    main()
