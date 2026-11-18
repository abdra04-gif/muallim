"""Phase 3, step 2: turn every letter clip into numbers once, so candidates can be compared fast.

For each clip the Arabic phoneme model (MostafaMaroof/wav2vec2-arabic-phoneme-asr) gives:
  * the mean of three of its inner layers (the "embedding" a classifier can learn from);
  * for every symbol it knows, the highest score it reached anywhere in the clip;
  * its ordinary free transcription.
One file per class is written, so a stopped run continues where it was.

Usage:
    python features.py DATA_DIR OUT_DIR
Speakers are stored as short hashes of the name in the file name, never as names.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from letters_test import RATE, decode

MODEL = "MostafaMaroof/wav2vec2-arabic-phoneme-asr"
SKIP = {"[PAD]", "<pad>", "<s>", "</s>", "[UNK]", "<unk>", "|", "sil"}


def speaker_of(stem: str) -> tuple[str, int]:
    """``Name_Parts_letter_vowel[_1]`` → (hash of the first word of the name, take number).

    The same student appears under a full name in most folders and a shorter one in a few, so
    only the first word identifies a speaker. Two students with the same first name are merged;
    that makes the speaker split stricter, never leakier.
    """
    take = 1 if stem.endswith("_1") else 0
    base = stem[:-2] if take else stem
    name = base.rsplit("_", 2)[0].split("_")[0]
    return hashlib.sha256(name.lower().encode()).hexdigest()[:10], take


def main() -> None:
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from transformers import Wav2Vec2ForCTC  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    vocab = json.loads(Path(hf_hub_download(MODEL, "vocab.json")).read_text(encoding="utf-8"))
    (args.out / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")
    names = {index: symbol for symbol, index in vocab.items()}
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    depth = model.config.num_hidden_layers
    layers = [depth // 2, 3 * depth // 4, depth]

    for number, folder in enumerate(sorted(p for p in args.data.iterdir() if p.is_dir())):
        target = args.out / f"{number:02d}.npz"
        if target.exists():
            # Already computed: only refresh the speaker codes (same file order as below).
            stored = dict(np.load(target))
            stored["speaker"] = np.asarray(
                [speaker_of(p.stem)[0] for p in sorted(folder.glob("*.wav"))]
            )
            np.savez(target, **stored)
            continue
        emb, ctc, greedy, speakers, takes, seconds = [], [], [], [], [], []
        for path in sorted(folder.glob("*.wav")):
            wave = decode(path)
            norm = (wave - wave.mean()) / (wave.std() + 1e-7)
            with torch.no_grad():
                out = model(torch.from_numpy(norm).unsqueeze(0), output_hidden_states=True)
            logp = torch.log_softmax(out.logits[0], dim=-1)
            ctc.append(logp.max(dim=0).values.numpy())
            emb.append(np.stack([out.hidden_states[i][0].mean(dim=0).numpy() for i in layers]))
            symbols, last = [], -1
            for index in logp.argmax(-1).tolist():
                if index != last and names[index] not in SKIP:
                    symbols.append(names[index])
                last = index
            greedy.append(" ".join(symbols))
            speaker, take = speaker_of(path.stem)
            speakers.append(speaker)
            takes.append(take)
            seconds.append(len(wave) / RATE)
        np.savez(
            target,
            name=folder.name.split(". ", 1)[1],
            emb=np.asarray(emb, dtype=np.float16),
            ctc=np.asarray(ctc, dtype=np.float32),
            greedy=np.asarray(greedy),
            speaker=np.asarray(speakers),
            take=np.asarray(takes, dtype=np.int8),
            seconds=np.asarray(seconds, dtype=np.float32),
        )
        sys.stdout.write(f"{number + 1}/84 {len(greedy)} clips\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
