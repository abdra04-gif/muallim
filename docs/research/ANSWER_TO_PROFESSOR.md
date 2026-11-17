# Muallim — answer on speech models, dataset format and public consent

**Project:** Muallim, a Telegram reading trainer for the textbook *al-Muallim ath-Thani*. Learners are Russian-speaking adults who start Arabic reading from zero.
**Date:** 2026-11-17
**Scope:** the three questions of the technical task. Details and sources are in the attached reports (list at the end).

---

## Short answers

| Question | Answer |
|---|---|
| 1. Which models or solutions can transcribe beginner audio? | **None is proven for our learners.** No model, open or commercial, has published results on adults who start from zero, or on Russian- or Kazakh-speaking learners. The best-supported design is a phoneme model without a language model, checked sound by sound against the known text. Our own first test on single letters shows that free transcription is right in only 39–50 % of clips, so Stage I of the book needs a different mechanism. |
| 2. What is the dataset format? | One record per attempt (one voice message, one textbook item). Original audio plus one JSON Lines table, published on Hugging Face in its audio-folder layout. Three transcription layers kept apart: expected, heard by the model, verified by teachers. Split by learner. |
| 3. How do we make the public release clear to learners? | One screen before the first recording. Its title and its main button both say that recordings will be published. A second button lets a person practise without recording. Telegram's own rules require this kind of consent, so it is not optional. A draft text is ready for approval. |

Nothing in the bot, its database or its learner-facing texts was changed. Every item below that needs a decision is listed in section 5.

---

## 1. Models and solutions

### 1.1 What the task is

A learner reads a text that we already know: a letter with a vowel sign, a syllable, a word. The system must report which sounds were actually produced, including the wrong ones. This is mispronunciation detection and diagnosis, not ordinary speech recognition. Ordinary recognisers are built to output the most likely word, so they hide the errors we need to see.

### 1.2 What exists

About forty models and services were examined in papers, model cards and catalogues. They fall into seven families.

| Family | Examples | Shows wrong sounds | Vowel signs | Evidence on real learners | Verdict for Muallim |
|---|---|---|---|---|---|
| A. Arabic phoneme models, no language model | Muaalem (the bot's model), Quran Lab TajweedFormer V4, `Hisnlabs/tajweed-v2`, IQRA 2026 systems, `nrshoudi`, `MostafaMaroof` | Yes | Yes | One model only (Quran Lab) | **Core of the design** |
| B. Text recognisers that write vowel signs | NVIDIA FastConformer Arabic, Tarteel Whisper | Partly | Yes | None | Control |
| C. General Arabic recognisers | Whisper, OmniASR, Qwen3-ASR | No | No | None | Control only |
| D. Language-independent phone recognisers | XLSR-espeak, ZIPA | Yes | Vowel quality | None for Arabic | Second opinion for non-Arabic sounds |
| E. Commercial pronunciation services | Azure Pronunciation Assessment | Score only | Unknown | One small study | Not recommended |
| F. Audio language models | Gemini and others, zero-shot | Weak | Weak | Negative | Not recommended |
| G. Methods without a recogniser | Closed-set letter classifier; comparison with a teacher's recording | Says "how far", not "which sound" | — | English and Japanese only | **Promising for Stage I** |

### 1.3 Findings that decide the choice

1. **No published result covers our population.** The organisers of the main Arabic benchmark (IQRA 2026) state that collecting learner data is future work.
2. **The best documented system misses more than half of real learner errors.** Quran Lab's TajweedFormer V4 is the only model with numbers on real learners. At a low false-alarm rate it catches 46 % of consonant errors of non-native speakers (L2-KSU) and 32 % of vowel errors corrected by teachers. These figures are self-reported.
3. **Error rates below 2 % are all measured on professional reciters.** On amateurs, phone audio or unseen reciters the same models show 4–9 %.
4. **"Canonical bias" is documented by model authors themselves.** A model trained on correct recitation tends to output what the rule says, not what was said. One model reported the expected sound in 81 of 94 clips where annotators heard something else.
5. **Single letters are a known weak point.** On the Horouf corpus of single vowelled letters, an off-the-shelf Arabic model reached 35–37 % accuracy. Stage I of the textbook is exactly this material.
6. **Small amounts of real error data help more than large synthetic sets.** At IQRA 2026, 1,333 real mispronounced utterances helped the top systems more than 55,400 synthetic ones. This supports collecting our own dataset.
7. **Licences split the field.** Permissive: Muaalem (MIT), `tajweed-v2`, NVIDIA, Whisper, ZIPA. Restricted: Quran Lab (no charging for any feature the model powers), the IQRA baseline encoder, MMS, SeamlessM4T (non-commercial). The thesis has a business part, so this matters.

### 1.4 How existing Arabic solutions are built

Ten approaches were found in products and papers, from the HAFSS system of 2006 to models of November 2026. Three points recur.

- **The text is known in advance, and good systems use it.** They do not transcribe freely and then compare. They score each expected sound against its likely alternatives. HAFSS did this in 2006 with 663 hand-written error rules.
- **Good systems allow the answer "not sure".** HAFSS had four responses by confidence. A confident verdict on every sound is not achievable today.
- **The widely used product (Tarteel) works at word level** and has no public interface. An independent review (arXiv:2510.12858) found no product with published accuracy on learners.

### 1.5 Our own test (Phase 3, preliminary)

We ran five systems on the same 840 clips of single vowelled letters: 28 letters × 3 vowel signs × 10 different speakers. The clips come from `Reinjin/Pelafalan_Huruf_Hijaiyah`, recorded by students of an Indonesian boarding school. All runs were on a MacBook Air M1 with 8 GB of memory.

For each clip we checked whether the first consonant and the first vowel in the system's output match the letter and vowel the student was asked to read.

| System | Kind | Letter right | Vowel right | Both right | Seconds per clip |
|---|---|---|---|---|---|
| `MostafaMaroof/wav2vec2-arabic-phoneme-asr` | Arabic phoneme model | 65.7 % | 74.2 % | **50.0 %** | 0.22 |
| `facebook/wav2vec2-xlsr-53-espeak-cv-ft` | Universal phone recogniser | 59.9 % ¹ | 65.4 % | 49.6 % ¹ | 0.19 |
| `obadx/muaalem-model-v3_2` | Arabic phoneme model — **the bot's model** | 50.4 % | 71.5 % | 39.4 % | 0.17 |
| `tarteel-ai/whisper-base-ar-quran` | Text recogniser with vowel signs | 48.0 % | 50.5 % | 24.5 % | 0.73 |
| `openai/whisper-small` | General recogniser | 51.3 % | 0.4 % | 0.1 % | 1.52 |

¹ Over 24 letters. This model has no symbols for the four emphatic letters (ص ض ط ظ): it writes them as plain `s`, `d`, `t`, `z`.

What this shows:

- **No system recognises a single vowelled letter reliably.** The best gets letter and vowel both right in half of the clips.
- **The bot's present model is not the best on this material.** It was trained on verses read by professional reciters, and a one-second clip of one letter is far from that.
- **The bot's model hears a long vowel where the learner holds a short one.** In 411 of 840 clips it wrote the vowel as long. A beginner who pronounces a letter slowly and clearly would be told that the vowel is too long.
- **Confusions follow phonetics.** Emphatic and plain consonants (ض→د, ط→ت, ظ→ز), voiced and voiceless (د→ت), and ث→س are the most frequent. These are also the errors a learner makes, so the model is weakest exactly where we need it.
- **Text recognisers turn sounds into words.** Whisper wrote a vowel sign in 3 of 840 clips, so it cannot see vowel errors at all; it answered with words such as «نعم» and «لا» and, in about a third of the clips, with one letter repeated until the length limit. The Quran-trained Whisper wrote vowel signs in about half of the clips and often produced a real word (فِي, ذُو, طه) instead of the letter.
- **Speed is not a constraint.** Phoneme models need about 0.2 seconds per clip on a laptop.

**Limits of this test — it must not be quoted as an evaluation of our learners.**

- The dataset has no "correct / incorrect" label. When the output differs from the class, we cannot tell whether the model misheard or the student mispronounced. The figures are a lower bound on model accuracy, not a measurement of it.
- The speakers are Indonesian school students, not Russian-speaking adults.
- 840 of 8,904 clips were used.
- Each system was used as published, without adaptation.

### 1.6 Recommended design

No single model fits. The material has two shapes, and the evidence points to a different mechanism for each.

| Material | Mechanism | Why |
|---|---|---|
| Stage I: one letter or syllable with a vowel sign | Verification, not transcription: a closed-set classifier over the 84 possible answers, comparison with the teacher's recording, and a score of the expected sound against its alternatives | Free transcription fails on this material in the literature (35–37 %) and in our test (39–50 %). The answer set is small and known |
| Stage II: words and lines | Phoneme model without a language model, each sound verified against the reference, separate threshold per error type | Recommended independently by three model authors; the only approach with learner numbers |
| Both | A "not sure" outcome; several recognisers run silently on the same recordings so they can be compared | The best system catches 32–46 % of real errors |

The existing architecture of the bot already allows this: the recogniser sits behind a replaceable interface, and the raw model output is stored with every attempt.

**The decisive step is our own data.** Until teacher-labelled recordings of our learners exist, no model can be chosen on evidence. The first labelled batch from the pilot is the real Phase 3.

---

## 2. Dataset format

### 2.1 What exists and what is missing

Nine comparable datasets were compared by structure, labels and licence. None combines adult beginners from zero, single letters and syllables with vowel signs, real errors, and sound-level labels.

| Dataset | Why it does not replace ours | Use for us |
|---|---|---|
| L2-KSU | 40 non-native speakers, but African students who already study Arabic, reading ten full sentences. Licence forbids derivative works (CC BY-NC-ND 4.0) | External test for consonant errors |
| RetaSy | 6,828 recordings, of which 938 are from Russia, Kazakhstan, Uzbekistan and neighbouring countries. One label per recording; no licence stated | Evidence that our learners' first languages occur; possible cooperation |
| `Reinjin` letters | Same material as Stage I, but no error labels and no documentation | Training a letter classifier; used in our test |
| IQRA 2026 sets | Errors are staged by native speakers or synthetic | Format model; benchmark comparison |
| speechocean762, L2-ARCTIC | English | Models for label structure |

The field's benchmarks are small: the main Arabic error test set has 1,643 utterances. A Muallim dataset of 20–40 learners and a few thousand attempts is of comparable size.

**Contribution.** The first open dataset that follows the same beginners through a graded textbook, from single letters to words, with teacher-verified sound-level labels and with the deployed system's own answer stored beside each recording. No dataset found stores the last item.

### 2.2 The format

| Element | Specification |
|---|---|
| Unit | One attempt: one voice message in which one learner reads one textbook item |
| Audio | The original Telegram voice message (OGG, Opus, mono), unedited. Loaders resample to 16 kHz |
| Canonical table | `metadata.jsonl`, one attempt per line, nested annotations |
| Derived tables | `speakers.csv`, `items.csv`, `phonemes.csv`, `marks.csv`, and `truth.csv` / `predictions.csv` in the IQRA benchmark format |
| Publication | Hugging Face audio-folder layout, converted to Parquet automatically; access behind accepted usage terms |
| Splits | By learner, never by recording. Test speakers fixed before any training. About 30 % of learners in the test part |
| Versions | Each release is rebuilt from current consents, with checksums and a changelog of removed recordings |

Three transcription layers are stored separately and never overwrite each other:

| Layer | Field | Produced by |
|---|---|---|
| What should be read | `reference_text`, `reference_phonemes` | The textbook, checked by a person |
| What the system heard | `model.heard_phonemes` with per-sound confidence | The model |
| What was actually read | `annotations[].actual_phonemes`, `verified_phonemes` | Teachers; filled as verified only when at least two agree |

Main fields of one record: `attempt_id`, `speaker_id` (release code such as `S017`), `item_id`, `curriculum_version`, `unit` (letter, syllable, word, line), `reference_text`, `reference_phonemes`, `duration_ms`, `attempt_no`, `model`, `detected_errors`, `annotations`, `verified_status`, `consent_version`. Each annotation records whether the teacher labelled without seeing the model's answer (`blind`), which the test part requires.

Speaker table: coarse age band, gender, first language, self-reported reading level at start. Not published: name, Telegram identifier, exact dates, and the questionnaire answer about prayer.

### 2.3 State of the project

The bot already stores most of this: every attempt with reference, model answer, versions and teacher labels, and an export in the benchmark format. Seven gaps separate the present export from a publishable dataset. The main ones:

1. no record of consent to **public** release;
2. the present learner code is derived from an internal identifier and must not be published;
3. no train / test assignment;
4. no dataset card, licence or checksums;
5. no symbol for a sound that is not Arabic (a Russian substitute).

---

## 3. Consent to public release

### 3.1 Why it is mandatory

Telegram's Bot Platform developer terms prohibit "any form of data collection aimed at creating large datasets, machine learning models". The one exception: data that users submit themselves may be used if the purpose is stated clearly and the user gives "individual, explicit, active and revocable consent". Violation can end the bot.

Consequences:

- A notice line without a button is not enough. An earlier project proposal to drop the consent screen cannot be combined with a public dataset.
- The present consent text says that recordings are heard "only by researchers". Recordings made under it cannot be published unless the learner accepts the new text.

### 3.2 What the learner must understand

| Fact | How the screen says it |
|---|---|
| The recordings will be published | In the title and again on the button |
| Anyone can download them, in any country | "Any researcher in any country will be able to download and listen to them" |
| A voice is not anonymous | "Your voice is you. Someone who knows you may recognise you" |
| Publication cannot be fully undone | "Copies that someone has already downloaded cannot be taken back" — stated before the button |
| Agreement is voluntary | A second button: practise without recording |

### 3.3 Draft screen (English version; the bot will show it in Russian)

> 🎙 **Your recordings will become part of an open dataset**
>
> This bot is part of a research project. We collect recordings of beginners reading so that researchers can make such programs more accurate.
>
> **If you press "Continue":**
> • Your voice messages with reading are saved.
> • They will be **published on the internet** in a research dataset. Any researcher in any country will be able to download and listen to them.
> • Published with each recording: what you read, the errors found by the bot and by a teacher, your age group, gender and first language.
> • **Not published:** your name, Telegram account, phone number.
>
> **Important:**
> • Your voice is you. Someone who knows you may recognise you in a recording.
> • You can change your mind at any time: /privacy. We will delete the recordings from our storage and from future versions of the dataset. Copies that someone has already downloaded cannot be taken back.
> • Only recordings of people aged 18 or over are published.
>
> You can also practise without recording — the bot will work the same way.
>
> [ ✅ Continue — I agree to publication ]
> [ Practise without recording ]
> [ More details ]

The Russian text is in the Phase 5 report, section 7.1. It is a draft: it has not been put into the bot.

### 3.4 Options considered

| Option | Assessment |
|---|---|
| A. Notice line, no button | Not acceptable: not "explicit" or "active" |
| B. "Continue" is the only way to use the bot | Possible, but consent tied to access can be challenged as not freely given |
| **C. "Continue" = publication, plus a smaller "Practise without recording"** | **Recommended**: one screen, clearly voluntary, meets Telegram's wording |
| D. Two separate consents (research, then publication) | Good, but two questions for a beginner |

### 3.5 What stands behind the button

- **Three states per learner:** not answered (no recording is processed), practice only (nothing stored), public release.
- **Rules in code:** no audio is written before consent; a recording is publishable only if consent was valid when it was made; a changed text asks again; learners under 18 or with no age answer are never published.
- **Withdrawal:** recording stops at once; audio and labels are deleted from our storage; the next release omits the speaker; registered users of the dataset are told which speaker code to delete. We say honestly that copies already taken cannot be recalled.
- **Access to the dataset:** Hugging Face gated access. Users accept terms that forbid identifying speakers, cloning voices and redistributing the audio, and oblige them to honour removals. This also gives us the list of users to notify.
- **Minors:** may use the bot; their recordings are not published. A Telegram bot cannot verify a parent's consent.
- **Privacy policy:** Telegram requires one registered for the bot.

### 3.6 Legal questions that remain open

The findings on law come from commentary by law firms, not from official texts, and they disagree on details. They show which questions must be answered:

- Commentary on Kazakhstan's law says personal data must be stored on servers in Kazakhstan. Commentary on Russia's law says first collection of Russian citizens' data must be in a database in Russia.
- Publication on Hugging Face is a transfer abroad. The consent names it.
- Reading aloud from a religious primer may reveal religious affiliation, so the whole dataset should be treated as sensitive.

This is not legal advice. The university's ethics body must confirm the consent text and the hosting country before the pilot.

---

## 4. What was and was not done

| Phase | State | Report |
|---|---|---|
| 1. Speech models | Done, desk research with sources; three revisions | `PHASE_1_ASR_RESEARCH.md` |
| 2. Datasets | Done, desk research with sources; L2-KSU's Springer paper could not be opened | `PHASE_2_DATASET_RESEARCH.md` |
| 3. Experiments | **Preliminary only:** five systems on public letter recordings. No test on our learners, because no labelled recordings of them exist yet | `PHASE_3_EXPERIMENTAL_RESULTS.md` |
| 4. Dataset specification | Done as a proposal | `PHASE_4_DATASET_SPECIFICATION.md` |
| 5. Architecture and consent | Done as a proposal | `PHASE_5_ARCHITECTURE_AND_CONSENT.md` |
| Extra: how Arabic solutions are built | Done | `SOLUTIONS_ARABIC.md` |

Not tested, and why: Quran Lab TajweedFormer V4 (licence decision and server access), Azure and Gemini (learner audio would leave our server), L2-KSU (access request not yet sent), comparison with teacher recordings and the letter classifier (next step).

---

## 5. Decisions needed

| # | Question | Recommendation |
|---|---|---|
| 1 | Consent model | Option C: "Continue" means publication; a second button allows practice without recording |
| 2 | Wording of the consent screen | Approve or correct the draft in section 3.3 |
| 3 | Licence of the dataset | Gated access with usage terms for audio; CC BY 4.0 for labels and tables |
| 4 | Learners under 18 | May use the bot; recordings not published |
| 5 | Ethics approval | Which body at the university reviews the consent text and the study |
| 6 | Hosting country | Depends on where learners live; decides which law applies |
| 7 | Quran Lab models | Their licence forbids paid features. Use for research comparison only, or not at all? |
| 8 | Contacts | May we write to the authors of RetaSy, Horouf and Quran Lab for data access? RetaSy's authors overlap with authors of sources attributed to your group |
| 9 | Order of work | Proposed: consent screen → pilot recordings → teacher labels → model comparison on our own data |

---

## 6. Attached documents

| File | Content |
|---|---|
| `PHASE_1_ASR_RESEARCH.md` | Models and services in seven families, evidence on learner speech, licences, strengths and weaknesses, shortlist |
| `PHASE_2_DATASET_RESEARCH.md` | Datasets found, L2-KSU in detail, RetaSy by country, critical analysis, Muallim's contribution |
| `PHASE_3_EXPERIMENTAL_RESULTS.md` | The letter test: method, results per letter and vowel, speed, difficulties, how to repeat it |
| `PHASE_4_DATASET_SPECIFICATION.md` | Release layout, full schema, transcription layers, error labels, annotation rules, splits, example records |
| `PHASE_5_ARCHITECTURE_AND_CONSENT.md` | Architecture, Telegram and legal requirements, consent options, draft text in Russian and English, withdrawal, privacy risks |
| `SOLUTIONS_ARABIC.md` | How existing Arabic systems are built: ten approaches, products, observations |
| `phase3/letters_test.py`, `phase3/summarise.py` | The scripts of the test |
| `phase3/results/` | Raw output of every system for every clip (CSV) and the summary tables |

Evidence marks used in the reports: **[P]** read in a primary source, **[R]** from the project's earlier reading, **[S]** secondary source to be confirmed, **[?]** not verified.
