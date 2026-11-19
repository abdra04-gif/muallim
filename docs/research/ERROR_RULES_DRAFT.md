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
| `drop_sukun_letter` | does not read a letter with sukun | نَسْتَعِينُ → نَتَعِينُ | `sound_missing` |
| `read_merged` | reads the first of two merging letters (idgham) instead of doubling the second | قَد تَّبَيَّنَ read as «qad tabayyana» | `extra_sound` |
| `sun_lam` / `moon_lam` | reads the lam of the article before a sun letter / drops it before a moon letter | ٱلشَّمْسُ read with «l»; ٱلْقَمَرُ read without it | `extra_sound` / `sound_missing` |
| `other_syllable` | says a different syllable altogether (not a look-alike) | بَ → زُ | `letter_substitution` |

Measured with MostafaMaroof on correct readers (PHASE_3 §11.8g–11.8h): `vowel_on_sukun` with any of the three vowels 97.9–99.5 %, `drop_sukun_letter` 97.3 %, `other_syllable` as a rival closes the hole where 18 of 100 wrong syllables passed. Not measured yet: `read_merged`, `sun_lam` / `moon_lam`, `no_tanwin`, `read_silent` — the converter exists (`to_maroof.py`); they need recordings of the lesson lines.

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
| 49–51 · two neighbouring letters, the first with sukun (merge or clear) | قَدْ تَبَيَّنَ · قَد تَّبَيَّنَ | + `vowel_on_sukun`, `drop_sukun_letter`, `read_merged`; partial merge (أَحَطتُ — ط keeps its heaviness) — teacher only |
| 52 · sukun inside words | نَسْتَعِينُ | + `vowel_on_sukun`, `drop_sukun_letter` |
| 53 · the article, sun and moon letters | ٱلشَّمْسُ · ٱلْقَمَرُ | + `sun_lam`, `moon_lam` |
| 54–55 · mim with sukun | وَلَكُم مَّا | as 49–52; ghunna — teacher only |
| any · qalqala letter (ق ط ب ج د) with sukun at the end | لَمْ يَلِدْ | `vowel_on_sukun` only as a soft hint: the correct echo can sound like a fatha (89.5 %, §11.8h) |
| any · the last word at a stop | — | both readings correct: with the final vowel and without it |
| 3–30 · the last syllable of a card of several syllables | رَ رِ رُ | **clear vowel** (approved by the author, ADR-0087 point 9): the right vowel heard — passed; another vowel clearly heard — error; a vowel hardly heard — «say it again, hold the last vowel» (PHASE_3 §11.8i) |
| 2 · alphabet | ا ب ت … | not checked by voice — the book teaches sounds, not names (ADR-0087 point 10) |
| 56–70 · nun and tanwin (izhar, idgham, ikhfa, iqlab), qalqala | مَنْ ءَامَنَ | the same rules; tajwid-specific errors (missing ghunna, idgham) — **not proposed yet**: they need length and nasality, which the current model does not measure (PHASE_3 §11.8b) |
| 71–96 · small letters, silent letters, stops, kinds of madd | — | as above; kinds of madd (2, 4, 6 counts) need length measurement — later |
| 97–125 · suras | lines | all rules taught so far |

## Decisions for the author

1. Approve or change the list of rules and the table of lessons.
2. Whether a held vowel on a single syllable is never an error (proposed: never).
3. Whether to judge tajwid rules (ghunna, idgham, qalqala, lengths of madd) automatically at all in
   this version, or leave them to the teacher.
