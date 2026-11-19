# Phase 3 — Experimental Results (preliminary)

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-17
**Status:** two experiments, run in full. Step 1: five ready-made systems on 840 public recordings of single vowelled letters. Step 2 (section 11): four candidate checkers **built by us** on one model and tested on all 8,904 recordings, each clip judged by a checker that never heard its speaker. **No recording of a Muallim learner was used**, because no teacher-labelled recordings of our learners exist yet.
**Builds on:** `PHASE_1_ASR_RESEARCH.md` (shortlist, section 8), `PHASE_2_DATASET_RESEARCH.md` (letter dataset, section 3.2).

Every number in this report was produced by the scripts in `docs/research/phase3/` and can be recomputed from the CSV files in `docs/research/phase3/results/`. Nothing is estimated.

---

## 1. Summary

1. **No system recognises a single vowelled letter reliably.** The best one reports the right letter and the right vowel in 50.0 % of clips.
2. **The bot's present model (Muaalem) is not the best on this material:** 39.4 % against 50.0 % for a smaller Arabic phoneme model.
3. **Muaalem writes a long vowel in 411 of 840 clips** although every clip is one letter with a short vowel. A learner who pronounces a letter slowly would be told the vowel is too long.
4. **The confusions are phonetically close pairs** — emphatic and plain, voiced and voiceless, ث and س. These are the pairs a beginner confuses too, so the models are weakest where the bot most needs them.
5. **Text recognisers turn sounds into words.** Whisper wrote a vowel sign in 3 of 840 clips. The Quran-trained Whisper often answered with a real word instead of the letter.
6. **Speed is not a constraint** for phoneme models: about 0.2 seconds per clip on a laptop.
7. **What this test cannot say:** how well any model judges *our* learners, and how often a mismatch is the student's error rather than the model's. See section 7.
8. **Built and tested (step 2): a small classifier over the 84 letter–vowel answers is right in 88.0 % of clips from students it never heard**, against 47.2 % for free transcription by the same model. Used as the bot would use it — "was the expected item read?" — it accepts 90.5 % of the readings and wrongly accepts 5.2 % of readings where a confusable letter was said instead. Free transcription accepts only 47.2 % of the readings. Section 11.

---

## 2. What was tested

### 2.1 Question

Phase 1 found that free transcription of isolated letters is a documented weak point (35–37 % on the Horouf corpus), and Stage I of the textbook is exactly this material. The experiment checks this on recordings of non-Arab learners with the models we can run.

### 2.2 Data

| Property | Value |
|---|---|
| Dataset | `Reinjin/Pelafalan_Huruf_Hijaiyah` (Hugging Face), licence AFL-3.0 |
| Speakers | Students of an Indonesian Islamic boarding school; age, gender and level are not documented |
| Content | 28 letters × 3 vowel signs (fatha, kasra, damma) = 84 classes; 8,904 clips |
| Used | **840 clips: 10 per class.** Only first takes, evenly spaced through the file list, so the ten clips of a class come from different students |
| Clip length | 0.58–2.18 s, mean 1.10 s |
| Labels | The class the student was asked to read. **No "correct / incorrect" label** |

The file names contain students' names. The result files identify clips by class number and index only.

### 2.3 Systems

| Name in files | Model | Kind | Licence | Device used |
|---|---|---|---|---|
| `muaalem` | `obadx/muaalem-model-v3_2` | Arabic phoneme model (the bot's model), given the expected text as the bot gives it | MIT | Apple GPU (as in the bot) |
| `maroof` | `MostafaMaroof/wav2vec2-arabic-phoneme-asr` | Arabic phoneme model | Apache-2.0 | CPU |
| `espeak` | `facebook/wav2vec2-xlsr-53-espeak-cv-ft` | Language-independent phone recogniser (IPA) | Apache-2.0 | CPU |
| `tarteel` | `tarteel-ai/whisper-base-ar-quran` | Text recogniser fine-tuned on Quran, writes vowel signs | Apache-2.0 (model page) | Apple GPU |
| `whisper` | `openai/whisper-small` | General text recogniser | Apache-2.0 | Apple GPU |

All models were used as published, with greedy decoding and no adaptation. Both Whisper models were limited to 12 output tokens (section 6).

### 2.4 Measure

For each clip the script takes the first consonant in the system's output and the first vowel after it, and compares them with the class.

- **Letter right** — the first consonant is the expected letter.
- **Vowel right** — the first vowel is the expected one (a, i or u; long and short count the same).
- **Both right** — both conditions.
- **No letter found** — the output is empty or has no consonant.

WER, CER and PER were **not** computed. They need a transcription of what was actually said, and this dataset has only the intended class. With one letter per clip, "both right" is the closest meaningful measure.

For the universal phone recogniser the four emphatic letters (ص ض ط ظ) are excluded from the letter score: its inventory has no symbols for them (section 4.4).

### 2.5 Environment

| Item | Value |
|---|---|
| Computer | MacBook Air, Apple M1, 8 GB memory, macOS 15.6.1 |
| Python | 3.12.15 |
| Libraries | torch 2.14.1, transformers 4.57.6, huggingface_hub 0.36.2, numpy 2.5.4, quran_muaalem 0.2.2, quran_transcript 0.6.4 |
| Audio decoding | ffmpeg 9.0.2 to 16 kHz mono, the same way the bot decodes voice messages |

---

## 3. Results

### 3.1 Overall

| System | Clips | Letter right | Vowel right | Both right | No letter found | Seconds per clip | Compute ÷ audio |
|---|---|---|---|---|---|---|---|
| maroof | 840 | 65.7 % | 74.2 % | **50.0 %** | 1.0 % | 0.22 | 0.20 |
| espeak | 840 | 59.9 % ¹ | 65.4 % | 49.6 % ¹ | 15.6 % | 0.19 | 0.18 |
| muaalem | 840 | 50.4 % | 71.5 % | 39.4 % | 4.6 % | 0.17 | 0.16 |
| tarteel | 840 | 48.0 % | 50.5 % | 24.5 % | 0.0 % | 0.73 | 0.66 |
| whisper | 840 | 51.3 % | 0.4 % | 0.1 % | 1.0 % | 1.52 | 1.39 |

¹ Over 720 clips (24 letters).

Times are for the model call only, without audio decoding. They are not comparable across rows where the device differs (section 2.3).

### 3.2 Letter right, by letter (30 clips each)

| Letter | muaalem | maroof | espeak | tarteel | whisper |
|---|---|---|---|---|---|
| ء | 86.7 % | 90.0 % | 0.0 % | 16.7 % | 100.0 % |
| ب | 30.0 % | 80.0 % | 46.7 % | 30.0 % | 93.3 % |
| ت | 76.7 % | 60.0 % | 83.3 % | 36.7 % | 63.3 % |
| ث | 6.7 % | 13.3 % | 20.0 % | 3.3 % | 6.7 % |
| ج | 46.7 % | 50.0 % | 53.3 % | 43.3 % | 36.7 % |
| ح | 60.0 % | 76.7 % | 0.0 % | 83.3 % | 20.0 % |
| خ | 83.3 % | 83.3 % | 96.7 % | 83.3 % | 73.3 % |
| د | 30.0 % | 40.0 % | 73.3 % | 20.0 % | 76.7 % |
| ذ | 43.3 % | 73.3 % | 20.0 % | 76.7 % | 46.7 % |
| ر | 76.7 % | 83.3 % | 86.7 % | 40.0 % | 70.0 % |
| ز | 56.7 % | 90.0 % | 90.0 % | 26.7 % | 83.3 % |
| س | 60.0 % | 66.7 % | 100.0 % | 86.7 % | 70.0 % |
| ش | 56.7 % | 96.7 % | 70.0 % | 93.3 % | 96.7 % |
| ص | 66.7 % | 40.0 % | — | 43.3 % | 20.0 % |
| ض | 40.0 % | 36.7 % | — | 23.3 % | 0.0 % |
| ط | 23.3 % | 33.3 % | — | 60.0 % | 3.3 % |
| ظ | 6.7 % | 26.7 % | — | 0.0 % | 3.3 % |
| ع | 36.7 % | 76.7 % | 0.0 % | 73.3 % | 3.3 % |
| غ | 26.7 % | 53.3 % | 23.3 % | 23.3 % | 6.7 % |
| ف | 76.7 % | 96.7 % | 100.0 % | 76.7 % | 100.0 % |
| ق | 66.7 % | 43.3 % | 20.0 % | 26.7 % | 0.0 % |
| ك | 40.0 % | 80.0 % | 90.0 % | 73.3 % | 66.7 % |
| ل | 56.7 % | 86.7 % | 96.7 % | 26.7 % | 83.3 % |
| م | 66.7 % | 70.0 % | 73.3 % | 60.0 % | 76.7 % |
| ن | 50.0 % | 66.7 % | 80.0 % | 46.7 % | 63.3 % |
| ه | 16.7 % | 86.7 % | 63.3 % | 40.0 % | 46.7 % |
| و | 60.0 % | 63.3 % | 70.0 % | 63.3 % | 63.3 % |
| ي | 63.3 % | 76.7 % | 80.0 % | 66.7 % | 63.3 % |

With 30 clips per cell, one clip is 3.3 points. Differences of a few clips between systems mean nothing.

### 3.3 Vowel right, by vowel (280 clips each)

| Vowel | muaalem | maroof | espeak | tarteel | whisper |
|---|---|---|---|---|---|
| a | 94.6 % | 83.2 % | 58.6 % | 43.6 % | 0.4 % |
| i | 58.2 % | 66.1 % | 67.9 % | 56.1 % | 0.7 % |
| u | 61.8 % | 73.2 % | 69.6 % | 51.8 % | 0.0 % |

### 3.4 Most frequent wrong letters (expected → reported, count)

- **muaalem:** د→ت ×18, ع→ء ×15, ث→س ×13, ض→د ×13, ب→ت ×12, ك→ق ×11, ح→ق ×9, ن→ل ×9, ه→none ×8, س→ص ×7, ط→ق ×7, ظ→ذ ×7
- **maroof:** د→ت ×17, ض→د ×14, ص→ش ×12, ت→ط ×10, ط→ض ×10, ظ→ز ×10, ث→ف ×9, ث→س ×8, ج→د ×8, س→ص ×7, ط→ت ×6, ك→ق ×6
- **espeak:** ء→none ×29, ع→none ×20, ث→س ×18, ب→none ×13, ح→ه ×12, ذ→ز ×11, ق→ل ×10, ش→none ×9, ه→none ×9, ح→none ×8, د→ت ×8, و→none ×7
- **tarteel:** ث→س ×21, ض→ذ ×17, ظ→ذ ×16, ز→ذ ×15, ب→ف ×13, ت→ط ×13, د→ت ×12, ق→ط ×12, ه→ف ×12, ء→ف ×10, ص→س ×10, ل→ذ ×10
- **whisper:** ض→د ×21, ح→ه ×20, ع→ء ×20, ق→ء ×18, ث→س ×11, ج→د ×10, ص→س ×10, غ→ء ×10, ص→ش ×9, ي→ء ×9, ظ→ز ×8, ن→ل ×8

---

## 4. Observations

### 4.1 Muaalem (the bot's model)

- Vowel a is right in 94.6 % of clips, but i and u in about 60 %. When the vowel is wrong, the model most often wrote a: 60 of 280 clips for i and 74 of 280 for u.
- In **411 of 840 clips** the output contains a long vowel (for example `قِۦۦ`, `ءَاا`), although the class is a short one. Students hold the vowel when they say a letter alone; the model, trained on recitation, reads that as a prolongation.
- 22 clips gave an empty output.
- Its letter score (50.4 %) is below the smaller `maroof` model (65.7 %). The gap is largest on ب, ه, ع, ك, ز, ش, ل.

### 4.2 The Arabic phoneme model `maroof`

- Best overall and the fewest empty answers (1.0 %).
- Weak on ث (13.3 %) and on all four emphatic letters (26.7–40.0 %).

### 4.3 What the errors have in common

Across the three phone-level systems the same pairs recur: د→ت, ض→د, ث→س, ظ→ز or ذ, ص→س or ش. In each pair the two sounds differ by one feature (voicing, emphasis, or place of the tongue). The dataset cannot tell us which side erred: an Indonesian student may really have said س for ث. Both readings lead to the same conclusion for the bot — on these pairs a verdict from free transcription cannot be trusted.

### 4.4 The universal phone recogniser

- It never reported ء, ح or ع: glottal and pharyngeal sounds are dropped or written as `h`.
- For the emphatic letters it writes the plain counterpart: ص → `s` ×19 of 30, ض → `d` ×21, ط → `t` ×11, ظ → `z` ×17.
- So it cannot check the sounds that are specific to Arabic. It remains usable only as a second opinion on sounds that exist in many languages.

### 4.5 Text recognisers

- `whisper`: a vowel sign appears in 3 of 840 outputs. Frequent answers are words — «نعم» ×24, «لا» ×20 — and in 265 clips the output ran to ten or more characters, typically one letter repeated up to the length limit («اووووووووووو»).
- `tarteel`: vowel signs in 446 of 840 outputs. Frequent answers are a bare letter (س ×65, ف ×50) or a real word: «ذِي» ×48, «فِي» ×34, «ذُو» ×32, «طه» ×19.
- This matches Phase 1: recognisers built to output words replace an isolated sound by the nearest word.

---

## 5. What follows for Muallim

| Finding | Consequence |
|---|---|
| Free transcription gives the right letter and vowel in at most half of single-letter clips | Stage I should not rely on reading errors off the transcription. Test verification instead: a closed-set classifier over the 84 answers, comparison with the teacher's recording, and scoring the expected sound against its alternatives |
| Muaalem reports a long vowel in half of the clips | Check how the bot treats prolongation on single-letter items; a held vowel must not be reported as an error there. This touches the method, so it is a decision for the author |
| Muaalem is not the strongest model on letters | Keep the recogniser replaceable and compare several on the same recordings, as proposed in Phase 5 |
| Confusable pairs are the weak spot of every model | These pairs need teacher labels first; they are also where a "not sure" answer is most justified |
| The letter dataset is usable | Its remaining 8,064 clips can train and test a letter classifier (next experiment) |

---

## 6. Installation and difficulties

| Problem | What happened | Solution |
|---|---|---|
| Whisper loops on one-second clips | Without a limit, `openai/whisper-small` wrote hundreds of tokens for some clips; the first full run was stopped after two hours | Output limited to 12 tokens for both Whisper models. Only the first letter and vowel are scored, so the limit does not change the scores |
| Old configuration of the Quran Whisper | `tarteel-ai/whisper-base-ar-quran` rejected the `language` argument ("generation config is outdated") | Called without the argument; the model knows only Arabic |
| Whisper is slow on the CPU | About 2 s per clip for the base model: every clip is padded to 30 s | Run on the Apple GPU |
| Muaalem is slow on the CPU | About 5 s per clip | Run on the Apple GPU, as the bot does: 0.17 s per clip |
| 8 GB of memory | Two models cannot be loaded together | Systems run one after another |
| Results lost when a run is stopped | The first version wrote the file only at the end | Rows are written as they are produced; `--resume` continues a stopped run. The `whisper` file was completed this way (776 clips, then 64) |
| Different symbol sets | Three inventories: Arabic script with vowel signs, Buckwalter-like symbols, IPA | A mapping table per system in `letters_test.py`; for IPA it is lenient and omits the emphatic letters |

No model failed to install. No new dependency was added to the project: the experiment uses the libraries already present in the project's environment.

---

## 7. Limitations

1. **Not our learners.** Indonesian school students, not Russian-speaking adults; their first language has a different sound system.
2. **No ground truth for errors.** A mismatch is either a model error or a student error. The scores are therefore a lower bound on model accuracy, and the test cannot measure error detection (missed errors, false alarms).
3. **A sample.** 840 of 8,904 clips; 30 per letter. Per-letter figures are rough.
4. **Only the first consonant and vowel are scored.** Extra sounds after them are ignored, which favours every system equally.
5. **Models as published.** No adaptation, thresholds or per-sound confidence were used. The bot does not use Muaalem's transcription alone in the same way, so this is not a measurement of the bot.
6. **Speed across devices.** Three systems ran on the Apple GPU and two on the CPU.
7. **Not tested:** Quran Lab TajweedFormer V4 (licence and server access undecided), `Hisnlabs/tajweed-v2`, `nrshoudi` models, NVIDIA FastConformer (needs a toolkit that is not installed — a new dependency is the author's decision), Azure and Gemini (audio would leave our computer), L2-KSU (access not requested yet), reference comparison and the letter classifier.

---

## 8. How to repeat

```sh
# 1. Data: download dataset.zip from the Hugging Face page of
#    Reinjin/Pelafalan_Huruf_Hijaiyah and unpack it; DATA is the folder
#    that holds the 84 class folders ("01. alif_fathah" …).

# 2. One system at a time, from the project root:
.venv/bin/python -I docs/research/phase3/letters_test.py DATA \
    docs/research/phase3/results/letters_maroof.csv maroof --per-class 10
#    …the same for: espeak, muaalem, tarteel, whisper
#    (add --resume to continue a stopped run)

# 3. Tables:
.venv/bin/python -I docs/research/phase3/summarise.py \
    docs/research/phase3/results > docs/research/phase3/results/summary.md
```

Clip selection is deterministic (sorted file names, fixed step), so a repeat uses the same 840 clips.

Files:

| File | Content |
|---|---|
| `phase3/letters_test.py` | Runs one system over the clips |
| `phase3/summarise.py` | Builds the tables |
| `phase3/results/letters_<system>.csv` | One row per clip: class, expected letter and vowel, raw output, parsed letter and vowel, audio length, compute time |
| `phase3/results/summary.md` | The tables of section 3 as produced by the script |

---

## 9. Open questions

1. How often is the mismatch the student's error? Answering needs a teacher to label a sample of these clips, or our own labelled recordings.
2. Does Muaalem's per-sound confidence separate its right and wrong answers on letters? The raw output is available but was not analysed here.
3. How well does a closed-set classifier trained on the remaining clips perform on speakers it has not heard?
4. Does comparison with a teacher's recording work on one-second clips?
5. Should a held vowel on a single letter count as an error at all? (Method — the author's decision.)

## 10. Recommended next steps

1. ~~Train and test the closed-set letter classifier on this dataset, split by speaker.~~ Done in step 2, section 11.
2. Test comparison with the bot's reference recordings on the same clips. Tried in step 2: the library recordings are not usable for this (section 11.6).
3. Request access to L2-KSU for a test with real error labels on words and sentences.
4. Above all: collect and label the first batch of our own learners' recordings, then repeat this comparison on them.

---

## 11. Step 2 — candidate checkers built and tested

### 11.1 Question

Step 1 ran ready-made systems as published. Phases 1 and 2 and both surveys pointed to a different design for the first stage of the book: do not transcribe freely, but *verify* the expected item from a small closed set. Step 2 builds that design and measures it against free transcription on the same data.

### 11.2 What was built

All four candidates use the same listening model, `MostafaMaroof/wav2vec2-arabic-phoneme-asr`, the strongest of step 1. They differ only in how the decision is made.

| Candidate | How it decides | Needs training data | Family in the surveys |
|---|---|---|---|
| **Free transcription** | Reads the first letter and vowel from the model's ordinary output (as in step 1) | No | Sounds, free |
| **Constrained choice** | Lets the model choose only among the 28 letters and 3 vowels: the letter whose symbol scored highest anywhere in the clip | No | Sounds, verified |
| **Template comparison** | Compares the clip's inner representation with the average representation of each of the 84 classes from other speakers | Yes, examples only | Comparison with references |
| **Trained classifier** | A single linear layer over the model's inner representation (three layers averaged over time), 84 outputs, plain regularised softmax; nothing tuned | Yes | Classifier per letter |

### 11.3 Test design

| Item | Value |
|---|---|
| Data | All 8,904 clips of `Reinjin/Pelafalan_Huruf_Hijaiyah`, 84 classes |
| Speakers | 48 groups. Students appear under a full name in most folders and a shortened name in a few; a first check that used the full name split one student into two and let some voices into both training and test. The final split groups by first name, which is stricter than needed |
| Split | Five folds by speaker: each clip is judged by a checker trained on the other four fifths of the speakers and **never on its own speaker** |
| Label | The class the student was asked to read (no teacher verification exists in this dataset) |
| Computation | One pass of the model over all clips (≈40 minutes on a MacBook Air M1), then training and testing in a few minutes |

### 11.4 Results — which letter and vowel was read

| Candidate | Letter right | Vowel right | Both right |
|---|---|---|---|
| Free transcription | 63.2 % | 70.9 % | 47.2 % |
| Constrained choice | 62.4 % | 86.2 % | 55.3 % |
| Template comparison | 70.9 % | 96.9 % | 69.6 % |
| **Trained classifier** | **88.5 %** | **99.0 %** | **88.0 %** |

Free transcription gives 47.2 % on all 8,904 clips, close to the 50.0 % measured on the 840-clip sample in step 1.

95 % intervals over students (bootstrap, 2,000 resamples of the 48 speaker groups, seed 0): trained classifier 88.0 % [86.8–89.1], free transcription 47.2 % [45.2–49.2]. Per student the classifier ranges from 71 % to 96 % (median 89 %); free transcription from 29 % to 61 % (median 46 %).

Letters that were hardest for free transcription, and the classifier on the same letters:

| Letter | ث | ظ | ض | ص | د | ق | ط |
|---|---|---|---|---|---|---|---|
| Free transcription | 17.9 % | 8.8 % | 18.6 % | 24.2 % | 25.8 % | 26.1 % | 27.4 % |
| Trained classifier | 82.7 % | 53.5 % | 77.4 % | 84.6 % | 86.2 % | 82.4 % | 79.6 % |

### 11.5 Results — the question the bot actually asks

The bot always knows what the learner should read. Its real question is "was the expected item read?" — accept or reject. Two kinds of trial were built from the same clips:

- **genuine:** the clip is checked against the item the student was asked to read;
- **substitute:** the clip is checked against a different item, as if the student had been asked for that one and said this instead. Three kinds: same letter with another vowel; a letter from a confusable pair (د/ت, ص/س, ض/د, ط/ت, ظ/ز, ث/س, ح/ه, ع/ء, ق/ك, ذ/ز, both directions); a random other letter.

| Checker | Correct readings accepted | Wrong vowel accepted | Confusable letter accepted | Random letter accepted |
|---|---|---|---|---|
| Free transcription | 47.2 % | 3.2 % | 13.1 % | 1.0 % |
| Classifier, accept at probability 0.1 | 94.3 % | 0.7 % | 9.9 % | 1.1 % |
| **Classifier, accept at 0.3** | **90.5 %** | **0.3 %** | **5.2 %** | **0.6 %** |
| Classifier, accept at 0.5 | 86.5 % | 0.2 % | 3.5 % | 0.3 % |

Read the first row as a learner would: with free transcription, more than half of the students who read the item as asked would be told they made an error. The classifier at 0.3 tells this to fewer than one in ten, and lets through about one confusable substitution in twenty.

Per confusable pair, at 0.3:

| Expected | Said instead | Correct accepted | Substitute accepted |
|---|---|---|---|
| د | ت | 89.0 % | 4.7 % |
| ص | س | 88.4 % | 6.3 % |
| ض | د | 83.3 % | 8.5 % |
| ط | ت | 81.8 % | 4.7 % |
| ظ | ز | 58.5 % | 3.1 % |
| ث | س | 85.8 % | 11.0 % |
| ح | ه | 92.5 % | 2.8 % |
| ع | ء | 93.4 % | 0.9 % |
| ق | ك | 86.2 % | 1.6 % |
| ذ | ز | 76.4 % | 2.5 % |
| س | ث | 93.1 % | 16.4 % |

The reverse directions of the other pairs are in `results/candidates.json`; all lie between 1.3 % and 7.5 % substitutes accepted.

**"Not sure" instead of a verdict.** When the classifier answers only if its top choice has at least a given probability:

| Answers when the top probability is at least | Clips answered | Right among answered |
|---|---|---|
| any | 100 % | 88.0 % |
| 0.5 | 96.5 % | 89.7 % |
| 0.7 | 88.4 % | 92.9 % |
| 0.9 | 75.0 % | 95.8 % |

**Two signals.** When the classifier and the constrained choice name the same letter and vowel (57.5 % of clips), the classifier is right in 92.1 % of them.

### 11.6 Check on the bot's own recordings

The project holds 84 library recordings of single vowelled letters (`curriculum/audio/library`, SRC-144). They were run through the classifier with `check_recordings.py`. The classifier's best guess matched the label in 22 of 84; the vowel was most often heard as a (55 of 84).

This result does not measure the classifier. The project already records that these files are mislabelled in places, and each of them contains the spoken name of the vowel ("fatha", "kasra", "damma") besides the syllable, which the classifier never saw in training. A real check needs voice messages with the syllable alone.

### 11.7 What this shows

1. **Verification over the closed set is the right design for the first stage.** On speakers it never heard, a simple classifier is right in 88 % of clips, against 47 % for free transcription by the same model. Nothing was tuned; the gain comes from the design.
2. **It answers the bot's real question far better.** It accepts 90.5 % of correct readings instead of 47.2 %, while letting through 5.2 % of confusable substitutions.
3. **A "not sure" zone works as expected.** Answering three clips out of four raises correctness to 95.8 %.
4. **Weak spots remain where they were:** ظ (58.5 % of correct readings accepted) and the pair ث/س (11–16 % of substitutes accepted).

### 11.8 Limitations of step 2

- **The labels say what the student was asked to read, not what was said.** The classifier learns how these students pronounce each item. If a group of students systematically says ز for ظ, the classifier learns to accept that. The substitute trials show that attempts at each letter of a pair are mostly kept apart, but whether any attempt was correct can only be known from teacher labels.
- **Substitutions are simulated** from other students' attempts at the other letter, not from real errors.
- **Not our learners.** Indonesian school students, not Russian-speaking adults. A classifier must be retrained on our own recordings.
- **One listening model.** The same comparison with Muaalem or other encoders was not run.
- Speakers were grouped by first name; two different students with the same first name are counted as one.
- Step 1 chose "ten different students" per class by spacing file names; because of the name variants found here, a few of those ten may be the same student.

### 11.8a What the bot itself would say today

The bot’s own decision code — its two accepted references (joined reading and reading with a stop, `infrastructure/asr/muaalem.py`), its comparison (`domain/assessment.py`) and its pass marks of 80 and 90 (`domain/policy.py`) — was run on the bot model’s output for the 840 recordings of step 1 (`demo_data.py`).

| Outcome | Recordings of 840 |
|---|---|
| “Repeat” (score under 80) | 725 (86.3%) |
| Passed | 72 |
| Excellent | 43 |

Most frequent errors the bot would name: vowel too long in 443 recordings, another letter in 268, extra sound in 174, several sounds replaced in 123 (a recording can carry several). In 204 of the 725 “repeat” recordings “vowel too long” is the only error (counted from the output of `demo_data.py`).

The trained classifier on the same 840 recordings, at the same thresholds as section 11.5: accept 739 (88.0%), “say it again” 41, name an error 60.

On the 725 “repeat” recordings the classifier accepts 629, asks again 37 and names an error 59.

A side finding about the bot’s references: for a single letter the second accepted reference, the reading with a stop, carries no vowel sign (أَ → `ءَ / ء`, ضَ → `ضَ / ض`, بَ → `بَ / بڇ`). The bot therefore passes a letter whose vowel the model did not hear at all: 7 of the 115 passed recordings contain no short-vowel sign in the model’s output (for example إِ heard as `ء`, scored 100). Whether single-letter items should accept the stop reading is a methodology decision for the author.

Who is right in each recording cannot be known without a teacher. The commonest reason, a long vowel on a single letter, is the student holding the sound, which is how a letter is usually said alone; this supports improvement 5 in `MUALLIM_AND_THE_FIELD.md` (methodology — the author’s decision).

### 11.8b Prototype: check each expected sound (forced alignment + GOP)

Why: the closed-set check covers only single syllables; the whole book (sukun, shadda, madd, words, lines) needs a method that works for any expected text and needs no training on our data. Prototype `align_check.py`: the expected syllable becomes the model’s symbols (letter, vowel; plain and doubled letters merged, short and long vowel merged so that a held vowel is not an error); CTC Viterbi forced alignment finds the frames of each expected sound; for each sound, GOP = mean over its frames of log P(expected) − max log P(another unit of the same kind). Pass when both letter and vowel score above the threshold. Model: MostafaMaroof; the same 840 recordings as step 1; nothing trained.

| Threshold | Correct passed | Look-alike letter passed (600 checks) | Other vowel passed (1,680 checks) |
|---|---|---|---|
| −1 | 68.9 % | 18.8 % | 7.1 % |
| 0 | 62.9 % | 14.8 % | 4.3 % |
| +1 | 56.1 % | 13.0 % | 2.4 % |

At threshold 0: the vowel fails in 55 of 840 recordings, the letter in 281 (most often ث ظ ط ض د ص ق — the look-alike letters).

Compared on the same kind of trials: free transcription with the same model passes 47.2 % of correct readings and 13.1 % of look-alike swaps; the closed-set classifier 90.5 % and 5.2 % (8,904 recordings, §11.5); the bot today passes 14 % (840, §11.8a).

What this shows: per-sound checking is better than free transcription and far better than the bot today, works without training and extends to any text, but on single letters it is clearly weaker than the closed-set classifier, and it lets look-alike consonants through as often as transcription does. A second finding from the listening page (`listen_page.py`): CTC models mark each sound by a short spike of one or two frames, not by its real duration — the vowel spike sits at the end of the voiced part. The alignment therefore gives *where* a sound is, not *how long* it lasts; shadda and madd length cannot be read from these spikes and need a duration-aware aligner or frame-level scoring. Not yet tested: words, sukun, shadda, madd; Muaalem as the listening model.

### 11.8c Prototype: choose among the card's variants (the answer the learner will see)

Author’s decision (2026-11-19): the learner sees only this method; the teacher sees all methods and marks which was right. For each card the variants are the correct reading and its typical errors — the other two vowels, the letter without a vowel, each look-alike letter with the same vowel; a held vowel counts as correct. The model scores how likely the recording is under each variant (CTC forward probability over the frame probabilities saved by `align_check.py`); the correct reading must beat the best error by the margin. `variants_check.py`, same 840 recordings, nothing trained, 5 s for all recordings.

| Margin | Correct passed | Look-alike letter passed (600) | Other vowel passed (1,680) |
|---|---|---|---|
| 0 | 76.1 % | 18.0 % | 3.2 % |
| 2 | 54.3 % | 9.8 % | 0.4 % |
| 4 | 20.8 % | 2.5 % | 0.1 % |

Side by side at the working thresholds: the bot today passes 14 % of these 840; free transcription 47 %; per-sound check 63 %; card variants 76 %; the 84-syllable classifier 91 % (§11.5, trained, single syllables only). Look-alike letters still slip through in about 1 of 5 trials; most frequent “errors” named on correct readings are س (40), fatha (33), ت (25), ز (22), د (18). The method extends to any card for which typical errors can be listed (sukun, words), which the classifier cannot. Not tested yet on words; the error lists for later cards are a methodology decision.

### 11.8c-bis Card variants on the bot's model Muaalem (ADR-0086, point 7)

Same 840 recordings and variants, written in Muaalem's phonetic script; a held vowel allowed for every variant. `muaalem_variants.py`, CPU, ≈25 min.

| Model | Correct passed | Look-alike passed | Other vowel passed |
|---|---|---|---|
| MostafaMaroof (§11.8c) | 76.1 % | 18.0 % | 3.2 % |
| Muaalem | 62.0 % | 18.5 % | 7.7 % |

(margin 0; at margin 2: Muaalem 47.9 / 7.3 / 3.6.) Muaalem is worse on single syllables — fewer correct readings passed and more vowel swaps let through, consistent with its bias towards “a” (§3.3). By the rule of ADR-0086, point 7, MostafaMaroof is added as a second listening model for the card-variants check; Muaalem stays for the rest. Even Muaalem with card variants passes 62 of 100 against 14 for the bot today.

### 11.8d Card variants on whole phrases (stage II: words and lines)

No open recordings of learners reading words were found with a clear licence (`Buraaq/quran-md-words` states none). Material: 300 random phrases of IqraEval `Iqra_train` dev (CC BY-NC 4.0; Common Voice MSA and Quran, **correct** readings by fluent speakers) with their phoneme transcription in the same symbols as MostafaMaroof. Error variants are made by the draft rules of `error_rules.py` (`ERROR_RULES_DRAFT.md`), two positions per rule and phrase; the model scores the correct reading against each variant (CTC forward). `words_check.py`.

| Rule | Pairs | Correct reading wins |
|---|---|---|
| another vowel | 600 | 96.2 % |
| vowel added on a sukun | 540 | 96.3 % |
| shadda dropped | 265 | 89.8 % |
| madd shortened | 538 | 91.3 % |
| short vowel lengthened | 600 | 98.8 % |
| look-alike letter | 599 | 98.8 % |

Per phrase (about 12 variants each), the share of correct phrases where at least one error variant wins — the bot would scold a correct reader: 34 % if any lead counts, 17 % with a tolerance of 2, 6 % with a tolerance of 4 (log-probability). Weakest rules: shadda and madd — the duration problem of §11.8b.

Caveats: the speakers are fluent, not beginners; MostafaMaroof was trained on IqraEval `Iqra_train` (its train split, not dev), so the material is close to its training data and the numbers are optimistic; only “does it leave a correct reading alone” is measured, not real learner errors. A first bug — the word-boundary symbol “|” was not folded into the blank, which made every inserted vowel look likely (2 % instead of 96 % for the sukun rule) — was found on a single phrase and fixed before these numbers.

### 11.8e MostafaMaroof against Muaalem on whole ayahs

Material: 200 phrases of `Iqra_train` dev that are exactly one whole ayah (663 found among 2,588; matched by the undiacritised text with `quran_transcript`), read correctly. Each model gets its reference as in the bot: MostafaMaroof the Halabi transcription of the dataset, Muaalem the bot's phonetiser on the Uthmani text (`_references`, reading with a stop). The same kinds of errors are made on each reference, two positions per rule and ayah. `compare_models.py`; listening page `muallim-listen-models.html` (`listen_models.py`).

| Error | MostafaMaroof: correct wins | Muaalem: correct wins |
|---|---|---|
| another vowel | 99.0 % (400) | 94.0 % (400) |
| vowel on a sukun | 99.2 % (375) | 99.7 % (343) |
| shadda dropped | 94.8 % (249) | 33.6 % (327) |
| madd shortened | 93.6 % (393) | 43.3 % (393) |
| short vowel lengthened | 98.8 % (400) | 99.8 % (400) |
| look-alike letter | 99.8 % (400) | 93.5 % (400) |

Correct ayahs the model would scold (at least one error variant ahead): MostafaMaroof 22 % strict, 5 % with a tolerance of 4; Muaalem 88 % and 82 %.

Reading the result: on what is not about length (vowels, letters, sukun) MostafaMaroof is equal or better. On shadda and madd Muaalem judges by recitation rules — its output on these readers is `قِۦ` where the reference has `قِۦۦ`, `كَذَبُ` for `كَذذَبُ` — the readers of this set read fast, so by Muaalem's standard they did shorten; MostafaMaroof, trained on ordinary speech, is lenient about length. For beginners, with shadda and madd judged softly (ADR-0086), the lenient model fits; Muaalem's strictness is what an advanced tajwid mode would need. MostafaMaroof has no symbols for ikhfa, ghunna or qalqala, so tajwid itself can only be checked with Muaalem. Caveats: MostafaMaroof was trained on the train split of the same dataset; the readers are not beginners and seem not to be professional reciters; only false alarms are measured.

**Baseline “before training”** — `results/baseline_840.csv`, one row per recording (840): what was asked; what the bot heard, its score, verdict and errors; the 84-syllable choice (best syllable, probability of the asked one, decision); the per-sound check (sound heard on the letter and on the vowel, confidence, GOP, decision); what the four other models wrote; how many models disagree with the asked syllable; empty columns `teacher_heard` and `teacher_verdict` for a teacher. Built by `baseline.py` from `align_check.py` and `demo_data.py`; `results/align_summary.json` keeps the alignment of every recording. After any training or change of model, rebuild the same table and compare it row by row with this file (and with the teacher columns once they are filled).

### 11.8f Thresholds of the three answers (MostafaMaroof, card variants)

margin = correct reading − best error variant. `margin ≥ PASS` → “passed”; `ERROR ≤ margin < PASS` → “say it again”; `margin < ERROR` → “error”. “Obvious error” is simulated: the same correct syllable recording checked as if another vowel (1,680 trials) or a look-alike letter (600 trials) had been asked. `thresholds.py` → `results/thresholds_summary.json`.

| Threshold | Correct syllables reaching it (of 840) | Other vowel slips past (of 1,680) | Look-alike slips past (of 600) | Correct ayahs below it (of 200) |
|---|---|---|---|---|
| −6 | 96.0 % | 83.9 % | 67.7 % | 0.5 % |
| −5 | 94.9 % | 68.2 % | 54.7 % | 2.0 % |
| −4 | 92.1 % | 45.6 % | 44.3 % | 5.0 % |
| −2 | 86.7 % | 12.7 % | 28.7 % | 9.0 % |
| −1 | 82.4 % | 6.3 % | 23.2 % | 14.5 % |
| 0 | 76.1 % | 3.2 % | 18.0 % | 22.0 % |
| +1 | 67.3 % | 0.9 % | 15.0 % | 32.5 % |
| +2 | 54.3 % | 0.4 % | 9.8 % | 47.0 % |

Reading: one number is not enough — a strict PASS (0) lets almost no wrong vowel through but stops a quarter of correct syllables; a soft ERROR (−4…−5) keeps wrongly scolded correct readings at 5–8 % of syllables and 2–5 % of ayahs. Between the two the learner hears “say it again”, which is safe both ways. Look-alike letters are the weak point at any threshold (18 % slip past even at 0) — the main target of fine-tuning (ADR-0087). The values for the bot are the author's choice (`domain/policy.py`); to be revisited on the 200 recordings labelled by the teacher. Caveat: the syllable recordings are not labelled by a teacher — some “correct” ones may contain real errors, which lowers the first column.

### 11.8g The learner said something else entirely

Each of the 840 syllable recordings checked against 3 cards of an unrelated syllable (another, not look-alike, letter; any vowel) — 2,520 trials, e.g. a recording of “zu” against the card “ba”. `wrong_card.py` → `results/wrong_card_summary.json`. Thresholds of the card variants 0 / −4 (§11.8f; ADR-0087 point 4, the strict option chosen by the author).

| Check | Own card: passed / again / error | Wrong card: passed / again / error |
|---|---|---|
| card variants only | 76.1 / 16.1 / 7.9 | **18.2** / 42.0 / 39.8 |
| + absolute fit per frame ≥ −0.1 | 68.9 / 9.4 / 21.7 | 3.8 / 1.9 / 94.3 |
| + absolute fit per frame ≥ −0.2 | 75.0 / 15.1 / 9.9 | 14.1 / 19.0 / 66.9 |
| + “another syllable” rival, again −3 / error −6 | 68.9 / 18.8 / 12.3 | **1.2** / 9.4 / 89.5 |
| + “another syllable” rival, again 0 / error −4 | 61.5 / 21.3 / 17.1 | 0.5 / 3.0 / 96.5 |

Reading: the card variants only compare the card with its own typical errors, so a different syllable can win as “the least bad” — 18 of 100 wrong syllables would pass. Adding every other syllable (another, not look-alike, letter) as one more rival closes the hole (1 of 100) at a price of 7 fewer correct syllables passed at once; an absolute per-frame fit does worse at every cut. For words and phrases the same rival is the free decoding — not yet measured; to be done before the bot uses phrases. Caveat as in §11.8f: the syllable recordings are not labelled by a teacher.

### 11.8h Sukun with MostafaMaroof

MostafaMaroof has no sukun symbol: a letter with sukun is a consonant with no vowel after it. Every sukun position of the 200 correct ayahs of §11.8e (1,115; inside the phrase 960, last letter 155), no sampling; the correct reading against: a vowel added after the letter (each of a / i / u, not only fatha as in §11.8e), and the letter not read at all. `sukun_check.py` → `results/sukun_summary.json`; MostafaMaroof outputs cached for later checks.

| Error variant | Correct wins | Error ahead by more than 4 |
|---|---|---|
| vowel a added | 97.9 % (1,115) | 0.5 % |
| vowel i added | 99.5 % | 0.0 % |
| vowel u added | 99.1 % | 0.0 % |
| sukun letter dropped (inside) | 97.3 % (960) | 0.3 % |
| vowel a added, qalqala letter (ق ط ب ج د) at the end | **89.5 %** (19) | 0.0 % |

Reading: plain sukun is safe to check strictly. The one weak spot is a qalqala letter at the stop — its correct light echo can sound like a fatha; the sample is small (19), so there the bot should only hint. Not measured: what the book's sukun lessons 49–51 actually teach — two neighbouring letters that merge (idgham: قَد تَّبَيَّنَ, the first letter is not read) or stay clear (قَدْ تَبَيَّنَ) — and the article with sun / moon letters (lesson 53). The converter now exists (§11.8i); they need recordings of the lesson lines; to be measured before those lessons use the new check. Caveat: readers are not beginners; only false alarms are measured.

### 11.8i Book text → MostafaMaroof sounds (the converter) and a first check on a teacher's voice

**Converter** (`to_maroof.py`): the bot's own phonetiser (quran_transcript, `_references` — reading by Hafs, with and without a stop) and a symbol table into MostafaMaroof's alphabet. Not the phonetiser the model was trained with (Nawar Halabi's, used by IqraEval): its transcriptions follow the spelling, not the reading the book teaches — on 663 whole ayahs they differ from ours in 6.3 % of sounds, and the differences are Quran reading rules: a long vowel shortened before a sukun across words (فِى ٱلْأَرْضِ), the pronoun's long vowel (إِنَّهُۥ), the long a of ٱللَّهِ, tanwin and merges of nun / mim. MostafaMaroof, trained on those transcriptions, prefers them (`convention_check.py`: of 378 differing places it accepts our reading in 17.7 %) — the reason to fine-tune it on book-style readings later, and a risk for lessons 42+ (tanwin, merges). Lessons 1–41 hardly have these rules: of the 288 cards checked by voice (plus 4 alphabet cards) none has tanwin or the pronoun's long vowel; all convert; the four alphabet cards (L002-02…05, «look at the letters and their names») are not checked by voice — the book teaches sounds, not names. Heavy vowels (A I U after emphatic letters) are not guessed: their probability is added to the plain vowel when scoring (`prepare`). A card of separate syllables is read with every vowel (no stop).

**Teacher's voice** (`library_check.py` → `results/library_check.json`): the bot's 28 library recordings of three syllables (رَ رِ رُ, …) by ar-Rai (SRC-144), the content of lessons 3–30, through the whole chain — card text → converter → card variants with the «another syllable» rival → answer (thresholds of ADR-0087).

| Setting | Own card: passed / again / error | Look-alike card (should be error) | Unrelated card (should be error) |
|---|---|---|---|
| every vowel judged (a held vowel counted as an error) | 1 / 5 / 22 | 14 of 16 error | 27 of 28 error |
| last syllable: a stop allowed and its vowel judged softly; a held vowel = short | 16 / 10 / 2 | 14 of 16 error, 1 passed | 26 of 28 error |

Reading: the teacher reads fast and the last vowel of the three fades — the model hears «b a b i b». To see whether a rule for the last syllable still catches errors, each recording is also checked against cards with its **last vowel** (56 trials) or **middle vowel** (56) replaced — as if the learner had read that vowel wrong:

| Rule for the last syllable | Correct reading: passed / again / error | Last vowel wrong: passed / again / error | Middle vowel wrong: passed / again / error |
|---|---|---|---|
| strict — like every syllable (here and below a held vowel = short) | 2 / 9 / 17 | 0 / 14 / 42 | 0 / 10 / 46 |
| soft — a stop allowed, another vowel an error only below −4 | 16 / 10 / 2 | **28** / 21 / 7 | 0 / 24 / 32 |
| **clear** — the vowel heard must be the right one; a vowel hardly heard → «say it again» | 2 / 24 / 2 | **0** / 46 / 10 | 0 / 24 / 32 |

The soft rule lets half of the wrong last vowels through: once a stop counts as correct, a faded vowel of any kind passes. The clear rule never passes a wrong last vowel and scolds the correct reading only twice (ث heard as س — the known weak pair — and و); a vowel the model cannot hear is asked again. The model cannot judge a vowel that is hardly pronounced — the learner has to say it clearly (a held vowel is allowed on lessons 3–30, ADR-0086). Caveats: one reader, a fast style, trimmed files; learners read slower (on the 840 learner syllables «no vowel» was rarely the rival, §11.8a). `results/library_check.json` holds the clear rule; the strict and soft rows are runs of the same script with `--last strict` / `--last soft --last-error=-4`. Which rule the bot uses is the author's decision.

### 11.9 How to repeat

```sh
# Book text → MostafaMaroof sounds, checks on whole ayahs and lessons 1–41 (§11.8i):
python docs/research/phase3/to_maroof.py WAV_DIR results/to_maroof_summary.json --cache LOGPROBS.npz --cards results/cards_1_41_maroof.tsv
python docs/research/phase3/convention_check.py WAV_DIR LOGPROBS.npz results/convention_summary.json
python docs/research/phase3/library_check.py results/library_check.json --last clear

# 1. Model features for every clip (one pass, resumable):
.venv/bin/python -I docs/research/phase3/features.py DATA FEATURES
# 2. Build and compare the four candidates; writes results/candidates.json
#    and results/letter_classifier.npz (the classifier trained on all clips):
.venv/bin/python -I docs/research/phase3/candidates.py FEATURES docs/research/phase3/results
# 3. Check any recordings: a CSV with columns file,text (e.g. ba.ogg,بَ):
.venv/bin/python -I docs/research/phase3/check_recordings.py \
    docs/research/phase3/results/letter_classifier.npz RECORDINGS.csv OUT.csv
```

`features.py` stores speakers only as short hashes; no student name is written anywhere.
