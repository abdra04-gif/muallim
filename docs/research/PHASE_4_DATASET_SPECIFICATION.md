# Phase 4 — Muallim Dataset Specification

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-16
**Status:** proposal. Nothing in the code or database was changed. Phase 3 (running models) was skipped by the author's decision, so this specification rests on Phases 1–2 and on the project's existing data model, not on our own measurements.
**Update (2026-11-17):** a preliminary Phase 3 test was run later (`PHASE_3_EXPERIMENTAL_RESULTS.md`). It used public letter recordings, not our learners, and does not change this specification.
**Revision 2 (2026-11-16):** section 3 rewritten as a sourced comparison of nine existing datasets and their design choices; section 12a added (strengths and weaknesses of the project's current data design, proposals to add, remove and keep); Hugging Face layout rules verified in its documentation.
**Next:** Phase 5 (architecture and consent) — waiting for approval.

---

## 1. Summary

1. **The project already has most of this dataset.** The bot stores every attempt with the reference, the model's answer, teacher labels and versions; an export already writes a manifest, benchmark-compatible tables and audio. This specification defines the **public release** built on that export and lists what is missing.
2. **Recommended format:** one folder of audio files plus plain-text tables (JSON Lines and CSV), published on Hugging Face, which converts it to Parquet automatically. One canonical table, several derived ones.
3. **Unit of data:** one *attempt* — one voice message in which one learner reads one textbook item.
4. **Three layers of transcription per attempt:** what should be read (reference), what the model heard, and what teachers say was actually read. They are stored separately and never overwrite each other.
5. **Split by learner, never by recording.** The test part is fixed before any training and its teacher labels are produced without seeing the model's answer.
6. **Seven gaps** separate the current export from a publishable dataset (section 12). The most important: public release needs its own consent record, release-only speaker codes, and removal of religious-practice data.

Schema changes, the consent text, annotation rules and anything touching personal data are decisions for the author under project rules; here they are proposals.

---

## 2. Starting point: what exists today

| Need | Already in the project | Where |
|---|---|---|
| Attempt record with reference and model answer | Yes | table `attempts` |
| Raw model output (per-sound confidence, articulation attributes) | Yes | `attempts.model_output` |
| Versions of curriculum, model, thresholds, code | Yes | `attempts`, `curriculum_items` |
| Teacher labels, several annotators, history kept | Yes | `annotations`, `annotation_marks` |
| Agreement between annotators | Yes (consensus field; α and κ computed) | `research/dataset.py`, `research/metrics.py` |
| Learner questionnaire (age group, gender, first language, reading level) | Yes | `learner_profiles` |
| Pseudonymous learner code | Yes (`L-` + 8 characters derived from the internal id) | `learners.pseudonym` |
| Export for research | Yes: `manifest.jsonl`, `truth.csv`, `predictions.csv`, `phonemes.csv`, `audio/` | `research/dataset.py` |
| Consent journal with text version | Yes, one kind: storing recordings for research | `consents` |
| Consent to **public** release | **No** | — |
| Speaker codes safe for publication | **No** | — |
| Train / validation / test assignment | **No** (planned in ADR-0051) | — |
| Dataset card, licence, checksums | **No** | — |

---

## 3. How existing datasets are built (revision 2)

Evidence marks as in Phases 1–2: **[P]** read on the dataset's page or paper in this research; **[R]** from the project's earlier reading; **[?]** general knowledge, not checked.

### 3.1 Structure of comparable datasets

| Dataset | Container | Unit of a record | How errors are stored | Speaker data | Splits | Licence | Evidence |
|---|---|---|---|---|---|---|---|
| **speechocean762** (English learners) | Parquet on Hugging Face; originally Kaldi-style files | Utterance | Nested: sentence scores (accuracy, completeness, fluency, prosody, total) → `words[]` with scores → per-sound accuracy 0–2 and a `mispronunciations[]` list (canonical sound, position, produced sound). Five experts per utterance | `speaker`, `gender`, `age` | train / test, 2,500 each | Free for commercial and non-commercial use; Apache-2.0 on the hub | [P] HF page, arXiv:2104.01378 |
| **L2-ARCTIC** (English learners) | WAV + one Praat TextGrid per recording | Utterance, time-aligned | Tiers: words, sounds, error tags (substitution, deletion, addition), annotator comments; boundaries corrected by hand | 24 speakers, first language and gender by design | None provided | CC BY-NC 4.0 | [P] corpus page |
| **L2-KSU** (Arabic, non-native) | Zip: folders by native / non-native → gender → speaker → sentence, each with `wav`, `transcript`, `annotation`; plus one CSV | Utterance | CSV columns `text`, `canon`, `ans` (canonical and produced sounds), `path`; TextGrid per file | Encoded in the folder path only | None (the two original files were identical) | CC BY-NC-ND 4.0 | [P] HF card |
| **IqraEval** (`Iqra_train`, QuranMB) | Parquet | Utterance | Columns `sentence`, `tashkeel_sentence` (vowelled), `phoneme_ref`, `phoneme_aug`; sounds separated by spaces; evaluation files `Reference_phn`, `Annotated_phn`, `Prediction` | None | train / dev; separate test set | CC BY-NC 4.0 | [P] HF card; [R] |
| **RetaSy** (Arabic, non-native) | Parquet | Recording | One `final_label` of six values; `golden` (expert or crowd); `judgments_num`; `annotation_metadata` with each annotator's label and reliability scores | `reciter_id`, `reciter_country`, `reciter_gender`, `reciter_age` | Single | None stated | [P] HF card |
| **qdat_bench** (Arabic, amateur readers) | Parquet | Recording | One column per rule measurement (lengths, nasalisation, qalqalah); `phonetic_transcript`; `sifat[]` — ten attributes per sound | `gender`, `age` | Single | Apache-2.0 | [P] HF card |
| **`sobolev210` errors** | Audio folder | Recording | `errors`: a dictionary word → list of categories or null; `reviewer_id` | `recording_id` only | Single | MIT | [P] HF card |
| **`Reinjin` letters** | Audio folder, class per directory | Clip | None — class label only | None | Single | AFL-3.0 | [P] HF card |
| **Common Voice** (general speech) | MP3 clips + TSV tables | Clip | None — `up_votes` / `down_votes` from listeners | `client_id`, `age`, `gender`, `accents` | train / dev / test / validated / invalidated tables | CC0 [?] | [P] column list; licence [?] |

### 3.2 What is strong and weak in these designs

| Design choice | Seen in | Strong | Weak | Decision for Muallim |
|---|---|---|---|---|
| Canonical and produced sound sequences side by side | L2-KSU, IqraEval, speechocean762 | Standard; every error type follows from comparing two strings; scoring scripts exist | Positions are implicit; needs an alignment rule | **Adopt** (already in the project) |
| Per-annotator labels kept, not only the final one | RetaSy, speechocean762 | Agreement can be recomputed; users can choose their own consensus rule | Larger records | **Adopt** (already in the project) |
| Final label only | L2-KSU, qdat_bench, IqraEval | Simple | Reliability cannot be checked | Avoid |
| Flag for expert versus crowd label | RetaSy (`golden`) | Lets users weight labels | — | **Adopt** as annotator description and `phonemes_source` |
| Invalid-audio categories kept in the data | RetaSy | Realistic; trains rejection of bad input | — | **Adopt** |
| Graded measurements, not yes/no | qdat_bench, speechocean762 | Finer than binary; shows "almost right" | Harder to annotate consistently | Partly: vowel length yes; overall score optional |
| Speaker facts only in folder names | L2-KSU | — | Not machine-readable; lost on conversion | Avoid: separate speaker table |
| Time-aligned annotation files | L2-ARCTIC, L2-KSU | Needed for phonetic research | Costly; one file per clip | Not now |
| No dataset description | IqraEval pages, several others | — | Users must read a paper to learn the columns | Avoid: full card |
| No predefined split | L2-ARCTIC, L2-KSU, RetaSy | — | Every paper splits differently; results not comparable | Avoid: fixed speaker split |
| Private test labels scored by the owner | Quran Lab benchmark | Nobody can train on the test | Needs the owner to run every submission | Consider later (open question 4) |
| Model's own output shipped with the data | None found | — | — | **Muallim adds this**: no comparable dataset stores what the deployed system answered |

### 3.3 Container formats

| Format | Strengths | Weaknesses | Used by | Role for Muallim |
|---|---|---|---|---|
| **Hugging Face Datasets** (audio folder + metadata table, auto-converted to Parquet) | One-line loading; browser preview with audio; versioning; access can be gated behind accepted conditions; nested fields allowed | Tied to one platform; a non-programmer cannot open Parquet directly | IqraEval, RetaSy, qdat_bench, most sets from Phase 2 | **Publication channel** |
| **JSON Lines manifest + audio files** | Human-readable; one record per line; nested annotations fit naturally; read by NeMo, Lhotse, ESPnet and by Hugging Face itself | No schema enforcement by itself | NVIDIA NeMo, Lhotse; our current export | **Canonical table** |
| **CSV / TSV** | Opens in Excel; simplest for teachers and reviewers | Flat only; Arabic text needs care with encoding; nested labels must be flattened | Common Voice, IqraEval evaluation files, L2-KSU annotation table | **Derived tables** for flat views |
| Kaldi-style directory (`wav.scp`, `text`, `utt2spk`) | Classic toolkits expect it | Several parallel files to keep in sync; no rich metadata | Older ASR recipes | Generate on demand, do not publish |
| Praat TextGrid | Time-aligned labels per sound; standard in phonetics | One file per recording; needs time boundaries we do not annotate | L2-ARCTIC, L2-KSU | Not now; possible later for a hand-aligned subset |
| WebDataset (tar shards) | Efficient streaming of very large sets | Unnecessary below hundreds of hours | Large corpora | Not needed |
| Croissant metadata | Machine-readable dataset description; generated by Hugging Face | Description only, not a data format | Hugging Face, dataset search engines | Comes for free on publication |

**Recommendation.** Keep the current approach and formalise it:

- canonical: `attempts.jsonl` (one attempt per line, nested annotations) + audio files;
- derived from it by script: flat CSV tables and the two benchmark files;
- published on Hugging Face in its audio-folder layout, so that the same files load there without conversion.

Reasons: it is what the project already produces; six of the nine datasets in section 3.1 are published on Hugging Face as audio plus tables; it is readable without code; and gated access on Hugging Face gives a place to require acceptance of usage conditions.

Checked against the Hugging Face documentation [P]: the metadata file must be named `metadata.csv`, `metadata.jsonl` or `metadata.parquet`; it must have a `file_name` column holding the relative path; it must sit in the same folder as the audio or a parent folder; OGG is a supported audio format; folders named after splits define the splits; the hub converts datasets to Parquet automatically up to 5 GB. The layout in section 4 follows these rules. NeMo's manifest layout is stated from general knowledge [?].

---

## 4. Release layout

```
muallim-beginner-arabic/                  (name is a placeholder)
├── README.md                    dataset card: description, datasheet, licence, citation
├── LICENSE
├── CHANGELOG.md                 what changed between releases, incl. removed recordings
├── SHA256SUMS                   checksum of every file
├── data/
│   ├── train/
│   │   ├── metadata.jsonl       attempts of training learners
│   │   └── audio/<speaker>/<attempt_id>.ogg
│   ├── validation/  …           same structure
│   ├── test/        …           same structure
│   └── unlabelled/  …           attempts with consent but no teacher label
├── tables/
│   ├── speakers.csv             one row per learner
│   ├── items.csv                one row per textbook item and curriculum version
│   ├── phonemes.csv             one row per expected sound per annotator
│   ├── marks.csv                one row per teacher mark on a letter cell
│   ├── truth.csv                IqraEval format: ID, Reference_phn, Annotated_phn
│   └── predictions.csv          IqraEval format: ID, Prediction (baseline model)
└── docs/
    ├── annotation-guide.md      the guide annotators followed, with version
    ├── phoneme-inventory.md     symbols used, mapping to IPA
    └── datasheet.md             "Datasheets for Datasets" questions answered
```

- Folder per speaker keeps a learner's files together and makes removal on withdrawal simple.
- Splits and the `unlabelled` part are declared explicitly in the README header as separate configurations, so loading does not depend on folder-name conventions.
- A release is identified by a version (`1.0.0`) and the checksum file. A withdrawn learner's files are removed in the next release and listed in the changelog by speaker code only.

---

## 5. Audio

| Property | Specification | Reason |
|---|---|---|
| File | Original Telegram voice message, OGG container, Opus codec, mono | It is what was recorded; converting to another format cannot add quality and loses the original |
| Derived copy | None stored. Loaders resample to 16 kHz mono on reading; a script produces WAV for toolkits that need it | All models from Phase 1 take 16 kHz mono; storing a second copy doubles size and removal work |
| Editing | None: no trimming, no noise removal, no loudness change | Real conditions are part of the dataset's value; processing choices belong to the user of the data |
| Name | `<attempt_id>.ogg`, where `attempt_id` is the release identifier | The current internal name is a content hash; a release identifier avoids exposing internal keys |
| Recorded per file | Duration, checksum, sample rate and bitrate as decoded | Integrity and filtering |
| Excluded | Recordings without public-release consent; test and stub recordings; recordings of learners under 18 until Phase 5 settles the rule for minors | Rights |

Limitation to state in the card: Opus is a lossy codec. This is how learners will reach any future system through Telegram, so it is representative, but it is not studio audio.

---

## 6. Schema

### 6.1 `metadata.jsonl` — one attempt per line

| Field | Type | Description | Source today |
|---|---|---|---|
| `file_name` | string | Path to the audio, relative to the split folder | new |
| `attempt_id` | string | Release identifier of the attempt | new (not the internal id) |
| `speaker_id` | string | Release code of the learner, e.g. `S017` | new |
| `item_id` | string | Textbook item, e.g. `L020-02` | `attempts.item_id` |
| `curriculum_version` | string | Version of the programme the learner saw | `attempts.curriculum_version` |
| `unit` | string | `letter`, `syllable`, `line`, `word` | `curriculum_items.kind` |
| `lesson_number` | integer | Lesson in book order | `curriculum_items` |
| `reference_text` | string | Arabic text shown to the learner, fully vowelled | `curriculum_items.text` |
| `reference_phonemes` | string | Expected sounds, Quran Phonetic Script | `attempts.reference_phonemes` |
| `reference_variant` | string | Which reading of the ending was used (`wasl` / `waqf`) | `attempts.reference_variant` |
| `duration_ms` | integer | Length of the recording | `attempts.audio_duration_ms` |
| `day_index` | integer | Days since the learner's first attempt | derived from `created_at` |
| `attempt_no` | integer | Which try of this item by this learner (1, 2, …) | derived |
| `model` | object | `version`, `heard_phonemes`, `score`, `verdict`, `phoneme_confidence` (list), `attributes` (list) | `attempts` |
| `detected_errors` | list | What the bot told the learner: `kind`, `position`, `expected`, `heard` | `detected_errors` |
| `annotations` | list | One object per annotator (section 6.2) | `annotations` |
| `verified_phonemes` | string or null | What was actually read: filled only when at least two annotators wrote the same sequence | `consensus_phonemes` |
| `verified_status` | string | `agreed`, `disagreed`, `single_annotator`, `unlabelled`, `unusable`, `off_task` | derived |
| `self_corrected` | boolean or null | The learner made an error and re-read correctly in the same recording | `annotations.self_corrected` |
| `app_version` | string | Version of the bot's code | `attempts.app_version` |
| `consent_version` | string | Version of the public-release consent text the learner accepted | **new** |

### 6.2 `annotations[]` — one object per annotator

| Field | Type | Description |
|---|---|---|
| `annotator` | string | Annotator code (`A1`), never a name |
| `status` | string | `agree` (the bot heard correctly), `fix` (corrected), `audio_unusable`, `off_task` |
| `actual_phonemes` | string or null | What was read, in the same script as the reference |
| `phonemes_source` | string | How the sequence was produced: `typed`, `marks`, `confirmed` (suggested by the bot and accepted), `reference` (marked clean) |
| `blind` | boolean | The annotator did not see the model's answer — **new**, required for the test split |
| `guide_version` | string | Version of the annotation guide |
| `marks` | list | Teacher marks on letter cells (section 6.3) |

### 6.3 `marks[]` — teacher marks on cells

| Field | Type | Description |
|---|---|---|
| `cell` | integer | Number of the cell in reading order, from 0 |
| `char_start`, `char_end` | integer | Position of the piece in `reference_text` |
| `piece` | string | The piece of text as the teacher saw it |
| `kind` | string | Error type (section 8) |
| `heard` | string or null | What was produced there, where the type has such an answer |
| `bot_flagged` | boolean | Whether the bot had flagged this cell |

### 6.4 `speakers.csv`

| Field | Values | Note |
|---|---|---|
| `speaker_id` | `S001`… | Assigned for the release, in random order; the link to internal records is kept privately |
| `split` | `train`, `validation`, `test`, `unlabelled` | One split per speaker |
| `age_group` | `18_24`, `25_34`, `35_44`, `45_54`, `55_plus` | Coarse bands only |
| `gender` | `m`, `f` | |
| `native_language` | `ru`, `kk`, `tt`, `other` | |
| `arabic_reading_at_start` | `none`, `some_letters`, `slow_syllables`, `fluent` | Self-reported level before starting |
| `attempts`, `items`, `active_days` | integers | Activity summary |

Not published: name, Telegram identifier, the internal learner code, exact dates and times, time zone, and the questionnaire answer about prayer (religious practice is sensitive data and is not needed to use the dataset).

### 6.5 `items.csv`

`curriculum_version`, `item_id`, `lesson_number`, `position`, `unit`, `reference_text`, `book_page`, `book_line`, `verified` (checked by a person against the book).

### 6.6 Identifiers

| Identifier | Rule |
|---|---|
| `speaker_id` | New code per release family, not derived from any internal value. The present learner code is computed from the internal id, so it must not be published. |
| `attempt_id` | `<speaker_id>-<running number>`, e.g. `S017-0042`; stable across releases |
| Withdrawal | The private mapping lets us find and remove a learner's files; published codes are never reused |

---

## 7. Text and transcription layers

| Layer | Field | Who produces it | Rule |
|---|---|---|---|
| Reference text | `reference_text` | The textbook, entered and checked by a person | Fully vowelled Arabic exactly as shown to the learner. Unicode normalisation form NFC. No added or removed marks. |
| Reference sounds | `reference_phonemes` | The phonetiser from the reference text | Stored with the version that produced it (inside `model.version`). Never edited by hand. |
| Model answer | `model.heard_phonemes` | The model | Stored raw, with per-sound confidence. |
| Verified transcription | `annotations[].actual_phonemes`, `verified_phonemes` | Teachers | Each annotator's sequence is kept. The verified field is filled only on agreement of at least two. Disagreements stay visible, they are not resolved silently. |

Diacritics:

- vowel signs, sukun, shadda and tanwin are always kept, in the reference text and in every sound sequence;
- a derived column without diacritics may be generated for users of ordinary ASR tools, but it is not stored as a source field.

Sound inventory:

- **primary:** the Quran Phonetic Script already used by the bot and by the Muaalem model and its relatives (Phase 1);
- **published mapping:** a table from each symbol to IPA and, where one exists, to the 68-symbol set of the IQRA benchmark, in the dataset's own `phoneme-inventory.md` (planned, see the tree above). This lets other groups score models that use a different inventory;
- sounds outside Arabic (a Russian substitute) need a symbol. Proposal: one reserved symbol for "non-Arabic sound" plus a free-text note; a finer inventory can be added after the first labelled batch shows which substitutes actually occur.

Time alignment: not annotated by hand. If automatic alignments are added later, they go into a separate field marked as automatic.

---

## 8. Pronunciation error labels

Two existing sets are kept as they are. Both were designed in the project before this phase.

| Set | Values | Where |
|---|---|---|
| Errors found by the system | `letter_substitution`, `vowel_substitution`, `sound_substitution`, `fragment_substitution`, `madd_too_short`, `madd_too_long`, `vowel_missing`, `shadda_missing`, `sound_missing`, `extra_sound` | `detected_errors[].kind` |
| Marks placed by teachers | Main: `letter`, `missing`, `vowel`, `extra`, `shadda`, `sukun`, `madd`. Other: `tafkhim`, `ghunna`, `qalqala`, `halting`, `wrong_stop` | `marks[].kind` |

Derived for every expected sound (table `phonemes.csv`): `expected`, `model_heard`, `human_heard`, and the outcome — correct acceptance, correct rejection, false alarm, missed error — the same four outcomes the IQRA benchmark and L2-KSU use.

Recording-level outcomes: `audio_unusable` and `off_task` stay in the dataset with their audio. Phase 2 showed that a quarter of labelled crowd recordings in a comparable dataset were invalid; a system must learn to recognise them.

---

## 9. Annotation guidelines

The project has an annotation guide with versions. For a public dataset it should state the following explicitly (most of it exists; items marked **new** do not):

| Topic | Rule |
|---|---|
| What is labelled | What was actually pronounced, not whether the reading "deserves a pass" |
| Reference point | The expected sound sequence; the annotator corrects it where the learner deviated |
| Uncertainty | "Not sure" is allowed and recorded; unclear audio is `audio_unusable`, not a guess |
| Self-correction | Marked separately; such attempts are excluded from headline figures |
| Hesitation, restart | Marked as `halting`; not an articulation error |
| Number of annotators | At least two per attempt in the test split |
| Blind labelling | **new as a recorded field:** test-split labels are produced without seeing the model's answer |
| Agreement | Reported per release: Krippendorff's α and Cohen's κ, per error type where numbers allow |
| Disagreement | Kept in the data; a joint review may add a third label but does not delete the first two |
| Annotator description | Published per code: qualification in tajwid, first language, hours of training — **new** |
| Non-Arabic sounds | Reserved symbol plus note — **new** |

---

## 10. Splits

| Rule | Specification |
|---|---|
| Unit of splitting | The learner. All attempts of one learner are in one split. |
| Proportions | About 70 % of learners for training and validation together, 30 % for test, as already decided in ADR-0051 |
| Stratification | By first language and by activity level, so that the test part is not all short-lived or all very active learners |
| Freezing | The test list of speakers is fixed before any model is trained and published with its checksum |
| Validation | Taken from the training learners by cross-validation over learners; a fixed validation list is published for convenience |
| Unlabelled | Attempts with consent but without teacher labels are published separately for self-supervised use |
| Text overlap | The same textbook items occur in every split. This is unavoidable and intended: the task is to judge new *speakers* reading known text. The card must say so. |
| New releases | Learners never move between splits. New learners are assigned by the same rule. |

With 20–40 learners the test part holds 6–12 speakers. Every reported figure needs a confidence interval computed over speakers.

---

## 11. Example records

Text and item identifiers below are real items of the programme (source SRC-040). The sound sequences, scores and labels are **illustrations of the format**, not data.

**A. Syllable read correctly; two annotators agree.**

```json
{"file_name": "audio/S017/S017-0042.ogg", "attempt_id": "S017-0042", "speaker_id": "S017",
 "item_id": "L020-02", "curriculum_version": "2026.11.08-book-7", "unit": "syllable",
 "lesson_number": 20, "reference_text": "صَ", "reference_phonemes": "صَ",
 "reference_variant": "waqf", "duration_ms": 1480, "day_index": 9, "attempt_no": 2,
 "model": {"version": "quran-muaalem 0.2.2 @01a1ef9", "heard_phonemes": "صَ", "score": 100,
           "verdict": "excellent", "phoneme_confidence": [0.97, 0.97]},
 "detected_errors": [],
 "annotations": [
   {"annotator": "A1", "status": "agree", "actual_phonemes": "صَ", "phonemes_source": "reference",
    "blind": true, "guide_version": "2.1", "marks": []},
   {"annotator": "A2", "status": "agree", "actual_phonemes": "صَ", "phonemes_source": "reference",
    "blind": true, "guide_version": "2.1", "marks": []}],
 "verified_phonemes": "صَ", "verified_status": "agreed", "self_corrected": false,
 "app_version": "0.2.0+a1b2c3d", "consent_version": "public-1"}
```

**B. Same item; the learner produced a plain "s" instead of the emphatic one; the model caught it; both teachers confirm.**

```json
{"file_name": "audio/S017/S017-0041.ogg", "attempt_id": "S017-0041", "speaker_id": "S017",
 "item_id": "L020-02", "curriculum_version": "2026.11.08-book-7", "unit": "syllable",
 "lesson_number": 20, "reference_text": "صَ", "reference_phonemes": "صَ",
 "reference_variant": "waqf", "duration_ms": 1320, "day_index": 9, "attempt_no": 1,
 "model": {"version": "quran-muaalem 0.2.2 @01a1ef9", "heard_phonemes": "سَ", "score": 50,
           "verdict": "failed", "phoneme_confidence": [0.81, 0.95]},
 "detected_errors": [{"kind": "letter_substitution", "position": 0, "expected": "ص", "heard": "س"}],
 "annotations": [
   {"annotator": "A1", "status": "agree", "actual_phonemes": "سَ", "phonemes_source": "marks",
    "blind": true, "guide_version": "2.1",
    "marks": [{"cell": 0, "char_start": 0, "char_end": 2, "piece": "صَ", "kind": "letter",
               "heard": "س", "bot_flagged": false}]},
   {"annotator": "A2", "status": "agree", "actual_phonemes": "سَ", "phonemes_source": "typed",
    "blind": true, "guide_version": "2.1", "marks": []}],
 "verified_phonemes": "سَ", "verified_status": "agreed", "self_corrected": false,
 "app_version": "0.2.0+a1b2c3d", "consent_version": "public-1"}
```

**C. A letter line; the recording is too noisy to judge.**

```json
{"file_name": "audio/S004/S004-0007.ogg", "attempt_id": "S004-0007", "speaker_id": "S004",
 "item_id": "L007-05", "curriculum_version": "2026.11.08-book-7", "unit": "letter",
 "lesson_number": 7, "reference_text": "تَ تِ تُ", "reference_phonemes": "تَتِتُ",
 "reference_variant": "waqf", "duration_ms": 5210, "day_index": 0, "attempt_no": 1,
 "model": {"version": "quran-muaalem 0.2.2 @01a1ef9", "heard_phonemes": "تَ", "score": 33,
           "verdict": "failed", "phoneme_confidence": [0.42, 0.51]},
 "detected_errors": [{"kind": "sound_missing", "position": 2, "expected": "تِ", "heard": ""}],
 "annotations": [
   {"annotator": "A1", "status": "audio_unusable", "actual_phonemes": null, "phonemes_source": null,
    "blind": true, "guide_version": "2.1", "marks": []}],
 "verified_phonemes": null, "verified_status": "unusable", "self_corrected": null,
 "app_version": "0.2.0+a1b2c3d", "consent_version": "public-1"}
```

**`speakers.csv`**

```
speaker_id,split,age_group,gender,native_language,arabic_reading_at_start,attempts,items,active_days
S004,test,25_34,f,kk,none,212,96,31
S017,train,35_44,m,ru,some_letters,548,240,57
```

---

## 12. Gaps between today's export and this specification

| # | Gap | What is needed | Who decides |
|---|---|---|---|
| 1 | Consent covers storing recordings for research, not publishing them | A separate consent kind and text version for public release; only attempts made after it are publishable | Author (Phase 5) |
| 2 | Published learner code is derived from the internal id | Release speaker codes with a private mapping | Author; small code change |
| 3 | Questionnaire holds religious practice and an under-18 band | Leave out of the release; rule for minors | Author (Phase 5) |
| 4 | Exact timestamps are exported | Replace by day index and attempt number | Agent may implement after approval |
| 5 | No split assignment | Speaker-level split table, frozen and checksummed | Author with supervisor (ADR-0051) |
| 6 | "Blind" labelling is a procedure, not a stored field | Store whether the annotator saw the model's answer | Schema change — author |
| 7 | No dataset card, licence, inventory mapping, checksums | Write them; licence choice in Phase 5 | Author |

Smaller items: a symbol for non-Arabic sounds; annotator descriptions; item table export; `verified_status` field.

---

## 12a. Critical analysis of the project's current data design (revision 2)

### Strong — keep

| Feature | Why it is strong | Comparison |
|---|---|---|
| Model answer, raw confidence and versions stored with every attempt | Any later model can be compared on identical audio; decisions can be traced | Not found in any dataset of section 3.1 |
| Label history kept; last label per annotator used | Corrections do not destroy evidence | Only RetaSy and speechocean762 keep per-annotator labels |
| Marks on letter cells with position in the text | A teacher can label without knowing a phonetic script | Not found elsewhere |
| How each sound sequence was produced (`phonemes_source`) | Separates hand-entered labels from ones suggested by the bot — important because suggested labels inherit the model's bias | Comparable only to RetaSy's `golden` flag |
| Self-correction as its own category | Beginners restart often; mixing these with errors distorts figures | Not found elsewhere |
| Snapshot of the programme per version | The text the learner saw can always be recovered | Not applicable to fixed-prompt corpora |

### Weak — fix before publication

| Weakness | Risk | Proposal |
|---|---|---|
| Labels confirmed from the bot's suggestion count as teacher labels | Agreement with the model is inflated; the "canonical bias" of Phase 1 enters the truth | Publish `phonemes_source`; compute headline figures on blind labels only |
| No stored fact that a label was blind | The test set's independence cannot be shown to a reviewer | Add the field (gap 6) |
| Published learner code derivable from the internal id | Re-identification by anyone with database access | Release codes (gap 2) |
| Score and verdict depend on thresholds that changed over time | Users may read `verdict` as ground truth | Keep `policy` with each attempt and state in the card that the verdict is the system's output, not a label |
| No native or expert control recordings of the same items | "Correct" on our material and channel is undefined; no references for comparison methods | Add a control group (Phase 2, section 5a) |
| One symbol set tied to one model family | Other groups cannot score their models | Publish the mapping table (section 7) |

### Proposals

**Add to the schema**

- `blind` per annotation; `consent_version` per attempt; `verified_status`; release identifiers.
- A `speaker_type` value in `speakers.csv`: `learner` or `control`.
- Optionally an overall teacher score per attempt, as in speechocean762 — only if the author accepts it as part of the methodology.
- Exact counts in the card: recorded, consented, labelled, agreed.

**Remove from the public release**

- The questionnaire answer about prayer; exact timestamps; time zone; internal identifiers; names.
- Attempts scored by the stub model; recordings without public-release consent.
- The under-18 band, until Phase 5 decides.

**Keep internal, do not publish**

- The mapping between release codes and learners; annotators' Telegram identifiers; the deletion journal.

**Do not build now**

- Time-aligned annotation, tar-shard packaging, a second audio copy. None is needed at this size, and each adds work on every withdrawal.

---

## 13. What the structure supports

| Use | Supported by |
|---|---|
| Evaluating error detection of any model | `reference_phonemes` + `verified_phonemes` + the benchmark files; any model's output can be scored against the same truth |
| Comparing with published benchmarks | `truth.csv` / `predictions.csv` in IqraEval layout; inventory mapping |
| Fine-tuning a sound-level model | Audio + `verified_phonemes` of training learners; `phonemes_source` lets a user keep only hand-entered labels |
| Training a letter-and-vowel classifier (Stage I) | `unit` = `letter` / `syllable` with `reference_text` as class and `verified_status` as correctness |
| Training a verifier on top of a model | `model.phoneme_confidence`, `attributes`, and per-sound outcomes |
| Ordinary ASR training | Audio + `reference_text` or its undiacritized derivative, for attempts verified as correctly read |
| Reference-comparison methods (Phase 1, section 3.10) | Correct attempts per item serve as additional references |
| Learning-curve research | `speaker_id`, `item_id`, `attempt_no`, `day_index` |
| Fairness analysis | `gender`, `age_group`, `native_language` |

---

## 14. Limitations

- Not validated by running models (Phase 3 skipped). In particular, whether one reserved symbol for non-Arabic sounds is enough is unknown.
- The example records show format only.
- The Hugging Face layout rules were checked in its documentation (section 3.3); the layout itself has not been test-uploaded.
- The L2-KSU paper could not be read, so its annotation procedure is known only from the dataset card.
- Voice recordings cannot be made anonymous. Codes and coarse bands reduce the risk of identifying a learner; they do not remove it.
- With few learners, a combination such as "female, 55+, Tatar" may identify one person. Rare combinations may need merging into `other` before release.
- Whole-surah readings (a separate part of the bot's data) are outside this specification.

---

## 15. Open questions

1. Which licence will the dataset carry? Related datasets are mostly non-commercial; the choice affects who can use ours. (Phase 5.)
2. May recordings made under the earlier consent be published after the learner accepts the new one, or only later recordings?
3. Are learners under 18 excluded, or included with a guardian's consent?
4. Is one dataset with gated access enough, or should the test labels be withheld and scored on request, as the Quran Lab benchmark does?
5. Who are the annotators for the frozen test split, and how many attempts can they label?
6. Should a small subset receive hand-made time alignment for phonetic research?

---

## 16. Recommendations for Phase 5

1. Design the public-release consent first; gaps 1–3 depend on it and nothing can be published without it.
2. Decide the withdrawal procedure together with the release cycle: a withdrawn learner disappears from the next release, but copies already downloaded cannot be recalled — the consent text must say this plainly.
3. Use gated access with usage conditions (no attempt to identify speakers, no voice cloning) as part of the licence design.
4. Settle the rule for minors before the pilot, since the questionnaire already has an under-18 band.
5. Reconcile with ADR-0085 (proposed: no consent screen, learner shown by name to the teacher). A public dataset requires an explicit, recorded agreement, which that proposal removes.

---

## Sources

- Project: `docs/data/data-dictionary.md`, `src/muallim/research/dataset.py`, `docs/research/annotation-formats.md`, ADR-0051, ADR-0052, ADR-0079, ADR-0080, ADR-0085
- `PHASE_1_ASR_RESEARCH.md`, `PHASE_2_DATASET_RESEARCH.md` (this folder)
- Gebru et al. Datasheets for Datasets. Communications of the ACM, 2021 (SRC-123)
- Zhao et al. L2-ARCTIC. Interspeech 2018 (SRC-063) — expected-versus-produced annotation
- IQRA 2026 Interspeech Challenge. arXiv:2603.29087 (SRC-031); evaluation file layout (SRC-066)
- Salameh et al. Quranic Audio Dataset. arXiv:2405.02675 (SRC-032) — invalid-audio categories, agreement reporting
- https://huggingface.co/datasets/IWAN/L2-KSU-Dataset — annotation table and folder layout
- https://huggingface.co/datasets/Quran-Lab/quran-tajweed-benchmark — private test labels, speaker-held-out design
- speechocean762 — https://huggingface.co/datasets/mispeech/speechocean762; arXiv:2104.01378 — https://arxiv.org/abs/2104.01378
- L2-ARCTIC corpus page — https://psi.engr.tamu.edu/l2-arctic-corpus/
- Hugging Face Hub documentation, audio datasets — https://huggingface.co/docs/hub/datasets-audio
- https://huggingface.co/datasets/RetaSy/quranic_audio_dataset · https://huggingface.co/datasets/obadx/qdat_bench · https://huggingface.co/datasets/IqraEval/Iqra_train · https://huggingface.co/datasets/sobolev210/quran-recitation-errors · https://huggingface.co/datasets/Reinjin/Pelafalan_Huruf_Hijaiyah
- Common Voice column layout — https://pytorch.org/audio/main/_modules/torchaudio/datasets/commonvoice.html
