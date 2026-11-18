# Phase 1 — Arabic Speech Recognition Technologies for Beginner Learners

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-16
**Status:** desk research only. Nothing was installed or run. No experimental results are reported here.
**Revision 2 (2026-11-16):** wider search added — model catalogues (Hugging Face, GitHub), letter-level work, methods that need no recogniser. New material is in sections 3.8–3.10; the summary, licences, shortlist and open questions are updated.
**Update (2026-11-17):** a preliminary test of five systems on single-letter recordings was run after this report; its results are in `PHASE_3_EXPERIMENTAL_RESULTS.md`. Statements below that "nothing was run" describe the state on 2026-11-16.
**Revision 3 (2026-11-16):** critical analysis added (section 5a: strengths and weaknesses, observations, proposals); licences verified on model pages.

---

## 1. Summary

1. **The task is not ordinary speech recognition.** A Muallim learner reads a known text (a letter with a vowel sign, a syllable, a word). The system must report *what sounds were actually produced*, including wrong ones. Ordinary ASR is built to output the most likely *word*, so it tends to hide exactly the errors we need to see. The right problem class is **mispronunciation detection and diagnosis (MDD)** over a phoneme-level recogniser.
2. **No available system has been evaluated on our population.** We found no model, open or commercial, with published results on adult beginners who start from zero, and none on Russian-speaking learners. The organisers of the main Arabic benchmark (IQRA 2026) state that collecting L2 learner data is future work.
3. **Phoneme-level CTC models built on self-supervised encoders are the strongest evidence-backed family.** They took the top places at IQRA 2026 (best F1 0.72). Text ASR, audio LLMs and the one commercial pronunciation API all score lower where a comparison exists.
4. **Small amounts of real error data matter more than large synthetic sets.** At IQRA 2026, 1,333 real mispronounced utterances helped the top systems more than 55,400 synthetic ones. This supports collecting our own dataset.
5. **Isolated letters are a known weak point.** On a corpus of single vowelled letters (the Horouf corpus), an off-the-shelf Arabic wav2vec 2.0 model reached 35–37 % accuracy; a small classifier on its embeddings reached about 65 %. Stage I of Muallim is exactly this material.
6. **A new model family exists that the project did not know: Quran Lab (2026).** Its newest model, TajweedFormer V4 (November 2026), is the only one found with published numbers on real learners. At a low false-alarm rate it catches 46 % of consonant errors of non-native speakers (L2-KSU) and 32 % of vowel errors corrected by teachers. So the best documented system still misses more than half of real learner errors.
7. **"Canonical bias" is documented by the model authors themselves.** A model trained on correct recitation outputs what the rule says, not what was said: one model reported the expected sound in 81 of 94 clips where annotators heard something else. This is the central technical risk for any model we choose.
8. **Licences now matter for the choice.** Quran Lab models forbid charging for any feature they power. The thesis has a business part, so this needs the author's decision before such a model enters the product.
9. **There is a route that needs no recogniser at all:** compare the learner's audio directly with a teacher's recording of the same item. In 2026 work on English and Japanese this reached human-level agreement for sentence-level scoring. The bot already holds human reference recordings, so this can be tested cheaply.
10. **Recommended design to test in Phase 3:** not one model but three mechanisms on the same audio — a phoneme model with per-sound verification, a closed-set classifier for single letters, and direct comparison with reference recordings (sections 3.10 and 8).

### How to read the evidence marks

| Mark | Meaning |
|---|---|
| **[P]** | Read in a primary source during this session (paper, official documentation, model card) |
| **[R]** | Taken from the project's earlier full-text reading (`docs/research/sources.md`, key `SRC-NNN`) |
| **[S]** | Secondary source only (search summary, third-party page) — check before citing |
| **[?]** | From general knowledge, not checked in this session — must be verified in Phase 3 |

---

## 2. What the task requires

| Requirement | Why it matters for Muallim | Consequence |
|---|---|---|
| Verbatim phonetic output | The error is the signal | Models with a strong language model "repair" errors |
| Short vowels and gemination in the output | Learners read vowelled text; fatha/kasra/damma confusions are core errors | Undiacritized ASR cannot see vowel errors at all |
| Very short audio (one letter, one syllable) | Stage I = 28 letters with vowel signs | Models trained on sentences behave unpredictably on 1-second clips |
| Sounds outside the Arabic inventory | A Russian speaker may substitute a Russian sound | Arabic-only phoneme sets force every sound into an Arabic label |
| Slow, hesitant, restarted speech | Normal for beginners | Long pauses and restarts cause deletions and hallucinations |
| Trainable on little data | The pilot will give thousands of short attempts, not hours | Prefer models with a public fine-tuning path |
| Runs on our server, open licence | Learner voices are personal data; public dataset planned | Commercial APIs are comparison points, not the product core |

Evidence that text ASR hides learner errors:

- In Dutch primary-school reading, Whisper's main failure was *omitting incorrect attempts* (207 cases), not mis-transcribing them; miscue-detection F1 was 0.52. [S] Gao et al., Interspeech 2024, arXiv:2406.07060.
- Post-hoc comparison of ASR output with the target text "performs poorly when ASR inaccurately transcribes verbatim speech"; prompting Whisper with the target text improved results on children's read-aloud speech. [S] Smith et al., Interspeech 2025, arXiv:2505.23627.
- Whisper large-v3 scores 98.78 % WER on Quran audio when diacritics are counted, because it does not output them. [P] Grigoryan et al., arXiv:2507.13977, Table V.

---

## 3. Technology landscape

### 3.1 Family A — Arabic phoneme-level models (closest to the task)

| Model | Base / size | Output | Reported result | Licence | Fine-tuning | Evidence |
|---|---|---|---|---|---|---|
| **Muaalem** `obadx/muaalem-model-v3_2` (current model of the bot) | w2v-BERT 2.0, 0.6B | Multi-level CTC: phonemes + articulation attributes (sifat), Quran phonetic script | PER 0.54 % on expert reciters, 5.8 % on `qdat_bench` (amateur readers) | Model MIT; code under QML 1.0 with conditions | Yes (weights and training data public) | [R] SRC-002; licence [P] model card |
| IqraEval baselines `IqraEval/Iqra_mhubert_base`, `Iqra_wav2vec2_base`, `Iqra_hubert_base`, `Iqra_wavlm_base` | mHuBERT-147 (94M) frozen + BiLSTM + CTC | 68-symbol MSA phoneme set (Halabi phonetiser) | F1 0.4414, PER 13.08 % on QuranMB.v2 | Not shown on the organisation page | Yes (recipe public) | [P] arXiv:2603.29087; HF org page |
| IQRA 2026 top systems (whu-iasp, UTokyo, RAM) | wav2vec2 XLS-R 300M + CTC, with LM rescoring or data filtering | Same 68-symbol set | F1 0.7201 / 0.7170 / 0.7157; PER 3.65–4.05 % | — | Weights: release not confirmed | [P] arXiv:2603.29087, Table 2 |
| Najva (IQRA 2026, rank 5) | NVIDIA FastConformer Hybrid Large, graphemes converted to phonemes | Same | F1 0.6894 | — | Release not confirmed | [P] same |
| Kalimat (IQRA 2026, rank 6) | Qwen3-ASR 1.7B, LoRA on the decoder | Generates phonemes as text | F1 0.6702 | — | Release not confirmed | [P] same |
| Harf-Speech best model | OmniASR-CTC-1B-v2, fine-tuned | MSA phonemes | PER 8.92 % on a 500-sample IqraEval validation subset; real-time factor 0.004 | Release not stated | — | [P] arXiv:2604.06191v2 |
| `nrshoudi/wav2vec2-large-xls-r-300m-Arabic-phoneme` | XLS-R 300M | Arabic phonemes | PER 1.99 % on its own evaluation set; training data "unknown" on the card | Apache-2.0 | Yes | [P] model card. **Assumption:** the author name matches N. Alrashoudi (L2-KSU corpus), so this may be the only public model trained on non-native Arabic. Not confirmed. |
| `IbrahimSalah/Arabic_speech_Syllables_recognition_Using_Wav2vec2` | wav2vec 2.0 | Syllables with vowel signs | — | — | — | [S] |
| AraS2P (Iqra'Eval 2025 winner) | Wav2Vec2-BERT, two-stage training | MSA phonemes | First place 2025 | — | — | [S] arXiv:2509.23504 |

Findings:

- Muaalem was trained on **male expert reciters only**; the authors state it will not detect some errors because such errors are absent from training. Its PER on amateur readers is about ten times worse than on experts. [R] SRC-002.
- A search summary of a later version of the Muaalem paper gives different figures (0.21 % and 1.94 % PER) and lists the paper at ICML 2026. [S] Not reconciled with the figures above.
- IQRA's real-error set (`Iqra_Extra_IS26`) consists of **native speakers instructed to produce given substitutions**, not learners. [P]
- IQRA systems predict phonemes only; the paper notes this limits learner-facing feedback. Muaalem additionally outputs articulation attributes. [P], [R]

### 3.2 Family B — Text ASR that outputs vowel signs

| Model | Base / size | Output | Reported result | Licence | Evidence |
|---|---|---|---|---|---|
| `nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0` | FastConformer hybrid RNN-T + CTC | Arabic text with diacritics and punctuation; trained on MSA + 392 h Quran (EveryAyah) | WER with diacritics 1.55 % / 6.65 % on EveryAyah (before / after overlap removal); 12.94–25.60 % on MSA sets | Paper says "commercial license"; exact terms **[?]** | [P] arXiv:2507.13977 |
| `tarteel-ai/whisper-base-ar-quran`, `whisper-tiny-ar-quran` | Whisper base / tiny | Quran text | WER 5.75 / 7.05 on an unnamed evaluation set | Apache-2.0 (model page, checked in Phase 3) | [S] model cards |
| Other Whisper Quran / tashkeel fine-tunes (`IJyad/whisper-large-v3-Tarteel`, `WajeehAzeemX/base-finetune`) | Whisper | Text, some with diacritics | Not comparable (different test sets) | **[?]** | [S] |

These models can show vowel-sign errors but still decode words through an internal language model. Whether they report a wrong vowel or silently restore the expected one is unknown and is a Phase 3 question.

### 3.3 Family C — General Arabic ASR (no vowel signs)

| Model | Size | Average WER, Open Universal Arabic ASR Leaderboard | Licence | Fine-tuning | Evidence |
|---|---|---|---|---|---|
| Cohere Transcribe Arabic (`CohereLabs/cohere-transcribe-arabic-07-2026`) | 2B | 25.87 | Apache 2.0 | Not documented | [P] vendor post (self-reported) |
| OmniASR-LLM-7B (Meta Omnilingual ASR) | 7B | 28.32 | Apache 2.0 | CTC and LLM variants public | [P] same table; licence [S] |
| Whisper large-v3 | 1.5B | 36.86 | Apache-2.0 [P] | Widely done | [P] same table |
| Qwen3-ASR 1.7B | 1.7B | ≈26.2 | Apache 2.0 | LoRA and full | [S] |
| Voxtral Mini 3B | 3B | ≈39.4 | **[?]** | — | [S] |
| SeamlessM4T v2 large | — | Better than Whisper on some MSA sets | CC-BY-NC **[?]** | — | [P] arXiv:2507.13977 |
| Meta MMS (1B) | 1B | — | CC-BY-NC **[?]** | Adapters | [?] |

Vendor and third-party figures conflict on which model leads (Audar claims 24.7, an aggregator lists OmniASR at 23.96). The live leaderboard was not checked. For Muallim the ranking matters little: all of these drop vowel signs and are trained on fluent native speech. Their use is (a) a control showing how much text ASR hides, and (b) encoders to fine-tune — OmniASR-CTC gave the best phoneme result in Harf-Speech.

### 3.4 Family D — Language-independent phone recognisers

Output: IPA symbols for any language, so a Russian substitute sound can in principle be seen as itself.

| Model | Size | Multilingual phone error (PFER, lower is better) | Evidence |
|---|---|---|---|
| PhoneticXEUS | — | 17.7 | [P] arXiv:2603.29042, Table 1 |
| POWSM | — | 18.7 | [P] same |
| ZIPA-CTC-NS | 64M variants exist | 19.0 | [P] same; arXiv:2505.23170 |
| wav2vec2 LV-60 espeak (`facebook/wav2vec2-lv-60-espeak-cv-ft`) | 300M | 19.5 | [P] same |
| wav2vec2 XLSR-53 espeak (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`) | 300M | 21.0 | [P] same |
| MultIPA | — | 21.3 | [P] same |
| Gemini 2.5 Flash (zero-shot) | — | 53.8 | [P] same |
| Qwen3-Omni (zero-shot) | — | 105.4 | [P] same |

Limitations: no Arabic results are reported; training labels come from automatic grapheme-to-phoneme conversion, which the authors say may miss non-native variation; licences and Arabic coverage of each model are **[?]**. Allosaurus (older, about 2,000 languages) was not checked.

### 3.5 Family E — Commercial services

| Service | Arabic | What it returns | Cost | Evidence |
|---|---|---|---|---|
| **Azure Pronunciation Assessment** | `ar-SA`, `ar-EG` are in the list of 33 supported locales | Accuracy, fluency, miscue scores. Phoneme and syllable labels came back **empty** for `ar-SA` in a June 2025 user report (scores were present); current state not checked [P] Microsoft Q&A | About $1.32 per audio hour reported in a Microsoft Q&A answer; official price page not confirmed | [P] Microsoft Learn (page dated 2026-10-28); price [S] |
| OpenAI gpt-4o-transcribe | Yes **[?]** | Text | $0.006 / min | [S] |
| ElevenLabs Scribe v2 | 90+ languages | Text | ≈$0.22 / h | [S] |
| Deepgram Nova-3 | **[?]** | Text | $0.0043–0.0077 / min | [S] |
| Google Chirp 3 | 125+ languages | Text | $0.004–0.016 / min | [S] |
| Speechmatics | **[?]** | Text | ≈$0.0117 / min | [S] |
| SpeechSuper, Speechace, ELSA | Arabic support **not confirmed** | Pronunciation scores | — | [S] |
| Tarteel | Quran only | Word-level mistakes (missed, wrong, extra word); consumer app, no public API found | — | [R] SRC-046; [S] |

Findings:

- Azure is the only commercial pronunciation-assessment API with confirmed Arabic. On 40 utterances scored by three speech-language pathologists, Azure reached correlation 0.635 with the mean expert score against 0.791 for an open pipeline. [P] arXiv:2604.06191v2. Speakers are not described; the sample is small.
- Microsoft states that results depend on its speech-to-text accuracy and recommends own evaluation. [S]
- At 5 seconds per attempt, the reported Azure price is about $0.002 per attempt. Cost is not the obstacle; sending learner voices to a third party and a closed, unadjustable model are.

### 3.6 Family F — Audio language models

| Evidence | Result | Source |
|---|---|---|
| Gemini-3-pro / Gemini-3-flash, zero-shot Arabic phoneme transcription | PER 15.07 % / 17.31 %; Gemini-3-pro about 10× slower than real time | [P] arXiv:2604.06191v2 |
| Qwen2.5-Omni-7B, zero-shot | "failed to produce usable phoneme outputs for Arabic" | [P] same |
| Qwen3-ASR 1.7B fine-tuned for phonemes | PER 16.79 % (Harf-Speech); F1 0.67 at IQRA 2026 (Kalimat) | [P] both papers |
| Qwen2-Audio, zero-shot scoring of L2 English | Over-predicts scores, imprecise on errors | [S] arXiv:2601.16230 |
| Audio LLMs for mispronunciation feedback (L2-Arctic-plus) | "significant limitations" in detection and feedback; instruction tuning helps | [S] arXiv:2601.14744 |

Conclusion: not suitable as the detector today. A text LLM remains useful *after* detection, to phrase the explanation — the bot already separates these steps.

### 3.7 Family G — Alternative approaches

| Approach | Idea | Fit for Muallim | Evidence |
|---|---|---|---|
| Goodness of Pronunciation on a CTC model, alignment-free | Score how well each expected phoneme matches the audio, without training on learner errors | Works on any Family A model; gives a per-phoneme confidence | [S] arXiv:2507.16838, arXiv:2506.02080; classic method [R] SRC-115 |
| Closed-set classifier on encoder embeddings | For "one letter + one vowel sign" (112 classes) classify instead of transcribe | Direct fit for Stage I; 35–37 % → ≈65 % on Horouf | [P] arXiv:2508.19587 |
| Text-prompted recognition | Give the model the target text so it transcribes deviations | Possible with Whisper-type models | [S] arXiv:2505.23627 |
| Forced alignment to the reference | Locate each expected sound in time, then score it | Tools already in `external/` (ctc-forced-aligner) | [R] |
| Learned verifier on top of the recogniser | Calibrated accept / reject / "not sure" | Already planned as component B1 (ADR-0051) | [R] |
| Verbatim Whisper variants (CrisperWhisper) | Keep fillers and hesitations | English/German focus; non-commercial licence; Arabic not shown | [S] |

### 3.8 Revision 2 — models found by searching the catalogues directly

Method: queries to the Hugging Face model index (`quran`, `tajweed`, `arabic-phoneme`, `mispronunciation`, `arabic-alphabet`, `hijaiyah`, `makhraj`) and GitHub. All rows are [P] (model cards read in this session); every metric is self-reported by the model author.

| Model | Size | Output | Trained on | Reported result | Licence | Note |
|---|---|---|---|---|---|---|
| **TajweedFormer V4** `Quran-Lab/tajweedformer-v4` (2026-11) | 65M, streaming, runs on CPU | 38 sound tokens incl. short and long vowels and a **"foreign"** token; separate heads for timing, gemination, articulation attributes; per-sound confidence | Correct recitation; thresholds fitted on 157 speakers | False flags on correct recitation 0.2–0.8 % per error class. On real learners: **32 %** of teacher-corrected vowel words caught; **46 %** of L2-KSU consonant errors caught at 2.1 % false flags; 19 % of length errors | NPL-1.2 (no charging for any feature it powers) | No language model by design. Ships no scorer: the app builds the verdict. Weights come through an SDK (Android, iOS, web, C for Linux); raw weights on request. Phone and child audio: 3–7 % false flags |
| `Quran-Lab/zipformer_p-arabic-v3` (2026-08) | 65.5M, ONNX | 251-symbol Quran phonetic alphabet | ≈5,400 h; 36 + 1,161 reciters; phone recordings | PER 1.43 % studio, 3.65 % phone, 9.10 % unseen reciter | NPL-1.2, gated | Card states the canonical bias (81 of 94 clips) and that children score 2–3× worse |
| `Hisnlabs/tajweed-v2` (2026-11) | **20.6M, 23 MB**; 4 s of audio in 28 ms on a laptop CPU | Phonetic transcription with lengths, per-word remarks; 10 attribute heads | Distilled from Muaalem; 27.7k clips incl. **learner recordings (RetaSy)** | PER on QDAT (159 learners) 7.0 % vs 4.9 % for Muaalem; false remarks on 3.6–8.9 % of correct words | Apache-2.0 | Cheapest to deploy; inherits Muaalem's errors |
| `Muno459/fastconformer-quran` | 114.6M | Diacritized text + three error signals: a small trained "pronunciation head", distance to master reciters, and a likelihood score; flag when 2 of 3 agree | EveryAyah + phone recordings (tlog) | Detection: ≈80 % true positives at 9.3 % false positives; WER 5.41 on a 600-clip benchmark (Whisper large-v3: 10.10) | NPL-1.1, no commercial licence | Labels for the head were produced by another ASR system, not by teachers |
| `quranic-orgz/omni-ctc-ipa-v7…` | 0.3B | 71 IPA-style symbols + four attributes | EveryAyah phonemes | PER 6.07 %; attribute F1 ≈ 97 % | CC-BY-NC-4.0 | Card: "Not validated as a mispronunciation-detection system"; a test on QuranMB.v2 showed no gain |
| `MostafaMaroof/wav2vec2-arabic-phoneme-asr` | XLSR-53, 0.3B | 75 MSA phonemes | IqraEval train + a studio MSA corpus | PER 14.42 %; short-vowel confusions dominate | Apache-2.0 | Well documented; author recommends alignment-based scoring rather than free decoding |
| `nrshoudi/…-Arabic-phoneme-*` (31 models, 2023) | XLS-R 300M; Whisper adapters | Arabic phonemes | Names include "native-non-native" and "MDD" | MDD variant PER 11.35 % | Apache-2.0 | Confirms the link to the L2-KSU work; cards give no data description |
| `TBOGamer22/wav2vec2-quran-phonetics` | 94M | Latin phonetic strings, **single words** | 77.4k word-level clips (`Buraaq/quran-md-words`) | 99.8 % word accuracy on its own split | Apache-2.0 | Trained on isolated words — closer to our unit of speech than verse-level models |
| Letter classifiers: `ojisetyawan/whisper-base-ar-quran-ft-hijaiyah-2`, `HamzaSidhu786/arabic-alphabet-speech-classification`, others | ≈20M | One label per clip (which letter) | Small letter-pronunciation sets, partly Indonesian | Accuracy 0.954 (own split; classes and speakers not described) | Apache-2.0 | Proof that the closed-set route is in use; none is documented well enough to rely on |

Other items seen and not pursued: about 25 re-exports of the Tarteel Whisper models; `Quran-Lab/mfa-quran-hafs` (forced aligner, Apache-2.0 — useful for timing); `mohammed/fastconformer-quran-ar` and `mrmuminov/quran-fastconformer-ctc-ar` (CC-BY-4.0 text models).

Findings:

- **Quran Lab is the most relevant new source.** It is described on its own site as a non-profit lab. It publishes a benchmark with a ranking metric built for our problem ("checker score": correct readings must be left alone and the wrong word must be found), and its model cards report failures openly.
- **Three independent authors recommend the same mechanism:** do not read errors off the decoded text; instead score the expected sound against alternatives at each position (TajweedFormer reference method, MostafaMaroof card, Muno459's likelihood signal).
- **All of these models are built for Quran text.** Whether their text-to-sound tools accept a single vowelled letter or a non-Quran word is not documented (`quran-g2p` examples use verse references only). The bot already solves this for Muaalem; for any other model it must be checked.

### 3.9 Revision 2 — letter-level work in other countries

| Work | Material | Method | Result | Evidence |
|---|---|---|---|---|
| Indonesian studies on *hijaiyah* letters (several, 2018–2022) | Single letters, some with vowel signs; small speaker groups | MFCC features + CNN / SVM | 62.45 % accuracy on 28 letters (616 clips) in one study | [S] |
| Makhraj of ʿayn | 1,600 clips, correct vs incorrect | MFCC + modified VGG-16 | — | [S] |
| Telkom University "Marked Hijaiyah Letters' Pronunciation Dataset" | 28 letters × vowel signs = 168 classes; 3 men, 3 women | — | Public dataset | [S] |
| Horouf (section 4) | 112 vowelled letters, ≈10,000 clips | wav2vec 2.0 embeddings + classifier | ≈65 % | [P] |

No letter-level study with modern self-supervised models and non-native adult beginners was found. Among beginner reading apps (Noorani Qaida apps, Thurayya), none was found that documents automatic per-letter feedback; the common solution is a human teacher listening to recordings. [S]

### 3.10 Revision 2 — methods that need no phoneme recogniser

| Method | Idea | Result | Why it matters for Muallim | Evidence |
|---|---|---|---|---|
| Direct comparison with native recordings | Align learner audio to teacher audio of the same item over self-supervised features (WavLM) and measure the distance | "Exceeds human agreement on holistic and sentence-level phonetic scoring" for L2 English and Japanese | Needs no training data, no phoneme inventory and no Arabic model; the bot already has human reference recordings for its items | [P] abstract, McIntosh et al., arXiv:2607.13721 |
| Native-reference geometry | Position of each sound class relative to native speakers' in the feature space | Correlation with proficiency up to −0.53 | Could give a per-sound "how far from native" measure | [S] arXiv:2609.28060 |
| Token surprisal | A small model trained on native speech only; unusual sound sequences score as surprising | Correlation 0.60–0.66 on speechocean762 | Light enough for a server CPU | [S] arXiv:2606.19910 |
| Articulation attributes instead of phonemes | Detect features (place, voicing, emphasis) rather than sounds; attributes are shared across languages | Mandarin L2: false acceptance −10.1 %, diagnosis error −23.6 % vs phoneme-only | Matches how tajwid describes errors (place and manner of articulation); can describe a sound that is neither the Arabic target nor a known substitute | [S] arXiv:2311.07037, arXiv:2606.22022 |
| First-language-aware detection | Tell the model the learner's first language | Lower phoneme error than language-blind model | Our learners share one or two first languages | [S] El Kheir et al., arXiv:2309.07719 |

These are unproven for Arabic and for single letters. Their value is that they do not depend on a model trained on correct Quran recitation, so they do not inherit the canonical bias.

---

## 4. Evidence on beginner and non-native speech

| Study | Speakers | Result | Access | Evidence |
|---|---|---|---|---|
| Alrashoudi et al., 2025 (L2-KSU) | Native and non-native adults, read speech | PER 3.1 %; detection accuracy 91.3 %, diagnosis 80.8 % | Corpus gated on Hugging Face (`IWAN/L2-KSU-Dataset`) | [P] abstract via Consensus; [R] SRC-161 |
| Algabri et al., 2022 | Non-native Arabic; errors partly synthesised by TTS | PER 3.83 %, F1 70.53 % | — | [P] abstract; [R] SRC-160 |
| Fanoush et al., 2025 | Native children 8–11, about 60 min annotated | F1 71.42 %, PER 16.47 % | — | [R] SRC-162 |
| Zaatiti et al., 2025 (Horouf) | Native and non-native, isolated vowelled letters, ≈10,000 clips | Off-the-shelf 35–37 %; classifier ≈65 % | On request, no licence | [P] arXiv:2508.19587 |
| IQRA 2026 | Native speakers; instructed errors | Best F1 0.72 | Public on Hugging Face | [P] |
| Nasution et al., 2025 | 10 Indonesian students | Descriptive only | — | [P] abstract |
| Quran Lab, TajweedFormer V4 card, 2026 | Real students corrected by teachers; L2-KSU (1,598 consonant errors) | 32 % of vowel errors and 46 % of consonant errors caught | Learner test sets private | [P] model card (self-reported) |
| L2AraSpeech, 2026 (*Language Resources & Evaluation*) | Non-native learners; frequent errors annotated by linguists | Details not read (paywall redirect) | Unknown | [S] |
| Arabic-CAPT (King Saud University) | ≈60 non-native speakers, 20 nationalities | — | Appears not public | [S] |

What is **not** in the literature we found:

- any evaluation on adult learners starting from zero;
- any Arabic speech study with Russian- or Kazakh-speaking learners;
- any study of how these models handle slow, hesitant, restarted reading in Arabic;
- any public model trained on real beginner errors.

---

## 5. Comparison of candidate families

| Criterion | A. Arabic phoneme CTC | B. Diacritized text ASR | C. General ASR | D. Universal phone | E. Azure PA | F. Audio LLM |
|---|---|---|---|---|---|---|
| Shows wrong sounds | Yes | Partly (unknown) | No | Yes | Score only | Weak |
| Vowel signs / gemination | Yes | Yes | No | Vowel quality yes | Unknown | Weak |
| Sounds outside Arabic | No | No | No | Yes | No | Unknown |
| Evidence on Arabic errors | Strong (IQRA) | Indirect | None | None | One small study | Weak, negative |
| Evidence on beginners | None | None | None | None | None | None |
| Isolated letters | Known weak | Unknown | Unknown | Unknown | Unknown | Unknown |
| Fine-tunable by us | Yes | Yes | Yes | Yes | No | Partly (LoRA) |
| Runs on own server | Yes | Yes | Yes (large) | Yes | No | Mostly no |
| Cost | Server only | Server only | Server only | Server only | ≈$1.3 / h | Per token; slow |

---

## 5a. Critical analysis (revision 3)

### Strengths and weaknesses of each candidate

Every row cites the section where the source is given. "Fit" is my judgement for Muallim's task, not a measured result.

| Candidate | Strong | Weak | Fit |
|---|---|---|---|
| **Muaalem** (3.1) | Richest output: sounds plus ten articulation attributes. No language model. Open weights and training data (MIT). Already integrated. | Trained only on male expert reciters; never saw a learner error. Phoneme error about ten times higher on amateurs than on experts. 0.6B parameters — the heaviest of the phoneme models. One annotator and one verse behind its learner benchmark. | High as baseline; unproven on beginners |
| **TajweedFormer V4** (3.8) | Only model with numbers on real learners and on non-native speakers. Reports its own failures per error class. Very low false alarms on correct reading (0.2–0.8 %). Small (65M). "Foreign sound" token. | Misses most real errors (catches 32–46 %). Licence forbids paid features. Weights through an SDK built for phones, not servers. No scorer included. All figures self-reported, learner test sets private. | High technically; blocked by licence and access |
| **`Hisnlabs/tajweed-v2`** (3.8) | Apache-2.0. 23 MB, 28 ms for 4 s of audio on a laptop. Training included learner recordings. | A copy of Muaalem's behaviour, including its errors; 7.0 % against 4.9 % error on the learner benchmark. Flags 3.6–8.9 % of correct words. | Medium: deployment option, not a better detector |
| **IQRA 2026 top systems** (3.1) | Best peer-reviewed benchmark result (F1 0.72); independent evaluation by organisers. | Weights not confirmed public. Test errors are staged by native speakers. Baseline encoder is non-commercial (CC BY-NC-SA). Verse-level audio, not letters. | Medium: reference point, not a product |
| **`nrshoudi` models** (3.8) | Only public weights linked to non-native Arabic. Apache-2.0. | Model cards empty; 31 variants with no guide to which is final; 2023, older base. | Medium: worth one test |
| **`MostafaMaroof` phoneme model** (3.8) | Honest card: lists its own error patterns and limits. Apache-2.0. | 14.4 % error; trained largely on synthetic speech. | Low–medium |
| **NVIDIA diacritized ASR** (3.2) | Peer-described training; outputs vowel signs; CC-BY-4.0 (verified on the model page); fine-tuning recipes public. | Decodes words through a language-like tokenizer, so it may restore the expected vowel. Needs the NeMo toolkit. | Control |
| **General ASR** — Whisper, Cohere, OmniASR, Qwen3-ASR (3.3) | Strong on fluent native speech; permissive licences. | No vowel signs; hide learner errors (Whisper: 98.78 % error with diacritics; omits wrong attempts). Large. | Control only |
| **Universal phone recognisers** (3.4) | Not limited to Arabic sounds; small variants exist; ZIPA main models are CC-BY-4.0, XLSR-espeak is Apache-2.0 (both verified). | No Arabic results published. Labels come from automatic conversion. Arabic emphatics and pharyngeals may be poorly separated — untested. | Medium: diagnostic tool |
| **Azure Pronunciation Assessment** (3.5) | Supported commercial product; Arabic locales listed. | No sound labels for Arabic in a 2025 report. Lower agreement with experts than an open pipeline (0.635 vs 0.791, 40 utterances). Audio leaves our server. Cannot be adapted. | Low |
| **Audio LLMs** (3.6) | No training needed; can explain in words. | 15–17 % phoneme error zero-shot; slow; one model failed outright on Arabic. | Low as detector |
| **Reference comparison** (3.10) | No Arabic model, no training, no canonical bias; uses recordings the bot already has. | Proven only for English and Japanese sentences, in a 2026 preprint. Says "how far", not "which sound". | Promising, unproven |

### What I noticed across the sources

1. **The numbers that look best say the least about us.** Error rates below 2 % are all measured on professional reciters. On amateurs, phone audio, children or unseen reciters the same models show 4–9 %. The only results on real learner errors are recall figures of 32–46 %.
2. **Almost every figure is self-reported.** Only the IQRA leaderboard is run by a party other than the model's author. Quran Lab's learner sets are private, so its key numbers cannot be reproduced.
3. **Sources contradict themselves.** The IQRA paper gives two values for the 2025 best score; the Horouf paper gives 35 % and 37 %; the NVIDIA paper's conclusion disagrees with its own table; the Muaalem paper has two sets of error rates across versions. None of this changes the conclusions, but no single figure should be quoted without the table it came from.
4. **Model cards that admit failure are the most useful.** The statements "outputs the rule, not what was said" and "not validated for mispronunciation detection" came from authors, not critics.
5. **Nobody evaluates what Muallim teaches first.** Published results concern verses and sentences. The two letter-level results (35–37 % and 62 %) are both poor.
6. **Licences split the field in two.** Permissive: Muaalem, tajweed-v2, NVIDIA, Whisper, OmniASR, ZIPA. Restricted: Quran Lab (no paid features), IqraEval baseline encoder, MMS, SeamlessM4T (non-commercial).
7. **The project's present approach is the one the field converged on:** a phoneme model without a language model, compared with a reference. The research did not find a different approach that is clearly better; it found ways to make this one more reliable.

### Proposals

**Strengthen**

- Replace reading errors off the decoded text with scoring each expected sound against alternatives, with a separate threshold per error class. Three independent authors recommend it (3.8).
- Report results the way the Quran Lab benchmark does: correct readings left alone and wrong ones found, in one figure. It makes false alarms visible, which matter most for beginners' motivation.
- Keep the "not sure" outcome already planned in ADR-0051. The 32–46 % recall of the best system shows that a confident verdict on every sound is not achievable now.

**Add**

- A Stage I path that does not transcribe: a closed-set classifier or comparison with the teacher's recording (3.10, 8).
- A universal phone recogniser as a second opinion for sounds that are not Arabic.
- `Hisnlabs/tajweed-v2` as a fallback when server load matters.
- Contact with Quran Lab, the only group holding learner-error test sets.

**Remove or deprioritise**

- General ASR and audio LLMs as detectors — keep only as controls.
- Commercial pronunciation APIs — no Arabic sound labels, weaker agreement with experts, data leaves the server.
- Chasing leaderboard word-error rankings: they measure a different task.

**Do not claim in the thesis**

- That any model "works for beginners": no published evidence exists.
- That Muallim's model choice was validated: the Phase 3 test was preliminary and did not use our learners.

---

## 6. Licensing and deployment

| Item | Finding | Evidence |
|---|---|---|
| Muaalem | Model and dataset MIT; code under QML 1.0 (Apache-based, with conditions on AI disclosure, religious compliance, no advertising) | [R] project licence review |
| **Quran Lab models and tools** (TajweedFormer V4, zipformer v3, `quran-g2p`, benchmark) | NPL-1.2: free to use, adapt and share; **no charging for the model or for any feature it powers**; the app must say that feedback can be wrong and does not replace a teacher; output must not be presented as a religious ruling | [P] model cards |
| `Hisnlabs/tajweed-v2`, `MostafaMaroof`, `nrshoudi`, `TBOGamer22` | Apache-2.0 | [P] model cards |
| OmniASR, Qwen3-ASR, Cohere Transcribe Arabic | Apache 2.0 | [S] / [P] |
| NVIDIA FastConformer Arabic (`…pcd_v1.0`) | CC-BY-4.0 | [P] model page (revision 3) |
| Whisper large-v3 | Apache-2.0 | [P] model page (revision 3) |
| MMS (`mms-1b-all`), SeamlessM4T v2 | CC-BY-NC-4.0 — non-commercial | [P] model pages (revision 3) |
| mHuBERT-147 (IqraEval baseline encoder) | CC-BY-NC-SA-4.0 — non-commercial | [P] model page (revision 3) |
| `facebook/wav2vec2-xlsr-53-espeak-cv-ft` | Apache-2.0 | [P] model page (revision 3) |
| ZIPA (`anyspeech/zipa-*`) | CC-BY-4.0 for the main models; "ns" variants CC-BY-NC-SA-4.0 | [P] model index (revision 3) |
| Commercial APIs | Learner audio leaves our server; data-processing terms differ per vendor | — |
| Hardware | Muaalem (0.6B) already runs in the bot. CTC models of 300M–1B work on CPU for short clips; 2B–7B models need a GPU | Project state; sizes [P] |

Any new dependency, paid service, or transfer of learner audio to a third party is a decision for the author (project rules).

---

## 7. Limitations of this report

- No model was run. Every number is taken from its source and measured on that source's data, not ours.
- Numbers across tables are **not comparable** with each other: different test sets, phoneme inventories and metrics.
- Several figures are vendor self-reports (Cohere, Audar) or third-party summaries; they are marked [S].
- API prices come mostly from third-party pages and one Microsoft Q&A answer.
- Licences still marked [?] were not opened. Revision 3 verified the licences of Whisper, MMS, SeamlessM4T, mHuBERT-147, the NVIDIA model, XLSR-espeak and ZIPA on their model pages (section 6).
- Public availability of the IQRA 2026 top-team weights was not confirmed.
- Two inconsistencies exist inside sources: the IQRA paper gives two different figures for the 2025 best F1 (≈0.47 and ≈0.30); the Horouf paper gives 35 % and 37 % for the same baseline.
- New sources from this session are not yet registered in `docs/research/sources.md`.
- Revision 2: figures from model cards are self-reported and were not reproduced. The Quran Lab leaderboard table itself could not be read (the page loads its data separately), so no ranking of models against each other is given.
- Revision 2: catalogue search was by keyword; models published without these keywords would be missed.

---

## 8. Shortlist for Phase 3 (revised)

### What the evidence says fits Muallim

No single model fits. The material has two different shapes, and the evidence points to a different mechanism for each:

| Material | Best-supported mechanism | Why |
|---|---|---|
| Stage I: one vowelled letter or syllable (closed set, about one second) | Verification, not transcription: (a) closed-set classifier on encoder embeddings; (b) direct comparison with the teacher's recording; (c) expected-sound-versus-alternatives score from a phoneme model | Free transcription of single letters is the documented weak point (35–37 %). The answer set is small and known in advance |
| Stage II: words and lines | Phoneme model without a language model + per-sound verification against the reference, with separate thresholds per error class | Recommended independently by three model authors; the only approach with learner numbers |

A model's licence, its behaviour on our text (not Quran verses) and its canonical bias decide the choice more than its headline error rate.

### Test first

| # | Candidate | Why |
|---|---|---|
| 1 | **Muaalem** `obadx/muaalem-model-v3_2` | Current model and baseline; phonemes + articulation attributes; MIT |
| 2 | **TajweedFormer V4** (Quran Lab) | Only model with published results on real learners and on non-native speakers; no language model; "foreign sound" token; small. **Blocked on two decisions:** licence (no paid features) and access to weights for a server |
| 3 | **`Hisnlabs/tajweed-v2`** | Apache-2.0, 23 MB, fast on CPU, trained partly on learner speech; tests how much is lost against Muaalem |
| 4 | **Phoneme models tied to non-native or benchmark data:** `nrshoudi/…-phoneme-based-MDD`, `MostafaMaroof/wav2vec2-arabic-phoneme-asr`, `IqraEval/Iqra_mhubert_base` | Apache-2.0 (first two); link our numbers to L2-KSU and to the IQRA benchmark |
| 5 | **Reference comparison without a recogniser** (WavLM features + alignment against the bot's human reference recordings) | No training, no Arabic model, no canonical bias; uses audio we already have |
| 6 | **Closed-set letter classifier** on embeddings of the best encoder from 1–4 | Direct fit for Stage I; needs labelled letter clips, so it becomes testable when Phase 2 finds usable letter data |
| 7 | **Universal phone recogniser:** `facebook/wav2vec2-xlsr-53-espeak-cv-ft`, ZIPA | Can show a non-Arabic substitute sound |

### Controls

| # | Candidate | Why |
|---|---|---|
| 8 | `nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0`, Whisper large-v3, `tarteel-ai/whisper-base-ar-quran` | Measure how much text ASR hides or repairs |
| 9 | `Quran-Lab/zipformer_p-arabic-v3` | Measures canonical bias in a large correct-recitation model |
| 10 | Azure Pronunciation Assessment (`ar-SA`) | Commercial reference; scores only, no sound labels. Only with recordings that may leave our server |
| 11 | Gemini (zero-shot) | Audio-LLM reference; same data restriction |

Not recommended for testing: SpeechSuper, Speechace, ELSA (no confirmed Arabic); Tarteel (no API, word level only); MMS and SeamlessM4T (licence, no vowel signs); `quranic-orgz/omni-ctc-ipa` (non-commercial, and its own card reports no gain on error detection).

### How to compare them

Borrow the Quran Lab ranking idea: on a balanced set of correct and incorrect attempts, count the share that gets exactly the right verdict. A system that never flags anything scores 50 %. This punishes both missed errors and false alarms, and it applies equally to a phoneme model, a classifier and a reference comparison.

---

## 9. Open questions

1. Are the IQRA 2026 top-team weights public, and under what licence?
2. Which of the 31 `nrshoudi` models corresponds to the published L2-KSU system, and what is its phoneme inventory? (The link to non-native data is now supported by the model names, still not by a description.)
3. Does Azure now return sound labels for `ar-SA`? (Empty in a June 2025 report.) Does it accept vowelled reference text?4. Do diacritized text models report a wrong vowel or restore the expected one?
5. How does each model behave on a one-second clip of a single vowelled letter?
6. Which Muaalem PER figures are current (0.54 % / 5.8 % or 0.21 % / 1.94 %)?
7. Which recordings will Phase 3 use? Without real beginner recordings Phase 3 can only be a preliminary test on expert, native or public data.
8. Three phoneme inventories are in play (Quran phonetic script, the 68-symbol MSA set, IPA). A mapping is needed before any PER comparison.
9. **Licence decision (author):** may a model under NPL-1.2 power the bot, given the business part of the thesis? If not, Quran Lab models can serve only as a research comparison.
10. Can TajweedFormer V4 run on a Linux server (C build or raw weights on request)? Will Quran Lab share how its learner test sets were built?
11. Do the Quran-oriented text-to-sound tools accept a single vowelled letter and non-Quran words?
12. How many reference recordings per item does direct comparison need, and does it work on one-second clips? The published results are for sentences.

---

## 10. Recommendations for Phase 2

1. Request access to **L2-KSU** first — gated access may take time, and it is the only known non-native Arabic corpus with phone-level labels.
2. Record for each dataset: speakers' first language and level, unit of speech (letter, syllable, word, verse), annotation type, licence. The gap identified here is *beginners × isolated units × real errors × Russian or Kazakh first language*.
3. Ask the Horouf authors for access: it is the closest existing material to Stage I.
4. Inspect the IQRA datasets on Hugging Face (`Iqra_train`, `Iqra_Extra_IS26`, `QuranMB.v2`) for licence and annotation format — they are the likely model for our own format in Phase 4.
5. Identify which existing public recordings could serve as the common test audio for Phase 3.
6. Dataset leads from revision 2, to examine in Phase 2: L2AraSpeech (2026), Arabic-CAPT and AraVoiceL2 (non-native); RetaSy (learner recitation); `Quran-Lab/quran-tajweed-benchmark` and `quran-tajweed-phonetics`; `Buraaq/quran-md-words` (77.4k single-word clips); Telkom "Marked Hijaiyah Letters" (168 classes), `Reinjin/Pelafalan_Huruf_Hijaiyah` and the Kaggle Hijaiyah set (single letters); `tarteel-ai/tlog` (gated phone recordings).
7. Write to Quran Lab: they hold the only learner-error test sets with published results and say raw weights are available for research.

---

## Sources

**Benchmarks and challenges**
- IQRA 2026 Interspeech Challenge. arXiv:2603.29087 — https://arxiv.org/abs/2603.29087 (SRC-031)
- IqraEval on Hugging Face — https://huggingface.co/IqraEval
- Iqra'Eval 2025 shared task — https://aclanthology.org/2025.arabicnlp-sharedtasks.61/ (SRC-043)
- El Kheir et al. Towards a Unified Benchmark for Arabic Pronunciation Assessment. arXiv:2506.07722 (SRC-004)
- Open Universal Arabic ASR Leaderboard. arXiv:2412.13788 — https://arxiv.org/abs/2412.13788

**Arabic phoneme-level and pronunciation models**
- Abdelfattah et al. Automatic Pronunciation Error Detection and Correction of the Holy Quran's Learners Using Deep Learning. arXiv:2509.00094 (SRC-002); model — https://huggingface.co/obadx/muaalem-model-v3_2
- Azad et al. Harf-Speech. arXiv:2604.06191 — https://arxiv.org/abs/2604.06191 (SRC-149)
- Zaatiti et al. Towards stable AI systems for Evaluating Arabic Pronunciations. arXiv:2508.19587 — https://arxiv.org/abs/2508.19587 (SRC-151)
- AraS2P: Arabic Speech-to-Phonemes System. arXiv:2509.23504 — https://arxiv.org/abs/2509.23504
- https://huggingface.co/nrshoudi/wav2vec2-large-xls-r-300m-Arabic-phoneme
- https://huggingface.co/IbrahimSalah/Arabic_speech_Syllables_recognition_Using_Wav2vec2

**Non-native and learner speech**
- Alrashoudi et al. Improving mispronunciation detection and diagnosis for non-native learners of the Arabic language. Discover Computing, 2025 — https://link.springer.com/10.1007/s10791-024-09489-8 (SRC-161); corpus — https://huggingface.co/datasets/IWAN/L2-KSU-Dataset
- Algabri et al. Mispronunciation Detection and Diagnosis with Articulatory-Level Feedback Generation for Non-Native Arabic Speech. Mathematics, 2022 — https://mdpi.com/2227-7390/10/15/2727 (SRC-160)
- Fanoush et al. Mispronunciation Detection and Diagnosis for Young Arabic Learners Using Transfer Learning. IEEE Access, 2025 (SRC-162)
- Nasution et al. Analyzing Phonetic Errors Among Non-Native Arabic Learners Through Artificial Intelligence. Arabiyat, 2025
- Gao et al. Reading Miscue Detection in Primary School through Automatic Speech Recognition. arXiv:2406.07060 — https://arxiv.org/abs/2406.07060
- Smith et al. Interspeech 2025. arXiv:2505.23627 — https://arxiv.org/abs/2505.23627

**Text ASR**
- Open Automatic Speech Recognition Models for Classical and Modern Standard Arabic. arXiv:2507.13977 — https://arxiv.org/abs/2507.13977
- Cohere Transcribe Arabic — https://huggingface.co/blog/CohereLabs/cohere-transcribe-arabic-07-2026-release
- Omnilingual ASR. arXiv:2511.09690 — https://arxiv.org/abs/2511.09690
- Qwen3-ASR Technical Report. arXiv:2601.21337
- https://huggingface.co/tarteel-ai/whisper-base-ar-quran

**Universal phone recognition**
- An Empirical Recipe for Universal Phone Recognition. arXiv:2603.29042 — https://arxiv.org/abs/2603.29042
- ZIPA. arXiv:2505.23170 — https://arxiv.org/abs/2505.23170
- POWSM. arXiv:2510.24992 — https://arxiv.org/abs/2510.24992

**Scoring methods and audio LLMs**
- Segmentation-free Goodness of Pronunciation. arXiv:2507.16838 — https://arxiv.org/abs/2507.16838
- Enhancing GOP in CTC-Based Mispronunciation Detection with Phonological Knowledge. arXiv:2506.02080 — https://arxiv.org/abs/2506.02080
- Zero-Shot Speech LLMs for Multi-Aspect Evaluation of L2 Speech. arXiv:2601.16230 — https://arxiv.org/abs/2601.16230
- Unlocking Large Audio-Language Models for Interactive Language Learning. arXiv:2601.14744 — https://arxiv.org/abs/2601.14744
- CrisperWhisper — https://github.com/nyrahealth/CrisperWhisper

**Revision 2 — models found in catalogues**
- https://huggingface.co/Quran-Lab/tajweedformer-v4 · https://sdk.quranlab.ai · https://github.com/Quran-Lab/quran-g2p
- https://huggingface.co/Quran-Lab/zipformer_p-arabic-v3
- https://huggingface.co/datasets/Quran-Lab/quran-tajweed-benchmark · https://huggingface.co/spaces/Quran-Lab/quranic-asr-leaderboard
- https://huggingface.co/Hisnlabs/tajweed-v2 · https://github.com/HisnLabs/tajweed
- https://huggingface.co/Muno459/fastconformer-quran
- https://huggingface.co/quranic-orgz/omni-ctc-ipa-v7-attraux-aux0p4-20260928
- https://huggingface.co/MostafaMaroof/wav2vec2-arabic-phoneme-asr
- https://huggingface.co/nrshoudi/wav2vec2-large-xls-r-300m-Arabic-phoneme-based-MDD
- https://huggingface.co/TBOGamer22/wav2vec2-quran-phonetics
- https://huggingface.co/ojisetyawan/whisper-base-ar-quran-ft-hijaiyah-2

**Revision 2 — letter-level work and other methods**
- Marked Hijaiyah Letters' Pronunciation Dataset, Telkom University — https://dataverse.telkomuniversity.ac.id/dataset.xhtml?persistentId=doi:10.34820/FK2/XACWLX
- Automatic Detection of Hijaiyah Letters Pronunciation using CNN — https://join.if.uinsgd.ac.id/index.php/join/article/view/882
- McIntosh et al. Self-supervised Speech Comparison for L2 Phone, Rhythm, and Intonation Scoring. arXiv:2607.13721 — https://arxiv.org/abs/2607.13721
- A Native-Reference Coordinate Geometry for L2 Pronunciation Deviation. arXiv:2609.28060
- Light-weight Pronunciation Assessment via Discrete Speech Token Surprisal. arXiv:2606.19910
- Shahin et al. Phonological Level wav2vec2-based Mispronunciation Detection and Diagnosis Method. arXiv:2311.07037; Mandarin extension arXiv:2606.22022
- El Kheir et al. L1-aware Multilingual Mispronunciation Detection Framework. arXiv:2309.07719 — https://arxiv.org/abs/2309.07719
- L2AraSpeech. Language Resources & Evaluation, 2026 — https://link.springer.com/article/10.1007/s10579-026-09924-w
- Azure, empty phoneme fields for `ar-SA` — https://learn.microsoft.com/en-us/answers/questions/2283242/azure-speech-pronunciation-assessment-empty-phonem

**Commercial**
- Azure Speech language support (pronunciation assessment tab) — https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=pronunciation-assessment
- Microsoft Q&A on pronunciation assessment pricing — https://learn.microsoft.com/en-us/answers/questions/5608069/pricing-and-usage-of-pronunciation-assessment-feat
- Tarteel mistake detection — https://tarteel.ai/blog/introducing-mistake-detection/ (SRC-046)
- Speechace supported languages — https://api-docs.speechace.com/getting-started/supported-languages
