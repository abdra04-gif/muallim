"""Разбор попытки группами для новичка (FR-54, этап 1; ADR-0070).

Одинаковые ошибки — одна группа «N раз» со словами, где они случились. Ключ — вид ошибки, нужный
звук и прозвучавший: у согласной — буквы («ح → ه»), у огласовки и мадда — знаки («дамма →
фатха» на любых буквах — одна группа). Число раз — число разных мест (буква с шаддой — одно
место). Буква урока — первой (ADR-0062, В3), затем явные ошибки, затем мадд (ADR-0031), внутри —
по строке. Ошибки после «не дочитал» в группы не входят; огласовка и мадд пропущенной буквы уходят
вместе с ней. Подписи — простой кириллицей (``Lexicon.sounds``, ``Lexicon.syllables``).

Только сборка данных: текст экрана и картинку строит presentation; полный текст каждой ошибки для
БД — ``feedback.py``.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from muallim.application.feedback import FOLLOW_MISSING, PRIORITY, focus
from muallim.application.transcription import EMPTY, plain, transcribe
from muallim.domain import arabic
from muallim.domain.assessment import Assessment, ErrorKind, PronunciationError
from muallim.domain.curriculum import Lexicon
from muallim.domain.phonetics import CONSONANTS, LONG_VOWELS, SHORT_VOWELS, syllables

VOWEL_KINDS: Final = frozenset(
    {
        ErrorKind.VOWEL_SUBSTITUTION,
        ErrorKind.VOWEL_MISSING,
        ErrorKind.MADD_TOO_SHORT,
        ErrorKind.MADD_TOO_LONG,
    }
)
# «Буква урока прозвучала иначе или пропущена»; огласовка и удвоение — не другая буква (В3 (а)).
LETTER_KINDS: Final = frozenset(
    {
        ErrorKind.LETTER_SUBSTITUTION,
        ErrorKind.SOUND_SUBSTITUTION,
        ErrorKind.FRAGMENT_SUBSTITUTION,
        ErrorKind.SOUND_MISSING,
    }
)
_VOWELS: Final = SHORT_VOWELS | LONG_VOWELS


@dataclass(frozen=True, slots=True)
class Place:
    """Одно место ошибки: слово строки (с 0), его чтение, буквы (кластеры) для подсветки."""

    word_index: int
    word_text: str
    word_reading: str
    clusters: tuple[int, ...]
    errors: tuple[PronunciationError, ...]


@dataclass(frozen=True, slots=True)
class ErrorGroup:
    kind: ErrorKind
    expected: str  # нужный звук (фонема): буква или знак
    heard: str  # прозвучавший; пусто — пропущен
    need_label: str  # «нужно» простой кириллицей: «ха» горлом
    heard_label: str  # «у тебя»: «ха» легко, «пропущено»
    places: tuple[Place, ...]
    lesson_letter: bool = False
    letter: str = ""  # буква как в тексте (ة, أ); пусто — звука нет буквой (н танвина)
    carrier: str = ""  # огласовка и мадд: буква-носитель, если она одна во всех местах

    @property
    def times(self) -> int:
        return len(self.places)


@dataclass(frozen=True, slots=True)
class Breakdown:
    groups: tuple[ErrorGroup, ...]
    words_ok: int
    words_total: int
    unread: tuple[int, ...] = ()  # номера не дочитанных слов (с 0)


@dataclass(frozen=True, slots=True)
class _Focused:
    error: PronunciationError  # как в оценке (сохраняется в месте)
    main: PronunciationError  # о чём говорим (``focus``)
    position: int  # где в эталоне буква или огласовка, о которой говорим


@dataclass(frozen=True, slots=True)
class _Line:
    """Строка и эталон: где согласные эталона, какой букве и слову строки каждая принадлежит."""

    text: str
    ref: str
    lexicon: Lexicon
    words: tuple[str, ...]
    letters: tuple[arabic.Cluster, ...]
    consonants: tuple[int, ...]  # позиции согласных в эталоне
    owner: tuple[int, ...]  # согласная эталона → кластер текста
    word_of: tuple[int, ...]  # кластер текста → слово

    @classmethod
    def of(cls, text: str, ref: str, lexicon: Lexicon) -> "_Line":
        return cls(
            text,
            ref,
            lexicon,
            tuple(text.split()),
            tuple(arabic.clusters(text)),
            tuple(i for i, ch in enumerate(ref) if ch in CONSONANTS),
            tuple(arabic.owners(text, ref)),
            tuple(arabic.cluster_words(text)),
        )

    def consonant_at(self, position: int) -> int:
        """Номер согласной эталона, к которой относится позиция (огласовка — к своей букве)."""
        last = max(len(self.consonants) - 1, 0)
        return min(max(bisect_right(self.consonants, position) - 1, 0), last)

    def cluster_of(self, k: int) -> int | None:
        return self.owner[k] if k < len(self.owner) else None

    def word_of_consonant(self, k: int) -> int:
        cluster = self.cluster_of(k)
        if cluster is None or cluster >= len(self.word_of):
            return 0
        return self.word_of[cluster]

    def written(self, k: int) -> str:
        """Буква текста, к которой относится согласная эталона (как написана: ة, أ)."""
        cluster = self.cluster_of(k)
        if cluster is None or cluster >= len(self.letters):
            return ""
        c = self.letters[cluster]
        return "ء" if arabic.HAMZA_MARKS & set(c.marks) else c.base


def build_breakdown(
    assessment: Assessment,
    text: str,
    lexicon: Lexicon,
    *,
    unread: int | None = None,
    lesson_letter: str | None = None,
) -> Breakdown:
    """Разбор попытки строки ``text`` группами. ``unread`` — ``assessment.unread_from``."""
    line = _Line.of(text, assessment.reference, lexicon)
    spans = syllables(line.ref)
    cut = spans[unread][0] if unread is not None and 0 < unread < len(spans) else None
    kept = [e for e in assessment.errors if cut is None or e.position < cut]
    kept = [e for e in kept if not _follows_missing(line, e, kept)]

    grouped: dict[tuple[str, ...], dict[object, list[tuple[int, _Focused]]]] = {}
    for e in kept:
        f = _focused(e)
        k = line.consonant_at(max(f.position if f.main.expected else f.position - 1, 0))
        key = (f.main.kind, f.main.expected, f.main.heard)
        cluster = line.cluster_of(k)
        place = cluster if cluster is not None else ("k", k)
        grouped.setdefault(key, {}).setdefault(place, []).append((k, f))

    ranked: list[tuple[tuple[int, int, int], ErrorGroup]] = []
    for places_of in grouped.values():
        found = list(places_of.values())
        group = _group(line, found, lesson_letter)
        start = min(f.position for one in found for _, f in one)
        rank = (0 if group.lesson_letter else 1, PRIORITY.get(group.kind, 0), start)
        ranked.append((rank, group))
    groups = tuple(g for _, g in sorted(ranked, key=lambda r: r[0]))

    unread_words = _unread_words(line, assessment.heard, cut)
    wrong = {p.word_index for g in groups for p in g.places}
    ok = len(line.words) - len(wrong | set(unread_words))
    return Breakdown(groups, max(ok, 0), len(line.words), unread_words)


def _unread_words(line: _Line, heard: str, cut: int | None) -> tuple[int, ...]:
    """Слова от места остановки до конца. Слово, оборванное посередине, — тоже не дочитано (B1);
    дочитанное до конца слово (эталон-текст: пробел достаётся последнему слогу) — нет."""
    if cut is None or not line.owner:
        return ()
    k_cut = bisect_left(line.consonants, cut)
    if k_cut >= len(line.owner):
        return ()
    first = line.word_of_consonant(k_cut)
    if k_cut and line.word_of_consonant(k_cut - 1) == first:
        rest = len(line.ref)
        for k in range(k_cut, len(line.consonants)):
            if line.word_of_consonant(k) != first:
                rest = line.consonants[k]
                break
        tail = "".join(line.ref[cut:rest].split())
        if tail and "".join(heard.split()).endswith(tail):
            first += 1  # слово дочитано: остановка после него
    return tuple(range(first, len(line.words)))


def _follows_missing(
    line: _Line, e: PronunciationError, errors: Sequence[PronunciationError]
) -> bool:
    """Огласовка и мадд пропущенной буквы уходят вместе с ней: тот же слог (I1)."""
    if e.kind not in FOLLOW_MISSING:
        return False
    k = line.consonant_at(e.position)
    return any(
        m.kind is ErrorKind.SOUND_MISSING
        and m.position < e.position
        and line.consonant_at(m.position) == k
        for m in errors
    )


def _focused(e: PronunciationError) -> _Focused:
    """Ошибка и то, о чём говорим: в замене куска — первая перепутанная буква или огласовка."""
    main = focus(e)
    if main is e:
        return _Focused(e, e, e.position)
    sounds = CONSONANTS if main.kind is ErrorKind.LETTER_SUBSTITUTION else _VOWELS
    want = [i for i, ch in enumerate(e.expected) if ch in sounds]
    got = [ch for ch in e.heard if ch in sounds]
    for i, b in zip(want, got, strict=False):
        if e.expected[i] != b:
            return _Focused(e, main, e.position + i)
    return _Focused(e, main, e.position)


def _is_lesson_letter(e: PronunciationError, letter: str | None) -> bool:
    if not letter or e.kind not in LETTER_KINDS:
        return False
    if e.kind is ErrorKind.FRAGMENT_SUBSTITUTION:
        return letter in e.expected and letter not in e.heard
    return e.expected == letter


def _group(
    line: _Line, found: list[list[tuple[int, _Focused]]], lesson_letter: str | None
) -> ErrorGroup:
    k0, first = found[0][0]
    main = first.main
    places = tuple(_place(line, one) for one in found)
    letter = carrier = ""
    if main.kind in VOWEL_KINDS:
        carriers = {line.written(k) for one in found for k, _ in one}
        carrier = carriers.pop() if len(carriers) == 1 else ""
        need, heard = _vowel_labels(line, main, k0, [f for _, f in found[0]], bool(carrier))
    else:
        written = line.written(k0)
        if main.expected and arabic.phoneme_of(written) == main.expected:
            letter = written
        need, heard = _letter_labels(line, main, k0, written=letter)
    return ErrorGroup(
        main.kind,
        main.expected,
        main.heard,
        need,
        heard,
        places,
        _is_lesson_letter(main, lesson_letter),
        letter,
        carrier,
    )


def _place(line: _Line, found: list[tuple[int, _Focused]]) -> Place:
    k = found[0][0]
    word = line.word_of_consonant(k)
    cluster = line.cluster_of(k)
    marked: set[int] = set()
    if cluster is not None:
        marked = {cluster}
        if any(
            f.main.kind in (ErrorKind.MADD_TOO_SHORT, ErrorKind.MADD_TOO_LONG) for _, f in found
        ):
            marked = arabic.tail_of(line.text, line.ref, cluster)
    word_text = line.words[word] if word < len(line.words) else ""
    return Place(
        word_index=word,
        word_text=word_text,
        word_reading=plain(word_text, line.lexicon) if word_text else EMPTY,
        clusters=tuple(sorted(marked)),
        errors=tuple(f.error for _, f in found),
    )


def _letter_labels(
    line: _Line, main: PronunciationError, k: int, *, written: str
) -> tuple[str, str]:
    """Буква: «ха» горлом → «ха» легко; пропуск — «пропущено»; шадда — «кук-ки» → «ку-ки»."""
    lexicon = line.lexicon
    missing = lexicon.missing or EMPTY
    if main.kind is ErrorKind.SHADDA_MISSING and line.consonants:
        need, heard = _shadda(line, k)
        return f"«{plain(need, lexicon)}»", f"«{plain(heard, lexicon)}»"
    need = _sound_label(main.expected, lexicon, written=written or None)
    heard = missing if main.kind is ErrorKind.SOUND_MISSING else _sound_label(main.heard, lexicon)
    return need, heard


def _shadda(line: _Line, k: int) -> tuple[str, str]:
    """Слог с удвоением и без: от предыдущей согласной до гласных после удвоенной буквы."""
    ref, consonants = line.ref, line.consonants
    letter = ref[consonants[k]]
    first = last = k
    while first > 0 and ref[consonants[first - 1]] == letter:
        first -= 1
    while last + 1 < len(consonants) and ref[consonants[last + 1]] == letter:
        last += 1
    start = consonants[first - 1] if first > 0 else consonants[first]
    end = consonants[last] + 1
    while end < len(ref) and ref[end] in _VOWELS:
        end += 1
    head, tail = ref[start : consonants[first]], ref[consonants[last] + 1 : end]
    return head + letter * 2 + tail, head + letter + tail


def _sound_label(sound: str, lexicon: Lexicon, *, written: str | None = "") -> str:
    """«ха» горлом; без подписи в словаре — буква как в тексте и название: ة (Тэ), ح (Хэ); звук
    без буквы в тексте (``written is None``: н танвина) — только звук: «н»."""
    if not sound:
        return EMPTY
    if len(sound) == 1 and sound in CONSONANTS and written is not None:
        say, note = lexicon.sounds.get(sound, ("", ""))
        if say:  # буква — в начале пункта, в подписи — только звук
            return " ".join(x for x in (f"«{say}»", note) if x)
        name = lexicon.consonants.get(sound, ("", ""))[0]
        letter = written or sound
        return f"{letter} ({name})" if name else letter
    return f"«{plain(sound, lexicon)}»"


def _vowel_labels(
    line: _Line, main: PronunciationError, k: int, found: list[_Focused], one_letter: bool
) -> tuple[str, str]:
    """Огласовка и мадд: слог буквы («фа» → «фи»), а если букв много — только звук («у» → «а»)."""
    lexicon = line.lexicon
    if line.consonants:
        start = end = line.consonants[k]
        while end + 1 < len(line.ref) and line.ref[end + 1] in _VOWELS:
            end += 1
        need = line.ref[start : end + 1]
    else:
        need = main.expected
    carrier, vowels = (need[:1], need[1:]) if line.consonants else ("", need)
    if main.kind is ErrorKind.MADD_TOO_SHORT:
        heard = carrier + "".join(ch for ch in vowels if ch in SHORT_VOWELS)
    elif main.kind is ErrorKind.MADD_TOO_LONG:
        heard = need + main.heard * 2
    else:
        heard = need
        for f in sorted(found, key=lambda f: f.position, reverse=True):
            at = f.position - (line.consonants[k] if line.consonants else 0)
            heard = heard[:at] + f.main.heard + heard[at + len(f.main.expected) :]
    if not one_letter:  # «Знак дамма: нужно «у», у тебя «а»» — только сам звук знака
        sound = main.expected or main.heard
        need, heard = {
            ErrorKind.MADD_TOO_SHORT: (sound * 2, sound),
            ErrorKind.MADD_TOO_LONG: (sound, sound * 2),
        }.get(main.kind, (main.expected, main.heard))
        carrier = ""
    note = lexicon.sounds.get(carrier, ("", ""))[1] if carrier else ""
    missing = main.kind is ErrorKind.VOWEL_MISSING and not heard[len(carrier) :]
    need_label = _syllable_label(need, lexicon, note)
    heard_label = (lexicon.missing or EMPTY) if missing else _syllable_label(heard, lexicon, note)
    return need_label, heard_label


def _syllable_label(syllable: str, lexicon: Lexicon, note: str) -> str:
    """Слог как в карточке курса: «фа», «сы», «ха» горлом; знак без буквы — «у», «аа»."""
    if syllable and syllable[0] in CONSONANTS:
        spoken = plain(syllable, lexicon)
    else:
        spoken = "".join(
            ch for ch in transcribe(syllable, lexicon) if ch.isalpha() and not ch.isascii()
        )
    shown = f"«{spoken}»" if spoken and spoken != EMPTY else EMPTY
    return " ".join(x for x in (shown, note) if x)
