# Automatic assessment of Quran recitation / Arabic pronunciation for learners: apps, models, datasets, metrics (landscape as of Oct 2026)

Research date: 2026-10-17. Status labels used below: **[peer-reviewed]**, **[preprint]**, **[workshop]**, **[marketing/app-store claim]**, **[3rd-party aggregator]**.

## 1. Products: what exists, who targets absolute beginners (Qaida level) with automatic feedback?

### Takeaway
The market leader, Tarteel, focuses on memorization (hifz). Its automatic feedback works at the word and tashkeel level and is paywalled. A newer wave of apps claims AI feedback at Qaida level (Al Siraat, Munabook, Nur Quran), but every claim comes from an app-store listing and none is independently evaluated. I found no Russian-, Kazakh- or Uzbek-language Telegram bot or app that automatically checks reading at "Муаллим ас-Сани" (letter/syllable) level. The closest is a Russian open-source MVP bot that compares whole verses with OpenAI ASR.

### Cited Findings
- **Tarteel (Tarteel Inc.).** The core paid feature is "Memorization Mistake Detection": the user hides the verses, recites, and the app "will alert you of any word level and tashkeel mistakes in real time" **[marketing]**. Other Premium features are Memorization Journey Planning, Peeking, Mistake History and Advanced Analytics. Recitation Follow-Along, Voice Search and Streaks are free. — [Tarteel support: Premium features](https://support.tarteel.ai/en/articles/12414460-what-features-do-i-unlock-with-tarteel-premium); [Tarteel: can I use for free](https://support.tarteel.ai/en/articles/12267535-can-i-use-tarteel-for-free)
- **Tarteel pricing conflicts across sources.**
  - The App Store in-app purchase list shows Monthly $12.99 / Annual $99.00, but also Premium Monthly $19.99 / Yearly $239.99 (likely regional or legacy tiers) — [apppricinglab (App Store data)](https://apppricinglab.com/app/apple/1391009396); [Tarteel: What's Premium](https://support.tarteel.ai/en/articles/12414387-what-s-tarteel-premium)
  - A third-party site gives about $7.50/month billed annually, and a Family plan covering up to 5 accounts — [similarlabs](https://similarlabs.com/pt/p/tarteel-ai)
  - An "Alim" subsidised-access program exists — [Tarteel support](https://support.tarteel.ai/en/articles/12414387-what-s-tarteel-premium)
- **Tarteel user numbers: no reliable 2025–2026 figure.**
  - CreatorDB claims "tens of millions of downloads", with no source **[3rd-party, unverified]** — [CreatorDB](https://creatordb.app/creatorstats/tarteelai/)
  - Adapty estimates about 40k downloads/month **[3rd-party]** — [Adapty](https://adapty.io/paywall-library/tarteel/{{i}})
  - A 2023 Tarteel blog post says Premium users spend 74% more time in the app (self-reported) — via [search summary of Tarteel blog](https://tarteel.ai/blog/tarteel-premium-is-free-this-month-heres-how-to-unlock-it/)
- **Tarteel's open model.** `tarteel-ai/whisper-base-ar-quran` is a Whisper-base fine-tune, Apache-2.0 licensed on Hugging Face. A third-party listing reports eval WER 5.75%, not confirmed on the card — [HF repo](https://huggingface.co/tarteel-ai/whisper-base-ar-quran/tree/e3f4a5f3f5336a1f0e43a2c2bdae62a680c53a8c); [PromptLayer](https://www.promptlayer.com/models/whisper-base-ar-quran). The Muaalem paper reports that its transcription step, a Tarteel Whisper-based ASR, had WER 5.7544% — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2).
- **Qaida-level apps that claim AI feedback (all [marketing/app-store]):**
  - **Al Siraat: Learn Quran with AI.** "Step-by-step, AI-powered Qaida lessons" covering Arabic letters, sounds and basic pronunciation, plus real-time mistake detection and a mistake log — [App Store](https://apps.apple.com/app/id6753738517)
  - **Munabook: Learn Quran.** AI pronunciation feedback for accuracy and fluency, Noorani Qaida support, some features under subscription — [App Store](https://apps.apple.com/app/id6569232688)
  - **Nur Quran.** Real-time voice analysis with "instant tajweed correction" and a full Qaida (Elif-Ba) — [mwm.ai listing](https://mwm.ai/apps/nur-quran/6764876011)
  - **Iqraa.** Noorani-method path from letters to tajweed. It compares user audio with a reference recitation, and the listing makes no AI claim — [mwm.ai](https://mwm.ai/apps/iqraa-qr/6450652768)
  - **Classic Noorani Qaida apps** (e.g., "Noorani Qaida with Audio") give audio per word, work offline and have no speech recognition — [search summary / appshunter](https://appshunter.io/ios/app/qurani-qaida/id1510779231/similar)
- **Other AI recitation apps (all [marketing]):**
  - **Tilawa.ai.** Record a surah and get feedback on pronunciation, tajweed, word mistakes and missed words; coaching on makharij, madd and ghunnah — [Similarweb listing](https://www.similarweb.com/app/google/ai.tilawa.app/)
  - **Qur'an SIDAQ.** AI feedback on tajwid and makhraj, plus the option to send recordings to human teachers — [mwm.ai](https://mwm.ai/apps/quran-sidaq/6755666354)
- **Quranly, Qariah, Quran Companion, Learn Quran Tafsir.** My searches returned no feature, pricing or user data for these. See Gaps.
- **Russian-language Telegram bots.**
  - The open-source MVP "Коран за 365 дней" (GitHub etbhitro/quran365) sends a daily passage. The user replies with a voice message; the bot transcribes it via the OpenAI API, shows mismatches with the text and computes a % match. Without an OpenAI key it cannot check audio. It works at word/verse level, not letter or tajweed level — [GitHub quran365](https://github.com/etbhitro/quran365)
  - Russian Telegram channels teach tajweed "starting from the alphabet" (e.g., "ЧИТАЙ КОРАН | ТАДЖВИД") but mention no automatic checking — [blackpot.ru listing](https://blackpot.ru/channel/tadjved)
  - The channel "Хафиза Корана" names "Муаллим Сани" as the standard step after basic tajweed rules, which confirms the textbook's role in Russian-speaking pedagogy — [t.me/s/hafiza_korana](https://telegram.me/s/hafiza_korana?before=1190)
- **Kazakh and Uzbek.** A Kazakh-language search returned no Quran-reading-check bot, only general AI-and-Quran reviews (e.g., Quranica journal). An Uzbek search for a "Muallimi soniy" app with AI pronunciation checking returned nothing relevant — [Quranica: AI in Quranic Education systematic review](https://ajba.um.edu.my/index.php/quranica/article/view/64955)
- **Possible building block.** The PyPI library `ijaza` validates Quran quotes and has an "ASR tolerant" mode — [PyPI ijaza](https://pypi.org/project/ijaza/)

### Inferences
- Existing products split into three groups:
  - memorization trackers at word/verse level (Tarteel, quran365 bot)
  - "AI tajweed" apps with unverified claims (Tilawa, SIDAQ, Nur Quran)
  - Qaida apps, most without automatic assessment and a few with unverified AI claims (Al Siraat, Munabook)
- No product found publishes accuracy figures for beginner letter or syllable reading.
- No product found works in Russian, Kazakh or Uzbek through Telegram at Муаллим ас-Сани level. That is the thesis niche.
- Because Tarteel and similar apps score at word level, they are not designed for isolated letters with harakat, which is what Муаллим ас-Сани drills. This is an inference from the feature descriptions, not tested.

### Gaps
- No data found for Quranly, Qariah, Quran Companion or Learn Quran Tafsir (features, pricing, users). Searches returned nothing on them, so check app-store pages manually.
- No verified 2025–2026 user counts for Tarteel.
- No Muallimi Soniy apps found in Uzbek or Kazakh stores through web search. Searching Google Play directly is advised.
- No independent evaluations of the AI claims of Al Siraat, Munabook, Nur Quran, Tilawa or SIDAQ.

## 2. Models: Quran Muaalem, IqraEval systems, Whisper/wav2vec2 fine-tunes, MDD methods

### Takeaway
Quran Muaalem is the most complete open (MIT) Quranic MDD model. It is a 0.6B Wav2Vec2-BERT model with 11 CTC heads (phonemes plus 10 sifat). It reports 0.21% average PER on expert test data, but on real error data (qdat_bench) it gets 5.78% phoneme PER and 0.758 tajweed F1. Ikhfaa is weak (F1 0.453), and it was trained only on expert male reciters.

On the IqraEval/QuranMB benchmark, the top 2026 system reached F1 0.720, up from a ~0.30 F1 baseline in 2025. The best systems are CTC-based SSL phoneme recognizers, often Wav2Vec2-BERT with two-stage fine-tuning and TTS-generated errors.

### Cited Findings
**Quran Muaalem (Abdelfattah, Khalil, Abbas)**
- **Status:**
  - arXiv 2509.00094 **[preprint]**: v1 27 Aug 2025; v2 dated 27 Aug 2026 on the arXiv page — [arXiv abs](https://arxiv.org/abs/2509.00094)
  - Also a poster at the ICML 2026 Affinity Event "6th Muslims in ML (MusIML) Workshop" **[workshop, not main-track peer review]** — [ICML 2026 virtual](https://icml.cc/virtual/2026/80144)
  - Title: "Automatic Pronunciation Error Detection and Correction of the Holy Quran's Learners Using Deep Learning"
- **Contributions:**
  - a 98%-automated data pipeline (expert recitations, segmentation at pause points, Tarteel-Whisper transcription, "Tasmeea" verification)
  - 848 h / 286K utterances
  - the Quran Phonetic Script (QPS), an 11-level notation of phonemes and sifat
  - qdat_bench, a 159-sample benchmark
  - a multi-level CTC model
  — [arXiv abs](https://arxiv.org/abs/2509.00094)
- **Architecture and training:**
  - Wav2Vec2-BERT encoder with 11 linear CTC heads and no LM
  - Loss weights: phonemes 0.4, others about 0.06–0.07
  - AdamW, constant LR 5e-5, batch size 64, 1 epoch, bf16, max 30 s
  - About 7 h on one H200
  - Augmentation: noise (Silero-VAD setup), TimeStretch, GainTransition. SpecAugment hurt performance and was dropped.
  — [arXiv 2509.00094v2 HTML](https://arxiv.org/html/2509.00094v2)
- **Results on the expert test set (moshafs 19, 29, 30):**

  | Level | PER |
  |---|---|
  | Phonemes | 0.543% |
  | hams/jahr | 0.117% |
  | shidda/rakhawa | 0.172% |
  | tafkheem/taqeeq | 0.167% |
  | itbaq | 0.092% |
  | safeer | 0.132% |
  | qalqla | 0.085% |
  | tikraar | 0.090% |
  | tafashie | 0.160% |
  | istitala | 0.080% |
  | ghonna | 0.130% |
  | **Average** | **0.21%** |

  — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **Results on qdat_bench (159 samples: 120 female, 39 male; bootstrap mean ± SD over 10k iterations):**

  | Metric | Value |
  |---|---|
  | Phoneme PER | 5.78% (6.03 ± 0.53) |
  | Average PER | 1.94% (1.97 ± 0.32) |
  | Average tajweed F1 | 0.758 (± 0.018) |
  | Tajweed accuracy | 0.847 |
  | Noon mushaddadah F1 | 0.869 |
  | **Ikhfaa F1** | **0.453** |
  | Qalqalah F1 | 0.953 |
  | Madd RMSE, average | 0.597 |
  | Madd RMSE, normal | 0.465 |
  | Madd RMSE, separate | 0.676 or 0.687 (inconsistent within the paper) |
  | Madd RMSE, aared | 1.034 |

  — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **Stated limitations:**
  - trained only on expert male reciters
  - Hafs only
  - letter-specific sifat (istitala for ض, tikraar for ر) are sparse
  - rare rules (imala, rawm, tasheel) are affected similarly
  - ikhfaa is weak because it sounds acoustically close to clear noon
  - qdat_bench has a single annotator and a single verse
  - no quantitative baseline comparison; Table 2 compares prior work only qualitatively
  — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **Internal inconsistencies in the paper:**
  - loss weights sum to about 1.08
  - phoneme vocabulary is given as 43 in one place and 44 with blank in another
  - "27 full recitations" vs 22 reciters
  — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **Model card `obadx/muaalem-model-v3_2`:**
  - MIT license; base `facebook/w2v-bert-2.0`; 0.6B params, F32
  - trained on obadx/muaalem-annotated-v3
  - Results and Limitations sections are empty
  - about 25.2k downloads in the last month, 11 likes
  — [HF model card](https://huggingface.co/obadx/muaalem-model-v3_2)
- **GitHub `obadx/quran-muaalem`:**
  - MIT license; default model v3_2 (badge links to v3_0); "660M params", about 1.5 GB GPU memory
  - pip package `quran-muaalem`, Gradio UI, and FastAPI engine/app servers on ports 8000/8001
  - phonetizer via `quran_transcript`, with configurable Hafs options (madd lengths, sakt, etc.)
  - 111 stars, 37 forks, 23 open issues, no formal releases
  — [GitHub](https://github.com/obadx/quran-muaalem)

**IqraEval / QuranMB benchmark (QCRI and partners)**
- **2025 benchmark paper.** El Kheir et al., "Towards a Unified Benchmark for Arabic Pronunciation Assessment: Quranic Recitation as Case Study", arXiv 2506.07722, accepted at Interspeech 2025 and the ArabicNLP 2025 Shared Task **[peer-reviewed, Interspeech]**. It introduces QuranMB.v1 and a 68-phoneme MSA set — [arXiv abs](https://arxiv.org/abs/2506.07722); [HTML v2](https://arxiv.org/html/2506.07722v2)
- **QuranMB.v1 baselines (PER / Precision / Recall / F1, %):**

  | Training data | Model | PER | Precision | Recall | F1 |
  |---|---|---|---|---|---|
  | CMV-Ar | wav2vec2 | 20.17 | 15.71 | 76.72 | 26.08 |
  | CMV-Ar | mHuBERT | 17.60 | 17.67 | 75.56 | 28.64 |
  | CMV-Ar+TTS | mHuBERT (best) | 16.42 | 18.70 | 74.29 | 29.88 |

  All baselines score F1 ≤ 30% with precision 13–19%: high recall, very low precision, i.e. many false alarms — [arXiv 2506.07722v2](https://arxiv.org/html/2506.07722v2)
- **Iqra'Eval 2025 shared task** (ArabicNLP 2025, ACL Anthology 2025.arabicnlp-sharedtasks.61). It has two subtasks, error localization and error diagnosis, and the shared-task pages say evaluation is on QuranMB.v2. The v1/v2 naming differs between the paper and the task pages — [Iqra'Eval site](https://iqraeval-arabicnlp2025.static.hf.space/index.html); [ACL Anthology preview](https://preview.aclanthology.org/setup/2025.arabicnlp-sharedtasks.61)
- **AraS2P (Matar, Fayed, Khalafallah; arXiv 2509.23504) [preprint/shared-task paper]** claims 1st place in Iqra'Eval 2025. It uses Wav2Vec2-BERT with task-adaptive continued pretraining on large Arabic speech→phoneme data (text phonemized), then fine-tuning with XTTS-v2 synthetic recitations that mimic errors. The exact F1 is not on the abstract page — [arXiv 2509.23504](https://arxiv.org/abs/2509.23504v1)
- **IQRA 2026 Interspeech Challenge** (El Kheir, Meghanani, Shahin, Ibrahim, Chowdhury, Almarwani, Elshahawy, Ali; arXiv 2603.29087, 31 Mar 2026) **[challenge overview, preprint]**:
  - 19 teams, up from 10
  - Top system **whu-iasp F1 = 0.7201**; UTokyo and RAM within 0.005
  - mHuBERT baseline F1 = 0.4414; 13/19 teams beat the baseline
  - The generative audio-LLM "Kalimat" placed 6th with F1 0.6702
  - Winning recipes: CTC-based SSL and two-stage fine-tuning
  - The reported gain over 2025 is inconsistent within the paper: +0.28 in the abstract, prior best ~0.47 in the intro, ~0.30 in Section 5.5
  — [arXiv 2603.29087](https://arxiv.org/html/2603.29087v1)

**Other models and approaches**
- Whisper fine-tune `tarteel-ai/whisper-base-ar-quran`, Apache-2.0 (see Section 1) — [HF](https://huggingface.co/tarteel-ai/whisper-base-ar-quran/tree/e3f4a5f3f5336a1f0e43a2c2bdae62a680c53a8c)
- Community derivative "Tarteel Base with Makharij Huruf" — [HF mark-muhammad/tarteel-base-finetuned](https://huggingface.co/mark-muhammad/tarteel-base-finetuned)
- **Rule-specific DNN classifiers on QDAT:**
  - "Evaluation of the Pronunciation of Tajweed Rules Based on DNN as a Step Towards Interactive Recitation Learning" (arXiv 2503.23470) — [arXiv](https://arxiv.org/abs/2503.23470)
  - "Mispronunciation Detection of Basic Quranic Recitation Rules using Deep Learning" (arXiv 2305.06429) — [arXiv](https://arxiv.org/abs/2305.06429v1)
  - I did not extract metrics from these two.
- **Critical review.** Al-Kharusi et al., "A Critical Review of the Need for Knowledge-Centric Evaluation of Quranic Recitation" (arXiv 2510.12858, Oct/Nov 2025) **[preprint]** argues:
  - ASR-derived systems "focus on identifying words rather than evaluating pronunciation quality"
  - they rely on biased datasets, show demographic disparities and give little pedagogical feedback
  - the authors recommend hybrid, knowledge-based systems (rule-based acoustic modelling of makharij plus data-driven audio)
  — [arXiv 2510.12858](https://arxiv.org/abs/2510.12858)

### Inferences
- The thesis can cite Quran Muaalem as a preprint plus ICML 2026 MusIML workshop poster. It should not call it a peer-reviewed main-conference paper.
- 0.21% PER is in-domain on experts. 5.78% phoneme PER on qdat_bench is the realistic figure for imperfect speakers.
- Muaalem's architecture (Wav2Vec2-BERT with CTC phoneme recognition, compared against the canonical phonetized text) is the same family as the IqraEval winners (AraS2P, whu-iasp). This justifies choosing it.
- The thesis could add a lightweight comparison baseline: the IqraEval mHuBERT baseline, or Tarteel Whisper used for word-level checks.
- For Муаллим ас-Сани (isolated letters, syllables, short words outside Quranic context), the main risk is domain mismatch. Muaalem is trained on continuous Quranic recitation segments, and its phonetizer expects Quranic text, so isolated letters and syllables may need custom canonical phoneme strings.

### Gaps
- Exact F1 of AraS2P and the full Iqra'Eval 2025 leaderboard: the HF Space returned 401 and the ACL Anthology preview returned 404.
- Whether a separate peer-reviewed journal version of Muaalem exists. Only arXiv and the ICML workshop poster were found.
- No published GOP-based results on QuranMB were found in this session.
- No 2025–2026 Arabic-specific GOP vs CTC comparison was located.

## 3. Datasets and licenses

### Takeaway
- **Open and permissively licensed:** the Muaalem training set (MIT, 848 h, expert reciters only) and QDAT (MIT per HF metadata).
- **No license on its HF page:** qdat_bench.
- **Learner or non-native data is scarce:**
  - RetaSy Quranic Audio Dataset: non-Arabic crowdsourced beginners, about 7k recitations
  - L2-KSU: gated
  - L2AraSpeech: non-commercial
  - Arabic-CAPT: 2.36 h
  - AraVoiceL2: 5.5 h
- **IqraEval data comes from native speakers:**
  - QuranMB.v1: 18 native speakers producing deliberate errors
  - Iqra_Extra_IS26: native speakers producing specified substitutions

### Cited Findings
- **obadx/muaalem-annotated-v3:**
  - MIT; about 847.99 h; 286,537 samples (row count 286,586)
  - "proficient reciters" (القراء المتقنين); reciters metadata has 22 rows
  - 27 moshaf configurations, train split only, 16 kHz mono
  - columns include uthmani/imlaey text, phonemes, 11 sifat levels and match_ratio
  - annotation is automatic via quran-transcript, with no manual review described
  - no learner data
  — [HF dataset card](https://huggingface.co/datasets/obadx/muaalem-annotated-v3)
- **Pipeline manual share.** 5,400 of 286,537 utterances were manually annotated (the "98% automated" figure) — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **qdat_bench (obadx/qdat_bench):**
  - 159 samples, apparently one per reciter out of the original QDAT's 161 reciters
  - labels: madd lengths (0–8), noon mushaddadah/mukhfah lengths, qalqalah (0/1), sifat sequences, gender and age
  - no license stated on the page; annotator not described on the card
  - the paper says one expert re-annotator and one verse (5:109)
  — [HF qdat_bench README](https://huggingface.co/datasets/obadx/qdat_bench/blob/main/README.md); [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **QDAT (Osman et al., 2021):**
  - 1,505 recordings of Al-Ma'idah 5:109
  - binary labels for separate madd, tight noon (ghunnah) and ikhfaa; no qalqalah
  - each reciter recorded the verse 10 times
  - HF metadata says MIT
  — [HF obadx/qdat README](https://huggingface.co/datasets/obadx/qdat/blob/main/README.md); [arXiv 2509.00094](https://arxiv.org/pdf/2509.00094)
- **QuranMB.v1:**
  - 98 verses, 18 native speakers (14 F, 4 M), about 2.2 h
  - MSA reading ignoring tajweed, with deliberately inserted errors cued by a tool
  - dataset license not stated in the paper
  - released at huggingface.co/IqraEval
  — [arXiv 2506.07722v2](https://arxiv.org/html/2506.07722v2)
- **IqraEval training data:**
  - CMV-Ar: Common Voice Arabic 12.0 plus Quranic samples; 79 h train (71,391 utt.) + 3.33 h dev
  - TTS: 52 h in the text vs 45 h in Table 1 (inconsistent)
  — [arXiv 2506.07722v2](https://arxiv.org/html/2506.07722v2)
- **IqraEval 2026 data:**
  - Iqra_train: about 79 h / 74k utterances, expert vowelization, Halabi phonetization
  - Iqra_TTS: about 52 h
  - Iqra_Extra_IS26: 1,333 utterances (about 1.5 h) of real mispronounced speech from native speakers
  - QuranMB.v2 test: 1,643 utterances (about 2.5 h), validated by 3 Arabic linguistic experts
  — [arXiv 2603.29087](https://arxiv.org/html/2603.29087v1)
- **RetaSy Quranic Audio Dataset** (Salameh, Al Mdfaa, Askarbekuly, Mazzara; arXiv 2405.02675, 2024):
  - about 7,000 recitations from 1,287 participants in 11+ non-Arabic countries, collected via NamazApp
  - 1,166 recitations annotated into 6 categories by proficient reciters on "Quran Voice"
  - crowd accuracy 0.77; inter-annotator agreement 0.63; algorithm–expert agreement 0.89
  - on HF as RetaSy/quranic_audio_dataset (about 1.26 GB parquet)
  - license not verified in this session
  - this is the closest public dataset to "non-native Quran beginners"
  — [arXiv 2405.02675](https://arxiv.org/html/2405.02675v1); [HF](https://huggingface.co/datasets/RetaSy/quranic_audio_dataset/blob/main/README.md)
- **Arabic L2 (non-Quranic MSA) MDD corpora:**
  - **L2-KSU** (King Saud University): native and non-native read speech with phone-level error annotations; gated on HF; linked to Alrashoudi et al., "Improving mispronunciation detection and diagnosis for non-native learners of the Arabic language", *Discover Computing* 28(1):1, 2025 **[peer-reviewed journal]** — [HF L2-KSU](https://huggingface.co/datasets/IWAN/L2-KSU-Dataset); [Springer](https://link.springer.com/10.1007/s10791-024-09489-8)
  - **L2AraSpeech:** 220 non-native speakers, 60 annotated for errors; non-commercial research license — [IEEE DataPort](https://ieee-dataport.org/documents/l2araspeech)
  - **Arabic-CAPT** (62 non-native speakers, 20 nationalities, 2.36 h) and **AraVoiceL2** (11 speakers, 5.5 h) are cited in search snippets — [search result: MUET journal](https://publications.muet.edu.pk/index.php/muetrj/article/download/2081/503) — **these numbers come from snippets only and should be verified**
- **Quran-MD** (Salman, Qazi, Alam; arXiv 2601.17880, Jan 2026; CC0):
  - verse-level audio from 32 reciters, plus word-level aligned audio with transliteration and translation
  - useful for word-level reference audio
  - no assessment experiments
  — [arXiv 2601.17880](https://arxiv.org/abs/2601.17880)

### Inferences
- For a Муаллим ас-Сани bot, none of the existing datasets covers isolated-letter or syllable reading by Russian, Kazakh or Uzbek speakers. The thesis will likely need to collect a small annotated test set from target learners. Even 30–50 speakers would be novel, given that the IqraEval organizers themselves list "L2 learner data collection" as future work.
- RetaSy is the best external proxy for non-native Quran beginners.
- QuranMB.v1/v2 is the proxy for a standardized MDD benchmark, though it covers native speakers.

### Gaps
- Licenses not verified in this session: RetaSy dataset, IqraEval HF datasets, EveryAyah, Tarteel public datasets.
- Common Voice Arabic license: not fetched. It is generally CC0 (background knowledge, not verified here).
- No Russian-, Kazakh- or Uzbek-L1 Arabic pronunciation dataset was found.

## 4. Metrics: how to evaluate MDD

### Takeaway
The IqraEval/QuranMB standard uses:
- a TA/TR/FA/FR confusion matrix at the phoneme level
- Precision = TR/(TR+FR), Recall = TR/(TR+FA), F1 as the primary metric
- PER for recognition quality
- a Correct Diagnosis rate for diagnosis

Muaalem additionally reports per-rule F1, accuracy and RMSE for madd duration, with bootstrap confidence intervals. Learner-facing validity measures (correlation with teachers, inter-annotator agreement) appear only in RetaSy (agreement 0.63).

### Cited Findings
- **IqraEval / QuranMB metric definitions:**
  - Precision = TR / (TR + FR)
  - Recall = TR / (TR + FA)
  - F1 = 2PR / (P + R)
  - PER is used for model selection
  - TA, TR, FA, FR, CD and ED are named but not all formally defined in the paper
  — [arXiv 2506.07722v2](https://arxiv.org/html/2506.07722v2)
- **IQRA 2026:** F1 is the ranking metric, computed from TR, FR and FA, alongside precision, recall and PER. Table 2 also reports TA, FR, FA and Correct Diagnosis rates — [arXiv 2603.29087](https://arxiv.org/html/2603.29087v1)
- **Muaalem metrics:**
  - per-level PER
  - per-rule tajweed F1 and accuracy
  - Madd RMSE (in counts)
  - accuracy split by gender
  - 10,000-iteration bootstrap mean ± SD
  — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- **Annotation reliability (RetaSy):** inter-annotator agreement 0.63 and crowd accuracy 0.77 against experts — [arXiv 2405.02675](https://arxiv.org/html/2405.02675v1)
- **Pedagogical framing.** The IQRA 2026 organizers note that phoneme-level output does not map cleanly to the Arabic script learners read, so learner-facing feedback is limited — [arXiv 2603.29087](https://arxiv.org/html/2603.29087v1)
- **Reliability and fairness.** Al-Kharusi et al. call for evaluation tools that are "reliable, fair, and pedagogically effective" and flag demographic disparities — [arXiv 2510.12858](https://arxiv.org/abs/2510.12858)

### Inferences
- **Recommended metric set for the thesis:**
  1. PER of the recognizer on the learner test set
  2. MDD precision, recall and F1 with IqraEval definitions, for comparability
  3. FAR/FRR expressed as False Accept rate (missed errors) and False Reject rate (correct readings flagged)
  4. per-letter or per-error-type breakdown, with special attention to letter pairs Russian/Kazakh/Uzbek speakers confuse (ح/ه, ع/ء, ق/ك, ص/س, ض/د, ط/ت, ظ/ز, ث/س, ذ/з)
  5. agreement between the bot and teachers (Cohen's κ, or Pearson/Spearman for scores), compared against teacher–teacher agreement as the ceiling
  6. bootstrap confidence intervals
- **On FAR/FRR for beginners:** a high False Reject rate (scolding correct readings) is pedagogically more harmful. The 2025 baselines' pattern of low precision and high recall would produce exactly that, so the thesis should report the decision threshold and the operating point.
- **Background, not verified in this session:** the hierarchical MDD evaluation scheme (TA/TR/FA/FR, then Correct Diagnosis/Diagnosis Error inside TR) originates from Qian et al. / Li et al. on L2-ARCTIC. It should be cited from the original sources after verification.

### Gaps
- No paper found that reports correlation between automatic Quranic scores and human teacher ratings for beginners.
- No source fetched that formally defines Correct Diagnosis / Error Diagnosis for QuranMB.

## 5. Known gap: performance on beginners and non-native (Russian/Kazakh/Uzbek) speakers

### Takeaway
I found no study evaluating Quran Muaalem, Tarteel or the IqraEval systems on Russian-, Kazakh- or Uzbek-speaking learners, or on Qaida-level isolated letters. All the evidence points to a domain gap:
- Muaalem: expert male training data → PER rises from 0.21% to 1.94% average (5.78% phoneme) on qdat_bench
- IqraEval: native-speaker data only, with L2 learners named as future work
- Critical reviews: demographic bias

### Cited Findings
- Muaalem was trained only on expert male reciters, and the authors flag possible poor generalization to other voices. qdat_bench (75% female) gives 5.78% phoneme PER vs 0.543% on the expert test set — [arXiv 2509.00094v2](https://arxiv.org/html/2509.00094v2)
- IQRA 2026 "contains no L2 learner data" and lists "L2 learner data collection" as a priority. It distinguishes dialect-L1 errors from non-Arabic learner errors — [arXiv 2603.29087](https://arxiv.org/html/2603.29087v1)
- QuranMB.v1 uses 18 native speakers producing scripted errors, not natural learner errors — [arXiv 2506.07722v2](https://arxiv.org/html/2506.07722v2)
- ASR-based Quranic tools show "demographic disparities" and rely on biased datasets — [arXiv 2510.12858](https://arxiv.org/abs/2510.12858)
- The RetaSy dataset is the only located Quranic dataset of non-Arabic beginners (11+ countries). Its paper (as summarized) reports no model-accuracy breakdown by L1 — [arXiv 2405.02675](https://arxiv.org/html/2405.02675v1)
- L2-KSU / Alrashoudi et al. 2025 address MDD for non-native Arabic learners (MSA, not Quran). Specific L1 groups and results were not extracted — [Springer](https://link.springer.com/10.1007/s10791-024-09489-8)

### Inferences
- The thesis contribution can be framed as the first evaluation of an open Quranic MDD model (Muaalem) on (a) Qaida/Муаллим ас-Сани-level material and (b) Russian/Kazakh/Uzbek-L1 beginners, delivered via Telegram. Possible extensions:
  - error-type analysis of L1-specific confusions
  - optional light fine-tuning on a small learner set (MIT license allows it)
- Expect elevated false rejects for female, child and non-native voices, and for very slow syllable-by-syllable reading typical of beginners. The thesis should measure this rather than assume it.

### Gaps
- No studies located on Russian-, Kazakh- or Uzbek-L1 Arabic or Quranic pronunciation assessment, in English, Russian or Kazakh searches. Searches in eLibrary.ru or CyberLeninka were not performed.
- No data on model behavior for isolated letters with harakat, or for children's voices.

## 6. License compatibility of Muaalem for academic use and fine-tuning

### Takeaway
All three Muaalem artifacts (code, model and training dataset) are MIT-licensed according to GitHub and the Hugging Face cards. That permits academic use, modification, fine-tuning and redistribution with the copyright notice kept.

Caveats:
- The base model `facebook/w2v-bert-2.0` has its own license, not verified here.
- qdat_bench has no license on its card.
- Recitation audio originates from reciters' recordings, whose upstream rights are not documented on the dataset card.

### Cited Findings
- GitHub `obadx/quran-muaalem`: MIT license (badge and LICENSE) — [GitHub](https://github.com/obadx/quran-muaalem)
- Model `obadx/muaalem-model-v3_2`: MIT in metadata; fine-tuned from `facebook/w2v-bert-2.0` — [HF model](https://huggingface.co/obadx/muaalem-model-v3_2)
- Dataset `obadx/muaalem-annotated-v3`: MIT — [HF dataset](https://huggingface.co/datasets/obadx/muaalem-annotated-v3)
- qdat_bench: no license stated — [HF qdat_bench](https://huggingface.co/datasets/obadx/qdat_bench/blob/main/README.md)
- Original QDAT: MIT per HF metadata — [HF qdat](https://huggingface.co/datasets/obadx/qdat/blob/main/README.md)
- The paper text is CC BY 4.0 on arXiv — [arXiv abs](https://arxiv.org/abs/2509.00094)
- Tarteel Whisper base: Apache-2.0 — [HF](https://huggingface.co/tarteel-ai/whisper-base-ar-quran/tree/e3f4a5f3f5336a1f0e43a2c2bdae62a680c53a8c)

### Inferences
- Academic use and fine-tuning are compatible with MIT. Attribute the work, cite arXiv 2509.00094, and keep the MIT notice when redistributing a fine-tuned checkpoint.
- For qdat_bench, use it only for evaluation, cite the source, and contact the author or note the missing license in the thesis.

### Gaps
- License of `facebook/w2v-bert-2.0`: not checked. I believe it is MIT, but this is unverified in this session.
- Upstream copyright of the reciters' audio inside muaalem-annotated-v3: not documented.
