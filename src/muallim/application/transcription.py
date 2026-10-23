"""Транскрипция фонем буквами языка ученика: «как читается» и «как прозвучало» (FR-21, FR-43).

Вспомогательная подсказка, а не замена образцу: преподаватели советуют учиться на слух
(методическое решение M-09, M-10; SRC-021, SRC-022). Поэтому на карточке она под спойлером.
Таблица — в ``lexicon.<язык>.yaml`` (по Крачковскому, SRC-051).
"""

import re
import unicodedata
from collections.abc import Collection
from typing import Final

from muallim.domain.arabic import ALIF_WASL, HAMZA_MARKS, PHONEME_OF, SHADDA, clusters
from muallim.domain.curriculum import Lexicon
from muallim.domain.phonetics import syllable_index, syllables

EMPTY = "—"
SEPARATOR = "-"
Reading = tuple[tuple[str, bool], ...]  # (слог транскрипцией, есть ли в нём ошибка)

# Мадд на 4–6 счётов — всё равно две буквы: длину объясняет подсказка, а не «ииииии».
_LONG_RUN = re.compile(r"([аеиоуэ])\1{2,}")
# Опоры хамзы читаются как сама хамза (FR-54): в слоге не остаётся арабской буквы.
_HAMZA_SEATS: Final = str.maketrans(dict.fromkeys("أإؤئ", "ء"))
# Простая кириллица (FR-54, Р1): без точек и черт снизу, без апострофов хамзы и эйна.
_DIACRITICS: Final = frozenset("\u0323\u0331\u0303")
_PLAIN: Final = str.maketrans({"һ": "х", "ў": "у", "’": "", "‘": "", "|": ""})
_TANWIN: Final = {"ً": "َن", "ٍ": "ِن", "ٌ": "ُن"}
_DAGGER_ALIF, _TATWEEL = "ٰ", "ـ"
_MADD_OF: Final = {"ا": "َ", "ي": "ِ", "و": "ُ", "ى": "َ"}
_LONG_OF: Final = {"ا": "ا", "ي": "ۦ", "و": "ۥ", "ى": "ا"}
_SHORT: Final = "َِ" + "ُ"  # фатха, кясра, дамма — порядок слогов в ``Lexicon.syllables``
_LONG: Final = "اۦۥ"


def _spoken(phonemes: str) -> str:
    """Без пробелов, опоры хамзы — ء: слоги делятся одинаково для текста и фонем."""
    return "".join(phonemes.split()).translate(_HAMZA_SEATS)


def transcribe(phonemes: str, lexicon: Lexicon) -> str:
    if not phonemes:
        return EMPTY
    text = "".join(lexicon.transcription.get(ch, ch) for ch in phonemes)
    return _LONG_RUN.sub(r"\1\1", text) or EMPTY


def reading(phonemes: str, lexicon: Lexicon, wrong: Collection[int | None] = ()) -> Reading:
    """Слоги транскрипцией; ``wrong`` — номера согласных с ошибкой (как в PronunciationError)."""
    phonemes = _spoken(phonemes)
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


def _as_phonemes(text: str) -> str:
    """Текст карточки → примерно фонемы: шадда — две согласные, танвин — «н» (алиф после него не
    читается), буква мадда — долгий гласный, «ٱ» внутри и татвиль не читаются, солнечная ل
    уподобляется («ар-ра…»), хамза на татвиле — ء. Фонемы (эталон модели) почти не меняются."""
    out: list[str] = []
    previous_vowel = ""
    after_tanwin = False
    letters = clusters(_spoken(text))
    for n, c in enumerate(letters):
        base, marks = c.base, c.marks.replace(_DAGGER_ALIF, "ا")
        if HAMZA_MARKS & set(marks):
            base, marks = "ء", "".join(m for m in marks if m not in HAMZA_MARKS)
        if n == 0 and base == ALIF_WASL and not marks:
            base, marks = "ء", "َ"  # с «ٱ» начинают чтение — «а» (ал-хам-ду)
        elif base in (ALIF_WASL, _TATWEEL) and not marks.strip("ا"):
            out.append(marks)  # «ٱ» не читается, «ـٰ» — долгое «аа»
            continue
        if base == "ا" and any(v in marks for v in _MADD_OF.values()):
            base = "ء"  # алиф с огласовкой («اِسْتَ») читается как хамза
        following = letters[n + 1] if n + 1 < len(letters) else None
        if base == "ل" and not marks and following and SHADDA in following.marks:
            continue  # солнечная ل: «ٱلرَّحِيمِ» — ар-ра-хии-ми
        if base in "اى" and not marks and (after_tanwin or (out and out[-1] == "ۥ")):
            after_tanwin = False
            continue  # «ثَوْبًا», «هُدًى», «قَالُوا»: алиф не читается
        if base in _MADD_OF and not marks and previous_vowel == _MADD_OF[base]:
            out.append(_LONG_OF[base])
            previous_vowel = ""
            continue
        after_tanwin = any(t in marks for t in _TANWIN)
        for tanwin, spelled in _TANWIN.items():
            marks = marks.replace(tanwin, spelled)
        base = PHONEME_OF.get(base, base)
        if SHADDA in marks:
            base, marks = base + base, marks.replace(SHADDA, "")
        out.append(base + marks)
        vowels = [ch for ch in marks if ch in _MADD_OF.values()]
        previous_vowel = vowels[-1] if vowels and not after_tanwin else ""
    return "".join(out)


def plain(phonemes: str, lexicon: Lexicon) -> str:
    """Слоги простой кириллицей через дефис: «мух-си-ну», «ах-са-на», «со-ба-ра» (FR-54, Р1).

    Новичок с нуля не читает значков х̣ һ ’ (docs/requirements/audience.md): разницу звуков на
    экране несёт подпись группы («ха» горлом / «ха» легко), а не транскрипция. Короткий слог
    буквы — как в карточке курса (``Lexicon.syllables``: «со · сы · су»).
    """
    source = _as_phonemes(phonemes)
    parts = [_syllable(source[a:b], lexicon) for a, b in syllables(source)]
    return SEPARATOR.join(p for p in parts if p and p != EMPTY) or EMPTY


def _syllable(part: str, lexicon: Lexicon) -> str:
    """Слог простой кириллицей; буква с короткой огласовкой — слог из карточки курса."""
    cards = lexicon.syllables.get(part[:1])
    vowel = part[1:2]
    if cards and vowel in _SHORT and not (part[2:3] and part[2] in _LONG):
        rest = part[2:]
        return cards[_SHORT.index(vowel)] + (_simple(transcribe(rest, lexicon)) if rest else "")
    return _simple(transcribe(part, lexicon))


def _simple(text: str) -> str:
    if text == EMPTY:
        return ""
    out = "".join(ch for ch in unicodedata.normalize("NFC", text) if ch not in _DIACRITICS)
    return "".join(ch for ch in out.translate(_PLAIN) if not ("\u0600" <= ch <= "\u06ff"))
