# Phase 3 — Experimental Results (preliminary)

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-17
**Status:** one preliminary experiment, run in full. Five systems, 840 public recordings of single vowelled letters. **No recording of a Muallim learner was used**, because no teacher-labelled recordings of our learners exist yet.
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

1. Train and test the closed-set letter classifier on this dataset, split by speaker.
2. Test comparison with the bot's reference recordings on the same clips.
3. Request access to L2-KSU for a test with real error labels on words and sentences.
4. Above all: collect and label the first batch of our own learners' recordings, then repeat this comparison on them.
