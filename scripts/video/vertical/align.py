# ruff: noqa
"""Время каждой фонемы басмалы по кадрам CTC модели Muaalem (жадно, пики)."""

import sys, numpy as np, torch
from quran_muaalem import Muaalem

x = np.fromfile(sys.argv[1], np.int16).astype(np.float32) / 32768
m = Muaalem(device="cpu", dtype=torch.float32)
f = m.processor([x], sampling_rate=16000, return_tensors="pt")
outs = m.model(**f, return_dict=False)[0]
p = torch.softmax(outs["phonemes"][0], -1)
voc = m.multi_level_tokenizer.id_to_vocab["phonemes"]
n = p.shape[0]
dt = len(x) / 16000 / n
ids = p.argmax(-1).tolist()
prev = None
start = 0
for i, k in enumerate(ids + [-1]):
    if k != prev:
        if prev is not None and voc[prev] not in ("[PAD]", "<pad>", "[UNK]") and prev != 0:
            print(f"{start * dt:5.2f}-{i * dt:5.2f} {voc[prev]!r}")
        prev, start = k, i
print("frames", n, "dt", round(dt, 4), "blank", repr(voc[0]))
