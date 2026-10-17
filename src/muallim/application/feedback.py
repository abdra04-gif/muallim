"""Объяснение ошибок ученику на выбранном языке (FR-05, FR-22, ADR-0017).

Шаблоны фраз — curriculum/feedback.<язык>.yaml, названия звуков и подсказки —
curriculum/lexicon.<язык>.yaml. Русские формулировки совпадают с прототипом (SRC-012).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from muallim.application.transcription import EMPTY, Reading, as_text, reading, transcribe
from muallim.domain.assessment import ErrorKind, PronunciationError
from muallim.domain.curriculum import Lexicon
from muallim.domain.learner import Learner
from muallim.domain.phonetics import (
    CONSONANTS,
    LONG_VOWELS,
    SHORT_VOWELS,
    syllable_index,
    syllables,
)

# Следуют за буквой: если пропущена сама буква, отдельно о них не говорим.
_FOLLOW_MISSING = frozenset({ErrorKind.VOWEL_MISSING, ErrorKind.MADD_TOO_SHORT})

# Порядок разбора (ADR-0031): лахн джали — явные ошибки, меняют слово (буква, огласовка, ташдид,
# пропуск, лишнее) — 0; лахн хафи — долгота (мадд) — 1. Источник: SRC-052.
_PRIORITY = {ErrorKind.MADD_TOO_SHORT: 1, ErrorKind.MADD_TOO_LONG: 1}


def _syllable_of(reference: str, position: int) -> int:
    """Индекс слога ``syllables(reference)``, в котором позиция ``position``."""
    for index, (_, end) in enumerate(syllables(reference)):
        if position < end:
            return index
    return max(len(syllables(reference)) - 1, 0)


def _as_heard(reference: str, start: int, end: int, errors: list[PronunciationError]) -> str:
    """Кусок эталона [start, end) так, как он прозвучал: ошибки применены к эталону."""
    out, i = [], start
    for e in sorted(errors, key=lambda e: e.position):
        at = max(e.position, i)
        out += [reference[i:at], e.heard]
        i = at + len(e.expected)
    out.append(reference[i:end])
    return "".join(out)


def _meaningful(group: list[PronunciationError]) -> list[PronunciationError]:
    """Пропущена буква — её огласовка и мадд пропущены вместе с ней: о них отдельно не говорим."""
    if any(e.kind is ErrorKind.SOUND_MISSING for e in group):
        return [e for e in group if e.kind not in _FOLLOW_MISSING]
    return group


def _focus(e: PronunciationError) -> PronunciationError:
    """«Прочитано иначе» — о первой перепутанной букве, а если буквы верны — о гласном."""
    if e.kind is not ErrorKind.FRAGMENT_SUBSTITUTION:
        return e
    for kind, sounds in (
        (ErrorKind.LETTER_SUBSTITUTION, CONSONANTS),
        (ErrorKind.VOWEL_SUBSTITUTION, SHORT_VOWELS | LONG_VOWELS),
    ):
        want = [c for c in e.expected if c in sounds]
        got = [c for c in e.heard if c in sounds]
        for a, b in zip(want, got, strict=False):
            if a != b:
                return PronunciationError(kind, e.position, e.syllable, a, b)
    return e


def _main(group: list[PronunciationError]) -> PronunciationError:
    """Главная ошибка места — о ней короткая подсказка."""
    return min(_meaningful(group), key=lambda e: _PRIORITY.get(e.kind, 0))


@dataclass(frozen=True, slots=True)
class FeedbackTemplates:
    """Шаблоны с полями: {where} {expected} {heard} {expected_vowel} {heard_vowel}
    {expected_seq} {heard_seq}. ``where`` — с полем {syllable} (слог транскрипцией) или {n}
    (номер слога, старые черновики); ``tip`` — с полем {tip}.

    ``how`` — «как сказать правильно» по типу ошибки (поле {tip} — подсказка из словаря),
    ``how_line`` — как эту строку показать (поле {how}). Без ``how`` — старый формат с ``tip``.
    """

    messages: Mapping[ErrorKind, str]
    where: str
    tip: str
    joiner: str = " + "
    how: Mapping[ErrorKind, str] = field(default_factory=dict)
    how_line: str = ""
    unread: str = ""  # «не дочитана»: поля {last} (последний прочитанный слог) и {rest}
    unread_how: str = ""
    # Коротко (ADR-0031): ``line`` — {expected} → {heard} слогами, ``line_missing`` — место
    # пропущено целиком, ``short`` — полфразы подсказки по типу ошибки (+ {expected_tr} {heard_tr}).
    # Без ``line`` — старый длинный формат.
    line: str = ""
    line_missing: str = ""
    short: Mapping[ErrorKind, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Explanation:
    """Пункт разбора: ``text`` — показать сразу, ``more`` — «👄 Подробнее» (свёрнуто)."""

    text: str
    more: str = ""


@dataclass(frozen=True, slots=True)
class FeedbackRenderer:
    lexicon: Lexicon
    templates: FeedbackTemplates

    def render(
        self, errors: tuple[PronunciationError, ...], reference: str = ""
    ) -> tuple[str, ...]:
        """Текст к каждой ошибке — для БД (detected_errors.message), по одному на ошибку.

        ``reference`` — эталон в фонемах: из него берётся слог ошибки (FR-43).
        """
        shown = reading(reference, self.lexicon) if reference else ()
        return tuple(self._message(e, reference, shown) for e in errors)

    def explain(
        self,
        errors: tuple[PronunciationError, ...],
        reference: str,
        unread: int | None = None,
    ) -> tuple[Explanation, ...]:
        """Разбор для ученика (ADR-0031): одно место — один пункт «как надо → как у тебя» и
        полфразы подсказки; «как сказать» — в ``more``. Сначала явные ошибки, потом мадд;
        непрочитанный конец — последним пунктом.

        ``unread`` — с какого слога строка не дочитана (``assessment.unread_from``).
        """
        t = self.templates
        shown = reading(reference, self.lexicon) if reference else ()
        spans = syllables(reference)
        cut = None
        if unread is not None and t.unread and 0 < unread < len(shown):
            cut = spans[unread][0]
        kept = [e for e in errors if cut is None or e.position < cut]
        ranked: list[tuple[int, int, Explanation]] = []
        for first, last, group in self._places(kept, reference) if shown else ():
            item = self._place(group, first, last, shown, reference)
            ranked.append((*self._rank(group, first), item))
        if not shown:  # без эталона (черновики, старые вызовы) — по ошибке на пункт
            ranked = [(0, n, self._long([e])) for n, e in enumerate(kept)]
        items = [item for *_, item in sorted(ranked, key=lambda r: (r[0], r[1]))]
        if cut is not None and unread is not None:
            items.append(self._unread(shown, unread))
        return tuple(dict.fromkeys(items))

    def _places(
        self, errors: list[PronunciationError], reference: str
    ) -> list[tuple[int, int, list[PronunciationError]]]:
        """Ошибки → места: слоги, задетые ошибкой; пересекающиеся места — вместе."""
        last_pos = len(reference) - 1
        places: list[tuple[int, int, list[PronunciationError]]] = []
        for e in sorted(errors, key=lambda e: e.position):
            first = _syllable_of(reference, min(e.position, last_pos))
            end = min(e.position + max(len(e.expected), 1) - 1, last_pos)
            last = _syllable_of(reference, end)
            if places and first <= places[-1][1]:
                a, b, group = places[-1]
                places[-1] = (a, max(b, last), [*group, e])
            else:
                places.append((first, last, [e]))
        return places

    @staticmethod
    def _rank(group: list[PronunciationError], first: int) -> tuple[int, int]:
        return min(_PRIORITY.get(e.kind, 0) for e in group), first

    def _place(
        self,
        group: list[PronunciationError],
        first: int,
        last: int,
        shown: Reading,
        reference: str,
    ) -> Explanation:
        t = self.templates
        if not t.line:
            return self._long(group)
        spans = syllables(reference)
        start, end = spans[first][0], spans[last][1]
        expected = "-".join(text for text, _ in shown[first : last + 1])
        heard = as_text(reading(_as_heard(reference, start, end, group), self.lexicon))
        if heard == EMPTY:
            line = t.line_missing.format(expected=expected)
        elif heard == expected:
            line = f"«{expected}»"
        else:
            line = t.line.format(expected=expected, heard=heard)
        main = _focus(_main(group))
        hint = t.short.get(main.kind, "").format(**self._fields(main))
        about = [main] if main.kind is not _main(group).kind else _meaningful(group)
        more = " ".join(dict.fromkeys(h for e in about if (h := self._how(e))))
        return Explanation("\n".join(x for x in (line, hint) if x), more)

    def _long(self, group: list[PronunciationError]) -> Explanation:
        """Старый формат: «что не так» целиком (для языков без коротких шаблонов)."""
        whats = [self._what(e, "") for e in _meaningful(group)]
        more = " ".join(dict.fromkeys(h for e in _meaningful(group) if (h := self._how(e))))
        return Explanation("\n".join(dict.fromkeys(whats)), more)

    def _unread(self, shown: Reading, unread: int) -> Explanation:
        t = self.templates
        rest = "-".join(text for text, _ in shown[unread:])
        return Explanation(t.unread.format(last=shown[unread - 1][0], rest=rest), t.unread_how)

    def describe(self, ch: str) -> str:
        if ch in self.lexicon.consonants:
            name, translit = self.lexicon.consonants[ch]
            return f"«{ch}» ({name}, {self.lexicon.transcription.get(ch) or translit})"
        if ch in self.lexicon.vowels:
            return self.lexicon.vowels[ch]
        return f"«{ch}»"

    def _where(self, e: PronunciationError, reference: str, shown: Reading) -> str:
        t = self.templates
        if "{syllable}" in t.where:
            if not shown:
                return ""
            syllable = shown[syllable_index(reference, e.syllable)][0]
            return t.where.format(n=e.syllable, syllable=syllable)
        return t.where.format(n=e.syllable) if e.syllable is not None else ""

    def _message(self, e: PronunciationError, reference: str, shown: Reading) -> str:
        t = self.templates
        msg = self._what(e, self._where(e, reference, shown))
        if t.how:
            how = self._how(e)
            if how:
                msg += t.how_line.format(how=how)
        elif e.kind is ErrorKind.LETTER_SUBSTITUTION and (tip := self._tip(e)):
            msg += t.tip.format(tip=tip)
        return msg

    def _fields(self, e: PronunciationError) -> dict[str, str]:
        vowels = self.lexicon.vowels
        return {
            "expected": self.describe(e.expected),
            "heard": self.describe(e.heard),
            "expected_vowel": vowels.get(e.expected, e.expected),
            "heard_vowel": vowels.get(e.heard, e.heard),
            "expected_seq": self.templates.joiner.join(self.describe(c) for c in e.expected),
            "heard_seq": self.templates.joiner.join(self.describe(c) for c in e.heard),
            "expected_tr": transcribe(e.expected, self.lexicon),
            "heard_tr": transcribe(e.heard, self.lexicon),
        }

    def _what(self, e: PronunciationError, where: str) -> str:
        return self.templates.messages[e.kind].format(where=where, **self._fields(e))

    def _how(self, e: PronunciationError) -> str:
        """«Как сказать» без обёртки ``how_line``; пусто, если шаблона нет."""
        template = self.templates.how.get(e.kind, "")
        return " ".join(template.format(tip=self._tip(e), **self._fields(e)).split())

    def _tip(self, e: PronunciationError) -> str:
        """Подсказка из словаря: для пары путаемых букв, для буквы или для гласного."""
        lex = self.lexicon
        if e.kind is ErrorKind.LETTER_SUBSTITUTION:
            return lex.pair_tips.get(frozenset(e.expected + e.heard)) or lex.letter_tips.get(
                e.expected, ""
            )
        if e.kind is ErrorKind.FRAGMENT_SUBSTITUTION and len(e.expected) == len(e.heard):
            # несколько замен подряд: подсказка к каждой паре «нужно → прозвучало»
            parts = (
                self._tip(PronunciationError(ErrorKind.LETTER_SUBSTITUTION, 0, None, want, got))
                if want in lex.letter_tips and got in lex.letter_tips
                else lex.vowel_tips.get(want, "")
                for want, got in zip(e.expected, e.heard, strict=True)
                if want != got
            )
            return " ".join(dict.fromkeys(tip for tip in parts if tip))
        if e.expected in lex.letter_tips:
            return lex.letter_tips[e.expected]
        return lex.vowel_tips.get(e.expected, "")


@dataclass(frozen=True, slots=True)
class FeedbackLanguage:
    code: str  # ru, kk, en
    title: str  # как показать в /language: «Русский», «Қазақша»
    enabled: bool  # включает человек после проверки перевода
    lexicon: Lexicon
    templates: FeedbackTemplates

    @property
    def renderer(self) -> FeedbackRenderer:
        return FeedbackRenderer(self.lexicon, self.templates)


@dataclass(frozen=True, slots=True)
class FeedbackCatalog:
    languages: Mapping[str, FeedbackLanguage]
    default: str = "ru"

    def __post_init__(self) -> None:
        if self.default not in self.enabled():
            raise ValueError(f"Язык по умолчанию {self.default!r} должен быть включён")

    def all_languages(self) -> list[str]:
        return sorted(self.languages)

    def enabled(self) -> list[str]:
        return sorted(c for c, lang in self.languages.items() if lang.enabled)

    def language(self, code: str) -> FeedbackLanguage:
        return self.languages[code]

    def renderer(self, code: str) -> FeedbackRenderer:
        return self.languages[code].renderer

    def resolve(self, learner: Learner) -> str:
        """Язык объяснений: выбранный → язык Telegram → по умолчанию (только включённые)."""
        for code in (learner.feedback_language, learner.language):
            if code and code in self.languages and self.languages[code].enabled:
                return code
        return self.default
