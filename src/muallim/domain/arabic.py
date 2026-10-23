"""Разбор арабской строки на буквы и сопоставление с эталоном в фонемах (FR-54, ADR-0024).

Нужен двум слоям: разбору ошибок группами (какие слова и буквы задеты — application) и картинке
(какую букву красить — presentation). Поэтому живёт в домене и не знает ни о шрифтах, ни о
Telegram. ``presentation.telegram.render`` реэкспортирует эти же объекты.
"""

import difflib
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from muallim.domain.phonetics import CONSONANTS

SHADDA: Final = "ّ"
HAMZA_FORMS: Final = frozenset("ءأإؤئآ")
MADD_LETTERS: Final = frozenset("اىوي")  # без знаков — удлинение, а не согласный
PHONEME_OF: Final = {"ة": "ت", "ى": "ي"}  # как буква текста записана в фонемах
ALIF_WASL: Final = "ٱ"
HAMZA_MARKS: Final = frozenset("\u0654\u0655")  # хамза над и под буквой (на татвиле)


@dataclass(frozen=True, slots=True)
class Cluster:
    """Буква со своими огласовками; start/end — индексы в строке."""

    start: int
    end: int
    base: str
    marks: str

    @property
    def is_consonant(self) -> bool:
        if self.base in HAMZA_FORMS or HAMZA_MARKS & set(self.marks):
            return True  # и хамза над татвилем «ـٔ» (L046-06)
        if self.base in MADD_LETTERS and not self.marks:
            return False
        return unicodedata.category(self.base) == "Lo"


def clusters(text: str) -> list[Cluster]:
    out: list[Cluster] = []
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and unicodedata.category(text[j]) == "Mn":
            j += 1
        if not text[i].isspace():
            out.append(Cluster(i, j, text[i], text[i + 1 : j]))
        i = j
    return out


def consonant_clusters(text: str) -> list[int]:
    """Номер кластера для каждого согласного по порядку (шадда — два согласных)."""
    order: list[int] = []
    for n, c in enumerate(clusters(text)):
        if c.is_consonant:
            order += [n] * (2 if SHADDA in c.marks else 1)
    return order


def error_clusters(
    text: str, syllables: Collection[int | None], reference: str | None = None
) -> set[int]:
    """Слоги ошибок (с 1, по согласным эталона) → кластеры текста (ADR-0024).

    С ``reference`` (эталон в фонемах) согласные сопоставляются по буквам: в фонемах шадда
    бывает одной согласной, «ٱ» внутри фразы не читается, и счёт по номеру уезжает.
    Буквы мадда и непроизносимые буквы подсвечиваются вместе со своим слогом.
    """
    if reference is None:
        order = consonant_clusters(text)
        return {order[s - 1] for s in syllables if s is not None and 1 <= s <= len(order)}
    owner = _owners(text, reference)
    letters = clusters(text)
    found = set()
    for s in syllables:
        if s is not None and 1 <= s <= len(owner):
            found.add(owner[s - 1])
    # к ошибочной букве — её «хвост» без своего звука (мадд, татвиль) и немые буквы перед ней
    tied = _tied(letters, set(owner))
    return {n for n in range(len(letters)) if tied[n] in found}


def unread_clusters(text: str, reference: str, consonant: int) -> set[int]:
    """Кластеры текста от ``consonant``-й согласной эталона (с 1) до конца строки."""
    total = sum(1 for ch in reference if ch in CONSONANTS)
    return error_clusters(text, range(consonant, total + 1), reference)


def owners(text: str, reference: str) -> list[int]:
    """Для каждой согласной эталона (по порядку) — номер кластера текста, её буквы."""
    return _owners(text, reference)


def consonant_words(text: str, reference: str) -> list[int]:
    """Для каждой согласной эталона — номер слова строки ``text`` (с 0), где она звучит."""
    word_of = cluster_words(text)
    return [word_of[n] for n in _owners(text, reference)]


def cluster_words(text: str) -> list[int]:
    """Номер слова (с 0) для каждого кластера строки."""
    out, word, gap = [], -1, True
    for i, ch in enumerate(text):
        if ch.isspace():
            gap = True
            continue
        if gap:
            word, gap = word + 1, False
        out.append((i, word))
    word_at = dict(out)
    return [word_at[c.start] for c in clusters(text)]


def _letter(c: Cluster) -> str:
    """Буква текста так, как она записана в фонемах."""
    if c.base in HAMZA_FORMS or c.base == ALIF_WASL or HAMZA_MARKS & set(c.marks):
        return "ء"
    return PHONEME_OF.get(c.base, c.base)


def phoneme_of(letter: str) -> str:
    """Буква текста (ة, أ) → как она записана в фонемах (ت, ء)."""
    if letter in HAMZA_FORMS or letter == ALIF_WASL:
        return "ء"
    return PHONEME_OF.get(letter, letter)


def _owners(text: str, reference: str) -> list[int]:
    """Для каждой согласной эталона — кластер текста, к которому она относится.

    Буква с шаддой — две согласные (как в фонемах «رَببَ»), поэтому вторая половина ташдида
    остаётся у своей буквы и своего слова; «ٱ» внутри фразы в фонемах пропущена — просто
    не получает согласной.
    """
    letters = clusters(text)
    spoken = consonant_clusters(text)
    sounds = [ch for ch in reference if ch in CONSONANTS]
    if not spoken:
        return [0] * len(sounds) if letters else []
    matcher = difflib.SequenceMatcher(
        None, [_letter(letters[n]) for n in spoken], sounds, autojunk=False
    )
    owner: list[int] = []
    for _, i1, i2, j1, j2 in matcher.get_opcodes():
        for k in range(j2 - j1):
            if i2 > i1:  # equal/replace: по порядку, лишние фонемы — к последней букве
                owner.append(spoken[min(i1 + k, i2 - 1)])
            else:  # вставка (танвин, лишняя согласная) — к предыдущей букве
                owner.append(owner[-1] if owner else spoken[min(i1, len(spoken) - 1)])
    return owner


def _tied(letters: Sequence[Cluster], voiced: set[int]) -> list[int]:
    """Кластер → чью ошибку он разделяет: буква без звука — с соседней звучащей."""
    tied = list(range(len(letters)))
    last = None
    for n, c in enumerate(letters):  # мадд и татвиль — к предыдущей звучащей
        if n in voiced:
            last = n
        elif not c.is_consonant and last is not None:
            tied[n] = last
    following = None
    for n in range(len(letters) - 1, -1, -1):  # немая согласная (ٱ, лям) — к следующей
        if n in voiced:
            following = n
        elif letters[n].is_consonant and following is not None:
            tied[n] = following
    return tied


def tail_of(text: str, reference: str, cluster: int) -> set[int]:
    """Кластер и его «хвост» без своего звука (буква мадда, татвиль) — для подсветки мадда."""
    letters = clusters(text)
    tied = _tied(letters, set(_owners(text, reference)))
    return {n for n in range(len(letters)) if tied[n] == cluster} | {cluster}


class WordState(StrEnum):
    OK = "ok"
    WRONG = "wrong"
    UNREAD = "unread"


def word_states(text: str, wrong: Collection[int], unread: Collection[int]) -> list[WordState]:
    """Состояние каждого слова строки по кластерам ошибок: хоть одна ошибка — слово неверно;
    все буквы не прочитаны — слово не прочитано."""
    words = text.split()
    of_word: list[list[int]] = [[] for _ in words]
    for n, c in enumerate(clusters(text)):
        of_word[text[: c.start].count(" ") if " " in text else 0].append(n)
    out = []
    for members in of_word:
        if members and all(m in unread for m in members):
            out.append(WordState.UNREAD)
        elif any(m in wrong and m not in unread for m in members):
            out.append(WordState.WRONG)
        else:
            out.append(WordState.OK)
    return out
