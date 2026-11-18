# Existing Solutions in Other Languages — Pronunciation and Reading Checkers Worldwide

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-17
**Status:** desk research at survey depth. No product was installed. Most facts come from search summaries of vendor pages and reviews; five sources were opened and read (marked [P]).
**Relation to earlier reports:** `SOLUTIONS_ARABIC.md` covers Arabic. This report looks at the same problem in other languages, to see what is done differently and what can be borrowed.

---

## 1. Summary

1. **The same three designs appear everywhere.** Products either recognise words and compare them with the text, or score each expected sound against a model of native speech, or let a general voice model talk to the learner. No fourth design was found in any language.
2. **The closest relatives of Muallim's first stage are children's reading tools, not adult language apps.** They face the same task: one letter sound, said alone, by someone who cannot read yet. The only published accuracy for it found here is 85 % agreement with human raters on letter sounds, against 95 % between two humans (2011).
3. **Vendors of children's tools say openly that isolated sounds are the hard case.** Sounds said alone lack the context that helps recognition inside words. This matches our own test, where no system exceeded 50 % on single vowelled letters.
4. **Commercial scoring services do not cover Arabic.** Speechace lists English, French and Spanish; SpeechSuper lists eight languages without Arabic. Microsoft's service lists Arabic but returned no sound labels in a 2025 report (Phase 1).
5. **Independent evidence is as thin abroad as in Arabic.** Accuracy claims are vendors' own. A 2025 systematic review of thirty studies states that such systems "still struggle to accurately evaluate" learner speech and that most research measured results with human listeners, not with the software.
6. **What is well supported is the teaching effect, not the scoring accuracy.** Meta-analyses find that computer pronunciation training helps, most of all beginners and most of all with explicit feedback on single sounds.
7. **Nobody found works the way Muallim does:** a graded textbook from single letters, checked by voice in a messenger, with teachers verifying the labels. A few hobby Telegram bots exist for English; none publishes an evaluation.

### Evidence marks

| Mark | Meaning |
|---|---|
| **[P]** | Page or paper opened and read in this session |
| **[S]** | Search summary only — check before citing |
| **[V]** | Vendor's own claim about its product |

---

## 2. Method

- Searched for products and research in four areas: adult pronunciation apps, children's reading tutors, scoring services for developers, and tools for tone languages; and for pronunciation bots in messengers.
- Opened and read: the Speechace list of supported languages, ELSA's efficacy page, the record of Black et al. (2011), the Evidence for ESSA entry for Amira, and the systematic review by Amrate and Tsai (2025).
- Everything else is known from search summaries and is marked [S]. Prices and user counts were not collected.

---

## 3. Adult pronunciation apps

| Product | Language taught | What the learner gets | How it works | Evidence |
|---|---|---|---|---|
| **ELSA Speak** | English | Score per sound, a "heat map" of mispronounced sounds, mouth-position tips | Scoring of each sound against a model of native speech; details not published | Vendor: "93.88 % agreement with expert human raters within ±1 CEFR band", no method or sample given [P][V]. Learner gains come from "internal studies" [P][V]. Small classroom studies report gains [S] |
| **BoldVoice** | American English | Score for every sound of every word, coach videos | Compares the learner with a native model; engine not disclosed | A 2025 review in *Language Learning & Technology* describes the feedback, not its accuracy [S] |
| **Duolingo** speaking exercises | Many | Each word turns blue when recognised | Word recognition: the sentence passes if its words are recognised | No published threshold or accuracy; studies ask for "clearer evaluation mechanisms and more detailed feedback" [S] |
| **Rosetta Stone** TruAccent | Many | Pass or fail per phrase; strictness adjustable | "Compares your attempts to native speakers"; no detail | User reports of both kinds: noise accepted as correct, and correct speech rejected [S] |
| **Mondly and similar** | Many | "Real-time pronunciation feedback" | Not disclosed | None found (see `SOLUTIONS_ARABIC.md`) |

Observation: the more a product tells the learner (which sound, how to fix it), the less it tells the public about how it decides.

---

## 4. Children's reading tutors

| Product | For whom | What it checks | How it works | Evidence |
|---|---|---|---|---|
| **Project LISTEN Reading Tutor** (Carnegie Mellon, 25 years of research) | Children learning to read English | Follows the child reading a story aloud and helps on hard words | Aligns the recogniser's output with the sentence text | Seven-month study, 178 pupils in grades 1–4: better reading scores than silent reading, clearest for first graders. Mostly the developers' own studies [S] |
| **Amira Learning** (successor of Project LISTEN) | Kindergarten to grade 4 | Oral reading fluency, type of each error | Word recognition tuned to children; details not published | Evidence for ESSA: rating "moderate", 2 studies, 15,602 pupils, average effect +0.15 [P]. This is the effect on reading, not the accuracy of error detection |
| **SoapBox Labs** (now part of Curriculum Associates) | Children from age two | Scores down to single sounds; tasks of blending, segmenting, isolating; a "short sounds" feature for letter sounds, ages 4–6 | A recogniser built only for children's voices | Vendor: trained on thousands of hours from 193 countries; certified for bias mitigation in 2022. No independent accuracy found [S][V] |
| **Google Read Along** | Children | Whether the words of a story are read | On the device, offline | Vendor figures only (see `SOLUTIONS_ARABIC.md`) |
| **Microsoft Reading Coach** | School pupils | Mispronounced words, five words to practise; teacher sets sensitivity | Built on Azure pronunciation scoring | 81 languages; depth per language not stated (see `SOLUTIONS_ARABIC.md`) |
| **Black et al. (2011)**, research | Children before they can read, kindergarten to grade 2, bilingual backgrounds | Whether a spoken letter name or letter sound is correct | Verification: accept or reject against the expected item, four recogniser-based methods | Agreement with human raters: 90 % for letter names, 85 % for letter sounds; humans agree with each other in 95 % [P] |
| **University of Southampton (2025)**, research | 254 pupils aged 10–11 learning French or Spanish | Fourteen symbol-to-sound correspondences read aloud | App's speech recognition scores each one | Validity figures not retrieved [S] |

Observation: this is the only area where the unit is the same as in Muallim's first stage — one letter sound, said alone. The design that works there is **verification** (is this the expected sound, yes or no), not free transcription.

---

## 5. Scoring services for developers

| Service | Languages | Finest unit | Arabic |
|---|---|---|---|
| **Speechace** | English (US, UK), French (France, Canada), Spanish (Spain, Mexico) | Word scores for all; sound lists for all; stress and intonation for English only | **No** [P] |
| **SpeechSuper** | English, Mandarin, French, German, Spanish, Japanese, Korean, Russian | Sound, word, sentence | **No** [S] |
| **Microsoft Azure Pronunciation Assessment** | Many, including Arabic locales | Sound for some languages | Listed, but no sound labels returned in a 2025 report (Phase 1) |

Observation: a team that wants sound-level checking of Arabic cannot buy it. It has to be built, which is what the Arabic research groups in Phase 1 are doing.

---

## 6. Tone languages

Mandarin is the nearest parallel to "a feature the learner's first language does not have": tones for a European learner, emphatic and pharyngeal consonants for a Russian speaker.

| Example | What it does | Evidence |
|---|---|---|
| **Putonghua Proficiency Test** (state exam in China) | Machine scoring of the read-aloud parts: single syllables, words, a passage. The free-talk part still needs human raters | "Machine scoring is very close to manual scoring" for the first three parts [S]. One study raised the correlation with human scores from 0.64 to 0.82 by scoring only the best sentences [S] |
| Earlier single-syllable scoring research | Posterior-probability scoring of each syllable with thresholds | [S] |
| Apps: TonePerfect, MandaTone, YuYin, CPAIT, ToneDetector | Score tone, initial and final of each syllable; draw the learner's pitch curve beside the model's | App-store descriptions only. One is built on Azure and "may score regional accents harshly" [S] |

Observation: here the unit is also tiny — one syllable — and the systems that reached exam use are verification systems with thresholds, working on read-aloud text. Free speech is still scored by people.

---

## 7. Messengers

| Example | What it is | Evidence |
|---|---|---|
| "Thought" | Hobby Telegram bot for English pronunciation, built on recent recognition models | Developer's blog [S] |
| "Falabola" | Speaking tutor in Telegram, text or speech chat | Conference slides [S] |
| "Pronuncibot" (2022 paper) | Telegram bot that gives pronunciation information from an online dictionary; does not score speech | [S] |

No messenger bot was found that checks reading sound by sound, that teaches a script from zero, or that publishes how accurate it is.

---

## 8. What research says about whether such tools help

| Source | Finding |
|---|---|
| Amrate and Tsai, *ReCALL* 37(1), 2025 — systematic review of 30 studies from 1999–2022 [P] | Most studies teach adult learners of English. Practice is mostly listen-and-repeat and reading aloud. Results were mostly measured by human listeners. The review states that systems "still struggle to accurately evaluate" learner speech. The word "Arabic" does not occur in the article |
| Mahdi and Al Khateeb (2019), meta-analysis of 20 studies, cited in the review [P] | Such training is effective, "particularly" for beginner and intermediate learners |
| Ngo, Chen and Lai (2024), meta-analysis of 15 studies, cited in the review [P] | Recognition-based training improves single sounds more than stress and intonation; explicit feedback is the most effective |

Meaning for Muallim: the learners (beginners), the target (single sounds) and the feedback style (explicit: what was expected, what was heard) are the combination for which the literature reports the largest benefit.

---

## 9. What can be borrowed

| Idea | Seen in | Use for Muallim |
|---|---|---|
| Verification instead of transcription for tiny units | Black et al., Putonghua test, SoapBox "short sounds" | Stage I: ask "is this the expected letter and vowel", not "what was said" |
| A recogniser tuned to the actual speakers | SoapBox (children only), Amira | Our data must come from our learners; a model trained on reciters is the wrong population |
| Report the ceiling: agreement between two humans | Black et al. (95 %) | Publish teacher–teacher agreement beside system–teacher agreement; the project already computes it |
| Teacher-adjustable strictness | Microsoft Reading Coach, Rosetta Stone | A strictness setting per group or learner |
| Show the learner the curve or picture, not only a verdict | Tone apps, ELSA | Already present in part: syllable cells, mouth videos |
| Score only the best of several attempts | Putonghua study | Compare the learner's best take of an item, not every take, in progress reports |
| Keep free speech for humans | Putonghua test | Do not try to grade connected recitation automatically at this stage |

## 10. What not to borrow

- A single pass-or-fail without saying what was wrong (Rosetta Stone, Duolingo): users cannot tell 60 % from 95 %.
- Accuracy stated as one headline figure without method (ELSA).
- Word recognition as proof of pronunciation (Duolingo).

---

## 11. Limitations

- Survey depth: most entries rest on search summaries, not on the vendors' pages themselves.
- No product was tried. Chinese-language sources on the Putonghua test and on the large Chinese vendors were not searched.
- Prices, user numbers and market size were not collected.
- Japanese, Korean and Indian-language tools were not examined separately.
- The list of children's tools is English-centred.

---

## Sources

**Opened and read**
- Speechace API documentation, supported languages — https://api-docs.speechace.com/getting-started/supported-languages
- ELSA, efficacy page — https://elsaspeak.com/en/efficacy
- Black M. P., Kazemzadeh A., Tepperman J., Narayanan S. S. Automatically assessing the ABCs: Verification of children's spoken letter-names and letter-sounds. ACM Transactions on Speech and Language Processing 7(4), 2011, 1–17 — https://researchonline.stthomas.edu/esploro/outputs/journalArticle/Automatically-assessing-the-ABCs-Verification-of/991015166250703691
- Evidence for ESSA, Amira — https://www.evidenceforessa.org/?p=665
- Amrate M., Tsai P. Computer-assisted pronunciation training: A systematic review. ReCALL 37(1), 2025, 22–42. DOI 10.1017/S0958344024000181

**Known from search summaries**
- Project LISTEN — https://en.wikipedia.org/wiki/Project_LISTEN
- Curriculum Associates acquires SoapBox Labs — https://thejournal.com/Articles/2023/12/05/Curriculum-Associates-Acquires-SoapBox-Labs-Gains-AI-Speech-Recognition-Tech.aspx ; SoapBox early literacy — https://soapboxlabs.com/early-literacy
- University of Southampton study of symbol–sound scoring — https://eprints.soton.ac.uk/505369
- SpeechSuper — https://github.com/speechsuper/SpeechSuper-API-Samples
- Putonghua Proficiency Test — https://en.wikipedia.org/wiki/Putonghua_Proficiency_Test ; automatic scoring study — https://www.ldc.upenn.edu/sites/www.ldc.upenn.edu/files/sighan2015-automatic-scoring-Mandarin-proficiency.pdf
- BoldVoice — https://boldvoice.com/frequently-asked-questions/
- Duolingo and Amazon Polly — https://aws.amazon.com/blogs/machine-learning/powering-language-learning-on-duolingo-with-amazon-polly/
- Rosetta Stone reviews — https://www.mezzoguild.com/rosetta-stone-review
- Telegram bots — https://dev.to/cursedknowledge/meet-thought-your-personal-ai-pronunciation-coach-in-telegram-3bhl
- YuYin — https://chatgate.ai/post/yuyin
