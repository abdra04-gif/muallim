"""Транскрипция фонем буквами языка ученика: «как читается» и «как прозвучало» (FR-21, FR-43).

Вспомогательная подсказка, а не замена образцу: преподаватели советуют учиться на слух
(методическое решение M-09, M-10; SRC-021, SRC-022). Поэтому на карточке она под спойлером.
Таблица — в ``lexicon.<язык>.yaml`` (по Крачковскому, SRC-051).
"""

import re
from collections.abc import Collection

from muallim.domain.curriculum import Lexicon
from muallim.domain.phonetics import syllable_index, syllables

EMPTY = "—"
SEPARATOR = "-"
Reading = tuple[tuple[str, bool], ...]  # (слог транскрипцией, есть ли в нём ошибка)

# Мадд на 4–6 счётов — всё равно две буквы: длину объясняет подсказка, а не «ииииии».
_LONG_RUN = re.compile(r"([аеиоуэ])\1{2,}")


def transcribe(phonemes: str, lexicon: Lexicon) -> str:
    if not phonemes:
        return EMPTY
    text = "".join(lexicon.transcription.get(ch, ch) for ch in phonemes)
    return _LONG_RUN.sub(r"\1\1", text) or EMPTY


def reading(phonemes: str, lexicon: Lexicon, wrong: Collection[int | None] = ()) -> Reading:
    """Слоги транскрипцией; ``wrong`` — номера согласных с ошибкой (как в PronunciationError)."""
    marked = {syllable_index(phonemes, n) for n in wrong}
    return tuple(
        (transcribe(phonemes[start:end], lexicon), i in marked)
        for i, (start, end) in enumerate(syllables(phonemes))
    )


def as_text(shown: Reading) -> str:
    return SEPARATOR.join(text for text, _ in shown) if shown else EMPTY


def legend(text: str, lexicon: Lexicon) -> tuple[str, ...]:
    """Пояснения только к тем значкам, что есть в строке, и называют только их."""
    lines = []
    for marks, hint in lexicon.transcription_legend.items():
        present = [mark for mark in marks.split() if mark in text]
        if present:
            lines.append(f"{' '.join(present)} — {hint}")
    return tuple(lines)
