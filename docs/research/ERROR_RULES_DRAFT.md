# Typical beginner errors per stage of the book — DRAFT for the author

Status: **draft, not approved.** Which errors the bot looks for on which cards is a methodology
decision of the author (CLAUDE.md, «Только человек»). The agent proposes; examples come from
`curriculum/course.ru.yaml`. Code: `docs/research/phase3/error_rules.py`; test on phrases:
`docs/research/phase3/words_check.py` (PHASE_3 §11.8d).

## Principle

The bot checks a card by comparing the correct reading with a short list of **typical errors**
for that card and choosing which one the recording is closest to (“card variants”, PHASE_3 §11.8c).
Following HAFSS (Abdou et al. 2006, SRC-164), the list holds **only errors of what has already been
taught** — fewer variants, fewer false alarms for a beginner.

## Error rules

| Rule | What the learner does | Example (expected → error) | Bot error kind today |
|---|---|---|---|
| `vowel` | another short vowel | كَتَبَ → كَتِبَ | `vowel_substitution` |
| `lookalike` | a look-alike consonant (pairs as in the letter tests) | صَبَرَ → سَبَرَ | `letter_substitution` |
| `vowel_on_sukun` | adds a vowel where there is sukun | قَدْ → قَدَ | `extra_sound` |
| `no_vowel` | drops a vowel (reads as if sukun) | بَ → بْ | `vowel_missing` |
| `no_shadda` | does not double a shadda letter | رَبَّ → رَبَ | `shadda_missing` |
| `short_madd` | shortens a long vowel | كَلَامُ → كَلَمُ | `madd_too_short` |
| `added_length` | lengthens a short vowel | كَتَبَ → كَاتَبَ | `madd_too_long` |
| `no_tanwin` | drops the n of tanwin | بًا → بَا | `sound_missing` |
| `read_silent` | pronounces a letter that is not read (hamzat al-wasl in joining, silent alif) | ٱلْقَمَرُ → أَلْقَمَرُ in the middle of speech | `extra_sound` |

`no_vowel` is tested on single syllables (`variants_check.py`), not yet on phrases. `no_tanwin` and `read_silent` are not in the code yet: they need word boundaries and the rules of
joining; the current symbols come from a phonemiser that already applied them.

## Which rules on which lessons (proposal)

| Lessons | Cards | Rules |
|---|---|---|
| 3–30 · letters and short vowels | single syllables (84) | `vowel`, `lookalike`, `no_vowel`; length **not** judged (a held vowel is normal) |
| 31–37 · madd | كَلَامُ | + `short_madd`; `added_length` only inside words |
| 38–41 · tashdid | رَبَّ | + `no_shadda` |
| 42–44 · tanwin | بًا بٍ بٌ | + `no_tanwin` |
| 45–48 · hamza, hamzat al-wasl, ta marbuta | ٱلْ… | + `read_silent` |
| 49–55 · sukun, the article, mim with sukun | قَدْ تَبَيَّنَ | + `vowel_on_sukun` |
| 56–70 · nun and tanwin (izhar, idgham, ikhfa, iqlab), qalqala | مَنْ ءَامَنَ | the same rules; tajwid-specific errors (missing ghunna, idgham) — **not proposed yet**: they need length and nasality, which the current model does not measure (PHASE_3 §11.8b) |
| 71–96 · small letters, silent letters, stops, kinds of madd | — | as above; kinds of madd (2, 4, 6 counts) need length measurement — later |
| 97–125 · suras | lines | all rules taught so far |

## Decisions for the author

1. Approve or change the list of rules and the table of lessons.
2. Whether a held vowel on a single syllable is never an error (proposed: never).
3. Whether to judge tajwid rules (ghunna, idgham, qalqala, lengths of madd) automatically at all in
   this version, or leave them to the teacher.
