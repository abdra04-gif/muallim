# Phase 2 — Existing Datasets and Scientific Research

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-16
**Status:** desk research only. No dataset was downloaded or opened; facts come from papers, catalogue pages and dataset cards.
**Builds on:** `PHASE_1_ASR_RESEARCH.md`.
**Revision 2 (2026-11-16):** critical analysis added (section 5a: strengths and weaknesses of every dataset, design references, observations, proposals). The L2-KSU paper was tried again by three routes and is still unreadable without a publisher login.
**Next:** Phase 3 (install and test models) — waiting for approval.

---

## 1. Summary

1. **No existing dataset matches Muallim's learners and material.** Nothing found combines adult beginners from zero, single letters and syllables with vowel signs, real errors, and sound-level labels.
2. **L2-KSU can support our research as an external test, not as training data.** It has 40 non-native speakers with phone-level labels, but they are African students already studying Arabic, reading ten full sentences. Its licence forbids derivative works. It is the best available check that a model catches real non-native consonant errors.
3. **Russian- and Kazakh-speaking learners are not absent from existing data.** The RetaSy dataset (about 7,000 recordings, 1,287 participants) lists Russia, Kazakhstan and Uzbekistan among its countries. It has only a verse-level "correct / has mistakes" label, and only 1,166 recordings are labelled. Its authors overlap with the authors of sources the project attributes to the supervisor's group, so fuller access may be possible.
4. **A public letter-level dataset from non-Arab learners exists.** `Reinjin/Pelafalan_Huruf_Hijaiyah`: 8,904 clips, 84 classes (28 letters × 3 vowel signs), Indonesian boarding-school students, open licence. It is the same material as Stage I of Muallim. It has no error labels and almost no documentation.
5. **The field's benchmarks are small.** The main Arabic error test set has 1,643 utterances; the main learner-recitation benchmark has 159 recordings. A Muallim dataset of 20–40 learners and a few thousand attempts would be of comparable size.
6. **Errors in the main benchmarks are not learner errors.** IQRA's test sets use native speakers who mispronounce on instruction, or synthetic speech.
7. **Muallim's contribution** would be the first open dataset that follows the same beginners through a graded textbook, from single letters to words, with teacher-verified sound-level error labels (section 7).

### Evidence marks

| Mark | Meaning |
|---|---|
| **[P]** | Read in a primary source during this session (paper, catalogue page, dataset card) |
| **[R]** | From the project's earlier reading (`docs/research/sources.md`, key `SRC-NNN`; `annotation-formats.md`) |
| **[S]** | Secondary source only (search summary) — check before citing |
| **[?]** | From general knowledge, not checked in this session |

---

## 2. What Muallim needs from a dataset

| Criterion | Target |
|---|---|
| Speakers | Adults learning to read Arabic from zero; first language Russian or Kazakh |
| Material | One letter with a vowel sign → syllable → word → line, in textbook order |
| Errors | Real, as they occur; both correct and incorrect attempts |
| Labels | Which sound was expected, which was produced, verified by a teacher |
| Recording | Phone microphone, home conditions (Telegram voice messages) |
| Rights | Usable for evaluation; ideally also for training and redistribution |

---

## 3. Datasets found

### 3.1 Non-native and learner speech

| Dataset | Speakers | Material | Size | Labels | Access and licence | Evidence |
|---|---|---|---|---|---|---|
| **L2-KSU** (King Saud University, recorded 2022) | 80: 40 native (Saudi Arabia, Egypt, Palestine), 40 non-native (Central and West African students of KSU's Arabic Linguistics Institute) | 10 MSA sentences, each repeated several times | ≈6 h; 4,094 audio files; 818 utterances in the annotation table | Phone-level (Praat TextGrid); table with text, canonical and actual phones | Hugging Face `IWAN/L2-KSU-Dataset`, gated, **CC BY-NC-ND 4.0**; also LDC2024S11 under a non-commercial research agreement, fee not shown | [P] LDC catalogue, HF card |
| **L2AraSpeech** (2026, *Language Resources & Evaluation*) | 220 non-native speakers, varied countries and first languages | Not read | Not read | Errors annotated by expert linguists | Said to be on IEEE DataPort for non-commercial use; listing not found | [S] |
| **Arabic-CAPT** (King Saud University) | 62 non-native speakers, 20 nationalities | Adapted from the KSU speech database | 2.36 h; 1,611 utterances | Phone-level, following L2-ARCTIC guidelines | Download location not found; one table lists it as not public | [S] |
| **AraVoiceL2** | 11 non-native speakers (Turkish, Nigerian, Bangladeshi, Indonesian, Malaysian backgrounds) | Fixed list of 642 words and short sentences | 5.5 h; 7,062 recordings | Character level including vowel signs | Terms not found | [S] |
| **RetaSy Quranic Audio Dataset** (2024) | 1,287 participants from 11+ non-Arabic countries, **including Russia, Kazakhstan and Uzbekistan**; 47 % female | Short surahs, Ayat al-Kursi, adhan, prayers (≈25 items); al-Fatiha is 2,934 recordings | ≈7,000 recordings, 11.5 h; 6,828 on Hugging Face | One label per recording: correct / incorrect / four "invalid" types. **Only 1,166 labelled.** Crowd annotators, 3 judgments each, agreement α = 0.63 | Hugging Face `RetaSy/quranic_audio_dataset`, not gated, **no licence stated**; consent procedure not described | [P] arXiv:2405.02675, HF card |
| **QDAT / `obadx/qdat_bench`** | Amateur reciters; 120 women, 39 men in the benchmark; age given | One verse (5:109) | QDAT ≈1,500 recordings; benchmark 159 | Lengths of prolongation, nasalisation, qalqalah; phonetic transcript and 10 articulation attributes per sound; one annotator | Apache-2.0, not gated | [R] SRC-155, SRC-002; [P] HF card |
| `sobolev210/quran-recitation-errors` | Not described; 137 recordings | Verses from 38 surahs; two reading traditions | 1,042 rows | Per word: Wording / Tajweed / Tashkeel error; 5 reviewers; many rows "not reviewed" | MIT, not gated; no paper | [P] HF card |
| `MON3EMPASHA/arabic_mispronunciation_dataset` | Not described | Single common words | 4,842 clips | Binary 0/1, meaning not defined | No licence, no documentation | [P] HF card |
| Quran Lab learner test sets | Real students corrected by teachers | Quran recitation | Not published | Word-level | Private by design | [P] model card |

### 3.2 Single letters and syllables

| Dataset | Speakers | Material | Size | Labels | Access and licence | Evidence |
|---|---|---|---|---|---|---|
| **`Reinjin/Pelafalan_Huruf_Hijaiyah`** | Students of an Indonesian Islamic boarding school; age, gender, level not stated | 28 letters × fatha / kasra / damma = **84 classes** | 8,904 clips, 0.45–2.4 s, 238 MB | Class only (which letter and vowel). No "correct / incorrect" label | Hugging Face, not gated, AFL-3.0; made for an undergraduate thesis; no paper | [P] HF card |
| **Horouf** (2025) | Native and non-native, varied age and gender; no counts | 28 letters × 4 marks = 112 classes | ≈10,000 clips, 11 % rejected in expert review | Class; expert review | On request from the authors; no licence | [P] arXiv:2508.19587 |
| Telkom "Marked Hijaiyah Letters' Pronunciation Dataset" (2021) | 3 men, 3 women | 28 letters with vowel marks, 168 classes | Not read | Class | University data repository; terms not read | [S] |
| `HamzaSidhu786/arabic-alphabet-speech-classification` | Not stated | 28 letters, no vowel signs | 22.2k rows | Class | No licence, no documentation; stored as pre-processed arrays, not audio files | [P] HF card |

### 3.3 Error benchmarks recorded by native speakers

| Dataset | Speakers | Material | Size | Labels | Access and licence | Evidence |
|---|---|---|---|---|---|---|
| **QuranMB.v2** (IQRA 2026 test) | Native speakers producing errors on instruction (18 speakers in v1) | Quran verses | 1,643 utterances, ≈2.5 h | Phoneme sequences validated by three linguists | `IqraEval/QuranMB.v2`, not gated, CC BY-NC 4.0 | [P] arXiv:2603.29087, HF card; speakers [R] |
| **Iqra_Extra_IS26** | Native speakers instructed to make given substitutions | MSA / Quran | 1,333 utterances, ≈1.5 h | Phonemes | Gated, CC BY-NC 4.0 | [P] |
| Iqra_TTS | 7 synthetic voices | — | 55,400 utterances, ≈52 h | Errors injected by rule | — | [P] |
| Iqra_train | Common Voice Arabic + Quran segments, correct speech | Sentences | 73,979 utterances, ≈79 h | Vowelled text, reference phonemes, "augmented" phonemes | Not gated, CC BY-NC 4.0 | [P] HF card |

### 3.4 Correct speech (training material and references)

| Dataset | What it is | Size | Licence | Evidence |
|---|---|---|---|---|
| `obadx/muaalem-annotated-v3` | 22 professional male reciters; phonemes and attributes generated by program | 286,537 segments, 848 h | MIT | [R] |
| EveryAyah (`tarteel-ai/everyayah`) | Professional reciters, verse by verse | 392 h used by NVIDIA | Reported as MIT in one source and CC-BY-4.0 in another; the dataset page itself carries no licence tag | [P] conflicting |
| `Buraaq/quran-md-words` | **Single words** cut from recitation, with Latin transliteration | 77,429 clips, ≈20 h | Not stated | [P] HF card |
| `Quran-Lab/quran-tajweed-benchmark` | 22 professional reciters held out from training; only 3 recordings by women, none by children | 3,910 recordings, 9.2 h | NPL-1.2 | [P] |
| `tarteel-ai/tlog` | Real phone recordings of app users, noisy labels | ≈27,000 clips used by one model | Gated | [P] via model card |
| Common Voice Arabic | Volunteers reading sentences, no vowel signs | 82 h used by IqraEval | CC0 | [R], [P] |

### 3.5 Children

| Dataset | Speakers | Size | Access | Evidence |
|---|---|---|---|---|
| Fanoush et al., 2025 | Native Saudi children, 8–11 | ≈60 min annotated | Not confirmed | [R] SRC-162 |
| Arabic Speech Mispronunciation Detection Dataset (ASMDD) | 27 Egyptian children | Word level | Not checked | [S] |

---

## 4. L2-KSU in detail

| Aspect | Finding |
|---|---|
| Who speaks | 40 non-native students from Central and West Africa enrolled in an Arabic language institute; 40 native speakers. First languages not listed. |
| Level | Not stated. Institute students read full sentences, so they are not beginners from zero. |
| What is read | Ten MSA sentences, repeated. No single letters, syllables or isolated words. |
| Labels | Phone-level alignments in Praat format; a table giving text, canonical phones and produced phones. |
| Recording | 16 kHz WAV. Non-native speakers recorded on site; native speakers sent recordings through a crowdsourcing platform. |
| Published results | Alrashoudi et al.: PER 3.1 %, detection 91.3 %, diagnosis 80.8 %. Quran Lab TajweedFormer V4: 46 % of 1,598 consonant errors caught at 2.1 % false flags. |
| Rights | CC BY-NC-ND 4.0 on Hugging Face; non-commercial research agreement at LDC. |
| Problems | 4,094 audio files but 818 annotated utterances — the relation is not explained. No official train/test split (the original two files were identical). The paper itself was not readable in this session. |

**Can it support our research?**

- **Yes, as an external test set.** It is the only obtainable corpus with sound-level labels on real non-native adult speech, and two published results exist to compare against.
- **No, as training data for our learners.** Different first languages, different level, sentences instead of letters, and ten prompts only.
- **Legal caution.** "No derivatives" may cover a model fine-tuned on the data and forbids sharing a modified copy. Use for evaluation is the safe reading; training on it needs the author's decision.

---

## 5. How existing datasets label errors

| Scheme | Used by | Unit | What is recorded |
|---|---|---|---|
| Expected vs produced phone sequence | L2-KSU, IqraEval, Arabic-CAPT (after L2-ARCTIC) | Sound | Canonical phones and annotated phones; substitution, deletion, insertion follow from comparing them |
| Category per word | `sobolev210` | Word | Wording / Tajweed / Tashkeel |
| Verdict per recording | RetaSy | Recording | Correct, incorrect, or one of four "invalid audio" types |
| Graded rule measurements | qdat_bench | Rule occurrence | Length in counts, full or partial nasalisation, attribute values |
| Class only | Letter datasets | Clip | Which letter and vowel was intended |

Observations for Phase 4:

- The expected-vs-produced scheme is the standard and the project's export already follows it. [R]
- RetaSy shows that "invalid audio" categories are needed in crowd-collected data: 25 % of its labelled recordings were empty, the wrong verse, several verses, or incomplete.
- Agreement is rarely reported. RetaSy reports α = 0.63 with three judges; qdat_bench has one annotator; most Hugging Face sets report nothing.
- No dataset records the same learner over time, and none records the system's answer next to the teacher's.

---

## 5a. Critical analysis (revision 2)

### Strengths and weaknesses of each dataset

Sources for every row are given in section 3. "Value" is my judgement for Muallim.

| Dataset | Strong | Weak | Value for Muallim |
|---|---|---|---|
| **L2-KSU** | Real non-native adults; labels per sound in a standard phonetics format; native control group of equal size; listed in a professional catalogue (LDC); two published results to compare with | Ten sentences only; speakers already study Arabic; first languages not listed; no agreement figures on the dataset page; 4,094 files against 818 labelled rows unexplained; no official split; no-derivatives licence | **High as test set**, none as training data |
| **RetaSy** | Largest learner pool (1,287 people); includes Russia, Kazakhstan, Uzbekistan; collected on phones in real conditions; reports annotator training, agreement (α = 0.63) and expert check; keeps invalid recordings with a reason | One verdict per recording, no sound labels; only 1,166 of ≈7,000 labelled; no licence; no consent procedure described; participants recite memorised prayers, they do not learn to read; age known for 93 people | **High for a first look at our population**, low for error detection |
| **`Reinjin` letters** | Exactly Stage I material (28 letters × 3 vowels); non-Arab learners; 8,904 clips; open licence; loads directly | A student thesis project with no paper; speakers, device and selection undocumented; no "wrong" examples marked; one school, so probably one accent and one teacher's style | **High for Stage I experiments**, quality unknown until opened |
| **Horouf** | Vowelled single letters from native and non-native speakers; expert review rejected 11 % of clips; published baseline results | Not downloadable; no licence; no speaker counts; the paper's own figures are inconsistent | Medium, if the authors share it |
| **QuranMB.v2 / Iqra_Extra_IS26** | The field's shared yardstick; three linguists validated the labels; 19 teams' results to compare with | Errors produced on instruction by native speakers; dataset pages have empty descriptions; non-commercial | **Medium: comparability**, not realism |
| **`qdat_bench`** | Real amateur readers; women are the majority (120 of 159); age recorded; graded labels (length, partial nasalisation) and ten attributes per sound; Apache-2.0 | One verse; one annotator; 159 recordings | Medium: the only open learner set with fine labels |
| **`sobolev210` errors** | Word-level error categories; reviewer codes; MIT | No description of speakers or method; many rows unreviewed | Low |
| **`MON3EMPASHA`** | Single words with a binary label | Label meaning undefined; no documentation, no licence | Not usable as is |
| **L2AraSpeech** | 220 non-native speakers — the largest claimed; expert linguists; peer-reviewed journal | Not located; details unread | Unknown — worth pursuing |
| **Arabic-CAPT, AraVoiceL2** | Sound- or character-level labels on non-native speech | Small (62 and 11 speakers); no download found | Low unless obtained |
| **Correct-recitation sets** (Muaalem training set, EveryAyah, quran-md-words, Quran Lab benchmark) | Large; clean; several are open | Professional adult male voices; no errors; verse or word level | Background only |

### Design references outside Arabic (verified in revision 2)

| Dataset | Facts | What it shows |
|---|---|---|
| **speechocean762** (English) | 5,000 utterances, 250 non-native speakers, half of them children; **five experts scored every utterance**; scores at sentence, word and sound level; free for commercial and non-commercial use | A benchmark of 5,000 utterances became the field's standard because of annotation depth and an open licence, not size |
| **L2-ARCTIC** (English) | 24 speakers, six first languages, two men and two women each; about 1,132 utterances per speaker, of which about 150 are hand-annotated; substitution, deletion and addition tags in Praat files; CC BY-NC 4.0 | Balanced design by first language and gender; annotating a carefully chosen subset is accepted practice |

Sources: arXiv:2104.01378; https://psi.engr.tamu.edu/l2-arctic-corpus/ [P].

### What I noticed

1. **Documentation is the weakest part of this field.** Of eleven Arabic learner or error datasets, three have an empty description page and four give no licence. A well-documented dataset of modest size would stand out.
2. **Agreement between annotators is almost never reported.** Only RetaSy gives a figure. qdat_bench, behind many published numbers, has a single annotator.
3. **"Non-native" hides very different people.** L2-KSU's institute students, RetaSy's worshippers reciting from memory and Indonesian boarding-school pupils are all "non-native", and none is an adult opening an Arabic primer for the first time.
4. **The standard benchmark does not contain learner errors at all**, and its organisers say so.
5. **Every useful learner set is restricted in some way:** no derivatives (L2-KSU), no licence (RetaSy), non-commercial (IqraEval), on request (Horouf), private (Quran Lab).
6. **Consent is not described anywhere.** No dataset page or paper read in this phase explains what participants agreed to. For RetaSy this is notable, since it contains voices of identifiable countries and ages.
7. **Counts do not always add up.** L2-KSU: 4,094 files, 818 rows. RetaSy: "about 7,000" in the paper, 6,828 on the hub, 1,166 labelled, 1,427 "with annotations".
8. **Women and children are scarce in correct-recitation data but not in learner data** (qdat_bench is 75 % women, RetaSy 47 %). Models trained on the former are tested on the latter.

### Proposals for Muallim's dataset

**Strengthen**

- Make documentation and agreement reporting the dataset's selling point: full datasheet, annotator description, α per error type. This is cheap and rare (observations 1–2).
- Use a permissive licence if consent allows. speechocean762's free licence is a main reason it is used everywhere.
- Describe the consent procedure in the dataset card. No comparable dataset does (observation 6).
- Balance recruitment by first language and gender as far as the pilot allows, following L2-ARCTIC.

**Add**

- A small **native or expert control group** reading the same items, as L2-KSU has. It shows what "correct" sounds like on our material and in our recording conditions, and it gives reference recordings.
- **Invalid-recording categories** kept in the data (RetaSy found 25 % invalid).
- Optionally, a **teacher's overall score** per attempt on a short scale, as in speechocean762. It is fast to give and allows comparison with scoring systems. This is a methodology decision for the author.
- A statement of **exact counts** at every stage — recorded, consented, labelled, agreed — to avoid the mismatches seen above.

**Remove from the plan or avoid**

- Do not use staged errors or synthetic speech in the test set. They may be used for training only, and labelled as such.
- Do not rely on a single annotator for any published figure.
- Do not train on L2-KSU while its licence forbids derivatives, unless the author and supervisor decide otherwise.
- Do not claim "first dataset of non-Arab learners": RetaSy, L2-KSU, L2AraSpeech and the Indonesian letter set exist. The defensible claim is in section 7.

### RetaSy by country (revision 3, 2026-11-17)

Counted from the dataset's published column statistics on Hugging Face (6,828 recordings). [P]

| Country | Recordings | | Country | Recordings |
|---|---|---|---|---|
| Germany | 1,665 | | Uzbekistan | 70 |
| United States | 738 | | Kyrgyzstan | 48 |
| United Kingdom | 494 | | Ukraine | 16 |
| **Russia** | **492** | | Tajikistan | 9 |
| **Kazakhstan** | **299** | | Belarus | 4 |

- Russia, Kazakhstan, Uzbekistan, Kyrgyzstan, Tajikistan, Ukraine and Belarus together: **938 recordings**, about 14 % of the dataset. Country is where the app was used, not the speaker's first language.
- Labels in the whole dataset: correct 409, incorrect 502, wrong verse 56, several verses 83, incomplete 25, not Quran or empty 153 — 1,228 labelled; the other 5,600 have no label. How many of the 938 are labelled is not visible without downloading.
- Age is unknown for 5,377 recordings; 279 are marked under 18.
- Gender: 2,928 female, 2,939 male.

This answers open question 1 in part: the data exists in useful quantity; its labels and licence still need the authors.

---

## 6. Research gaps

| Gap | Evidence |
|---|---|
| No sound-level labelled data from beginners who start from zero | All learner sets are either institute students (L2-KSU, Arabic-CAPT), people who already recite (RetaSy, QDAT), or unlabelled for errors (letter sets) |
| No sound-level labels for Russian- or Kazakh-speaking learners | RetaSy includes these countries but has verse-level labels only; per-country counts are not published |
| Letter-level data has no error labels | Reinjin, Horouf, Telkom record the intended class only |
| No graded progression | Each dataset covers one unit type: letters, or sentences, or verses |
| No longitudinal data | No dataset follows the same learner across lessons or repeated attempts |
| Benchmark errors are staged or synthetic | QuranMB, Iqra_Extra, Iqra_TTS; the IQRA organisers name learner data as future work |
| Women and children under-represented in correct-recitation data | Muaalem: male reciters only; Quran Lab benchmark: 3 recordings by women |
| Rights are restrictive or undefined | Non-commercial (IqraEval), no-derivatives (L2-KSU), no licence at all (RetaSy, quran-md-words), on request (Horouf) |
| Consent for publication is rarely documented | RetaSy paper describes no consent procedure |

---

## 7. What Muallim could contribute

A dataset of the bot's attempts would be, to our knowledge from this search, the first that offers all of the following together:

| Property | Why it is new |
|---|---|
| Adult beginners from zero, first language Russian or Kazakh | Not covered at sound level by any dataset found |
| Graded material from one vowelled letter to words, in textbook order | Existing sets hold one unit type each |
| Real errors with the expected and the produced sound, verified by teachers, with agreement reported | Letter sets have no error labels; RetaSy has no sound-level labels |
| The same learner over many lessons and repeated attempts | No longitudinal Arabic learner speech found; allows learning curves and self-correction analysis |
| The system's answer stored next to the teacher's label | Allows direct measurement of false alarms and misses for any model |
| Phone recordings in home conditions | Matches real use; studio data dominates elsewhere |
| Documented consent and a clear public licence | Rare in this field |

Scale for comparison: QuranMB.v2 has 1,643 utterances, Iqra_Extra_IS26 has 1,333, qdat_bench has 159, L2-KSU has 818 annotated utterances from 80 speakers. L2-ARCTIC, the standard English benchmark, has 24 speakers; speechocean762 has 5,000 utterances from 250 speakers (section 5a). [P] A pilot with 20–40 learners and several thousand attempts is therefore a normal size for a benchmark in this field, though small for training.

Limits to state honestly in the thesis:

- The claim "no Russian or Kazakh learner data exists" would be false; RetaSy contains such speakers. The accurate claim is about sound-level labels and beginner material.
- A dataset from one textbook and one or two first languages will not generalise to other learner groups.
- The number of speakers, not the number of recordings, limits what can be concluded.

---

## 8. What each existing dataset can be used for

| Use | Dataset | Condition |
|---|---|---|
| External test of error detection on non-native adults | L2-KSU | Accept the access conditions with a Hugging Face account |
| Test of letter-and-vowel recognition on non-Arab learners; training a Stage I classifier | `Reinjin/Pelafalan_Huruf_Hijaiyah` | Check audio quality and class balance after download |
| Recordings from Russia, Kazakhstan, Uzbekistan for a first look at our population | RetaSy (filter by `reciter_country`) | No licence stated — ask the authors; verse-level labels only |
| Link to the public benchmark | QuranMB.v2, Iqra_Extra_IS26 | Non-commercial |
| Learner recitation with rule-level labels | `obadx/qdat_bench` | One verse, one annotator |
| Single-word correct speech | `Buraaq/quran-md-words` | No licence stated |
| Second letter-level source | Horouf | Write to the authors |
| Larger non-native corpus | L2AraSpeech | Find the listing or write to the authors |

---

## 9. Limitations of this report

- No dataset was downloaded. Audio quality, class balance, label quality and the real content of undocumented sets are unknown.
- The L2-KSU paper and the L2AraSpeech paper could not be opened (publisher login redirect). L2-KSU facts come from the LDC catalogue and the Hugging Face card; L2AraSpeech facts are secondary.
- The LDC licence text and fee could not be read.
- Search was by keyword in Hugging Face, LDC and the web. Kaggle, IEEE DataPort, ELRA and university repositories were not searched systematically.
- Datasets held privately by companies (Tarteel, Quran Lab) are known only from descriptions.
- The link between RetaSy's authors and the supervisor's group is inferred from author names in project notes, not confirmed.

---

## 10. Open questions

1. How many RetaSy recordings come from Russia, Kazakhstan and Uzbekistan, and can the authors share labels or licence terms?
2. What is the relation between L2-KSU's 4,094 audio files and its 818 annotated utterances? Which errors are most frequent?
3. Where is L2AraSpeech actually hosted, and what do its speakers read?
4. Does the Reinjin letter set contain mispronounced clips, and how many speakers does it have?
5. Will the Horouf authors share their data?
6. May a model be trained on CC BY-NC-ND data, in the author's and supervisor's view?
7. Which licence should Muallim's own dataset carry, given that most related data is non-commercial? (Phase 5.)

---

## 11. Recommendations for Phase 3

1. **Test audio that can be obtained now, in order of relevance:**
   - `Reinjin/Pelafalan_Huruf_Hijaiyah` — Stage I material from non-Arab learners;
   - RetaSy, filtered to Russia, Kazakhstan, Uzbekistan — our population, verse level;
   - L2-KSU — non-native adults with sound-level labels;
   - `obadx/qdat_bench` and QuranMB.v2 — to connect with published numbers;
   - the bot's own human reference recordings — as the "correct" side.
2. **State plainly in the Phase 3 report** that none of these is beginner speech from our learners; results are preliminary.
3. **Two actions need the author:** accepting the gated-access conditions for L2-KSU and Iqra_Extra_IS26 under a Hugging Face account, and deciding whether to write to the RetaSy, Horouf and Quran Lab authors.
4. **Disk and memory:** the sets above total a few gigabytes without Iqra_train (12.2 GB), which is not needed for testing.
5. **Use the benchmark-style score** from Phase 1 (share of attempts given exactly the right verdict) so that letter, word and verse sets can be reported in one table.

---

## Sources

**Non-native and learner speech**
- L2-KSU Native and Non-Native Arabic Speech, LDC2024S11 — https://catalog.ldc.upenn.edu/LDC2024S11
- L2-KSU on Hugging Face — https://huggingface.co/datasets/IWAN/L2-KSU-Dataset
- Alrashoudi N., Al-Khalifa H., Alotaibi Y. Improving mispronunciation detection and diagnosis for non-native learners of the Arabic language. Discover Computing 28(1), 2025. DOI 10.1007/s10791-024-09489-8 (SRC-161)
- Introducing a nonnative Arabic speech corpus for CAPT: L2AraSpeech. Language Resources & Evaluation, 2026 — https://link.springer.com/article/10.1007/s10579-026-09924-w
- Algabri et al. Mathematics 10(15), 2022 (Arabic-CAPT) — https://mdpi.com/2227-7390/10/15/2727 (SRC-160)
- El Kheir et al. Automatic Pronunciation Assessment — A Review. arXiv:2310.13974 — https://arxiv.org/abs/2310.13974 (source of the Arabic-CAPT and AraVoiceL2 descriptions)
- Salameh R., Al Mdfaa M., Askarbekuly N., Mazzara M. Quranic Audio Dataset: Crowdsourced and Labeled Recitation from Non-Arabic Speakers. arXiv:2405.02675 — https://arxiv.org/abs/2405.02675 (SRC-032); data — https://huggingface.co/datasets/RetaSy/quranic_audio_dataset
- https://huggingface.co/datasets/obadx/qdat_bench (SRC-155)
- https://huggingface.co/datasets/sobolev210/quran-recitation-errors
- https://huggingface.co/datasets/MON3EMPASHA/arabic_mispronunciation_dataset

**Letters**
- https://huggingface.co/datasets/Reinjin/Pelafalan_Huruf_Hijaiyah
- Zaatiti et al. Towards stable AI systems for Evaluating Arabic Pronunciations (Horouf). arXiv:2508.19587 (SRC-151)
- Marked Hijaiyah Letters' Pronunciation Dataset, Telkom University — https://dataverse.telkomuniversity.ac.id/dataset.xhtml?persistentId=doi:10.34820/FK2/XACWLX
- https://huggingface.co/datasets/HamzaSidhu786/arabic-alphabet-speech-classification

**Benchmarks and correct speech**
- IQRA 2026 Interspeech Challenge. arXiv:2603.29087 (SRC-031)
- https://huggingface.co/datasets/IqraEval/QuranMB.v2 · https://huggingface.co/datasets/IqraEval/Iqra_Extra_IS26 · https://huggingface.co/datasets/IqraEval/Iqra_train
- https://huggingface.co/datasets/Quran-Lab/quran-tajweed-benchmark
- Quran-MD. arXiv:2601.17880; https://huggingface.co/datasets/Buraaq/quran-md-words
- Abdelfattah et al. arXiv:2509.00094 (SRC-002)
- Fanoush et al. IEEE Access, 2025 (SRC-162)
- Zhao et al. L2-ARCTIC. Interspeech 2018 (SRC-063)
