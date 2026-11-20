"""Запись фонетизатора бота → символы модели MostafaMaroof (ADR-0087 п. 8, ADR-0088 п. 2).

Прототип и замеры — `docs/research/phase3/to_maroof.py`. Правила:
    буква → свой символ; та же буква подряд (шадда, слияние, гунна) → двойной символ (bb);
    огласовка + знаки мадда → долгая гласная (aa ii uu), сколько бы знаков ни было;
    ں / ۾ (скрытые нун / мим) → n / m; ڇ (калькаля), ۜ (сакт) → ничего;
    و / ي, протянутые на остановке (لَوْ), → один символ;
    гласные — простые (a i u): твёрдую гласную модели (A I U) складывает с простой `ctc.prepare`.
"""

from typing import Final

VERSION: Final = "1"  # входит в model_version: другой перевод — другие ответы

_LETTER: Final = {
    "ء": "<", "ب": "b", "ت": "t", "ث": "^", "ج": "j", "ح": "H", "خ": "x", "د": "d", "ذ": "*",
    "ر": "r", "ز": "z", "س": "s", "ش": "$", "ص": "S", "ض": "D", "ط": "T", "ظ": "Z", "ع": "E",
    "غ": "g", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w",
    "ي": "y", "ں": "n", "۾": "m", "ٲ": "<",
}  # fmt: skip
_VOWEL: Final = {"َ": "a", "ُ": "u", "ِ": "i", "۪": "a", "ؙ": "u"}
_MADD: Final = {"ا": "a", "ۥ": "u", "ۦ": "i", "ـ": "a"}
_DROP: Final = frozenset({"ڇ", "ۜ"})
_HIDDEN: Final = frozenset({"ں", "۾"})


def to_maroof(phonetic: str) -> tuple[str, ...]:
    """Строка фонетизатора бота → звуки MostafaMaroof; незнакомый знак → ValueError."""
    out: list[str] = []
    chars = [c for c in phonetic if c not in _DROP]
    i = 0
    while i < len(chars):
        c = chars[i]
        j = i + 1
        if c in _LETTER:
            while j < len(chars) and chars[j] == c:
                j += 1
            vowel_next = j < len(chars) and chars[j] in _VOWEL
            # скрытый нун / мим (ихфа) тянется с гунной, و / ي без гласной на остановке (لَوْ) —
            # тоже протяжка: для модели это один звук; у удвоенной буквы за ней гласная
            held = c in _HIDDEN or (c in "وي" and not vowel_next)
            sym = _LETTER[c]
            out.append(sym * 2 if j - i >= 2 and not held else sym)
        elif c in _VOWEL:
            while j < len(chars) and chars[j] in _MADD:
                j += 1
            out.append(_VOWEL[c] * (2 if j > i + 1 else 1))
        elif c in _MADD:  # знак мадда без гласной перед ним — долгая гласная
            while j < len(chars) and chars[j] in _MADD:
                j += 1
            out.append(_MADD[c] * 2)
        else:
            raise ValueError(f"незнакомый знак {c!r} в {phonetic!r}")
        i = j
    return tuple(out)
