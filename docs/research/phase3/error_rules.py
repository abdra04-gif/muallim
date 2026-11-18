# ruff: noqa: E501, RUF005
"""Typical errors of a beginner as rules over the expected sound sequence — a DRAFT for the author.

Symbols are the Halabi-style phonemes of IqraEval / MostafaMaroof: a doubled consonant is a
shadda (bb), a doubled vowel is a madd (aa, ii, uu), capital A I U are vowels after emphatic
letters. Which rules apply to which cards of the book is a methodology decision of the author
(docs/research/ERROR_RULES_DRAFT.md).

    variants(tokens) -> {rule: [(position, error_sequence), ...]}
"""

SHORT = {"a", "i", "u", "A", "I", "U"}
LONG = {"aa", "ii", "uu", "AA", "II", "UU"}
VOWELS = SHORT | LONG
OTHER_SHORT = {
    "a": ("i", "u"),
    "i": ("a", "u"),
    "u": ("a", "i"),
    "A": ("I", "U"),
    "I": ("A", "U"),
    "U": ("A", "I"),
}
# Look-alike consonants (the same pairs as in the single-letter tests), both directions.
LOOKALIKE = {"d": ("t", "D"), "t": ("d", "T"), "S": ("s",), "s": ("S", "^"), "D": ("d",), "T": ("t",),
             "Z": ("z", "*"), "z": ("Z", "*"), "^": ("s",), "H": ("h",), "h": ("H",), "E": ("<",),
             "<": ("E",), "q": ("k",), "k": ("q",), "*": ("z", "Z")}  # fmt: skip

RULES = ("vowel", "vowel_on_sukun", "no_shadda", "short_madd", "added_length", "lookalike")


def _consonant(t: str) -> bool:
    return t not in VOWELS


def variants(tokens: list[str]) -> dict[str, list[tuple[int, list[str]]]]:
    out: dict[str, list[tuple[int, list[str]]]] = {r: [] for r in RULES}
    n = len(tokens)
    for i, t in enumerate(tokens):
        if t in SHORT:
            for o in OTHER_SHORT[t]:  # another vowel sign: كَتَبَ → كَتِبَ
                out["vowel"].append((i, tokens[:i] + [o] + tokens[i + 1 :]))
            out["added_length"].append(
                (i, tokens[:i] + [t + t] + tokens[i + 1 :])
            )  # held short vowel
        if t in LONG:
            out["short_madd"].append((i, tokens[:i] + [t[0]] + tokens[i + 1 :]))  # قَالَ → قَلَ
        if _consonant(t) and i + 1 < n and _consonant(tokens[i + 1]):
            # consonant with sukun (no vowel after it): a learner adds a vowel — اَبْ → اَبَ
            v = "a" if t.islower() else "A"
            out["vowel_on_sukun"].append((i, tokens[: i + 1] + [v] + tokens[i + 1 :]))
        if _consonant(t) and len(t) == 2 and t[0] == t[1]:
            out["no_shadda"].append((i, tokens[:i] + [t[0]] + tokens[i + 1 :]))  # رَبَّ → رَبَ
        base = t[0] if _consonant(t) and len(t) == 2 and t[0] == t[1] else t
        for o in LOOKALIKE.get(base, ()):
            new = o + o if base != t else o
            out["lookalike"].append((i, tokens[:i] + [new] + tokens[i + 1 :]))
    return out
