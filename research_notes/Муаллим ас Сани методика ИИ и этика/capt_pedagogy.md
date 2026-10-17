# CAPT and automated pronunciation/reading feedback: pedagogical grounding for an Arabic-reading Telegram bot ("Муаллим ас-Сани")

Scope note: the notes below were compiled from web searches and fetches on 2026-10-17, about 20 tool calls. Some figures come from search-engine abstracts or snippets rather than full texts, and those are labelled. Items recalled from memory that could not be verified in this session are listed only under "Gaps".

## 1. Effectiveness of CAPT / ASR-based pronunciation feedback (meta-analyses, reviews)

### Takeaway
Meta-analyses consistently find **medium-sized positive effects** for CAPT/ASR-based training. Ngo, Chen & Lai (ReCALL) report g = 0.69, and the effects are largest for **segmental** accuracy (individual vowels and consonants) and for **explicit** corrective feedback. This is close to what an Arabic-letter reading checker does. Most of the evidence comes from adult ESL/EFL learners in short quasi-experiments, and the comparison condition is usually no-ASR or traditional instruction. It is not a well-specified "human teacher feedback" condition, so the data do not show that CAPT is *equivalent* to a teacher.

### Cited Findings
- **Ngo, Chen & Lai, "The effectiveness of automatic speech recognition in ESL/EFL pronunciation: A meta-analysis," ReCALL 36(1), 4–21 (online 2023, print 2024).** 15 studies, 38 effect sizes, overall **g = 0.69** (medium). Moderators: explicit corrective feedback gave large effects, while indirect feedback (e.g., ASR dictation/transcript only) gave moderate effects. Effects were large for segmental features and small for suprasegmentals. Medium-to-long treatments did better. Practice with peers gave a large effect and solo practice a small one. Effects were strongest for adults and intermediate learners. — [Cambridge ReCALL](https://resolve.cambridge.org/core/journals/recall/article/effectiveness-of-automatic-speech-recognition-in-eslefl-pronunciation-a-metaanalysis/A915444CF252B61D14961D2FE733822D) (summary via search abstract. I could not fetch the full text, so moderator g-values and CIs are not reported here.)
- **Mahdi & Al Khateeb (2019), "The effectiveness of computer-assisted pronunciation training: A meta-analysis," Review of Education 7(3).** 20 studies. CAPT improves L2 pronunciation, especially for **beginner and intermediate** learners. — [described in Amrate & Tsai 2025 / search snippet](https://resolve.cambridge.org/core/services/aop-cambridge-core/content/view/71E786F7DFC99727837909FDED7A2320/S0958344024000181a.pdf/computer-assisted-pronunciation-training-a-systematic-review.pdf). **Uncertain details:** the DOI appears as both 10.1002/rev3.3165 and 10.1002/rev3.3164 in different records ([sindex.sdl.edu.sa](https://sindex.sdl.edu.sa/esploro/outputs/journalArticle/Context-and-Implications-Document-for-The/9910320308331)), and I could not retrieve the pooled effect size. Check both before citing.
- **Almusharraf, Mahdi, Al-Nofaie & Aljasser (2024), Journal of Computer Assisted Learning 40(4), 1605–1615, DOI 10.1111/jcal.12974.** CAPT meta-analysis of 31 primary studies and 42 effect sizes, with setting, educational level and tool as moderators. **The pooled effect size was not retrieved.** — [ERIC record EJ1431925 via nufind](https://nufind.nu.edu.sa/EdsRecord/eric,EJ1431925)
- **Amrate & Tsai (2025), "Computer-assisted pronunciation training: A systematic review," ReCALL 37(1), 22–42 (online Sept 2024).** 30 empirical studies, 1999–2022.
  - Most learners were adults learning English at intermediate level. Segmentals were studied more than suprasegmentals.
  - Practice was almost all controlled: drilling, listen-and-repeat, read-aloud.
  - Feedback: 11 studies used explicit feedback, 6 implicit (spectrogram only), 11 combined, 2 none. 16 used ASR and 14 did not.
  - ASR often fails on accented and children's speech and can give **erroneous feedback on comprehensible pronunciation**. The review recommends **collaborative/supervised CAPT, where teachers or peers compensate for faulty system feedback**.
  - Design weaknesses: mostly quasi-experimental, with 20 control-group designs. Sampling was unspecified in 14 studies. Samples ranged from 5 to 132 (mean ≈ 47). Durations ran 1–32 weeks (mean ≈ 7). — [Cambridge](https://www.cambridge.org/core/journals/recall/article/computerassisted-pronunciation-training-a-systematic-review/71E786F7DFC99727837909FDED7A2320)
- **Lee, Jang & Plonsky (2015), Applied Linguistics 36(3).** Meta-analysis of L2 pronunciation instruction in general (not CAPT only): 86 reports, **d = 0.89** within-group and **d = 0.80** between-group. Larger effects came from longer interventions, **treatments providing feedback**, and more controlled outcome measures. — [NAU Experts](https://experts.nau.edu/en/publications/the-effectiveness-of-second-language-pronunciation-instruction-a-/). Saito & Plonsky (2019) describe d = 0.80 as "medium" by L2 benchmarks. — [UCL Discovery](https://discovery-pp.ucl.ac.uk/10068780/1/LL2019.pdf)
- **Stoughton & Kang (2024), Languages.** Systematic review of mobile-assisted pronunciation training. Per-study Cohen's d varied widely, from large to negligible. — [DOAJ](https://doaj.org/article/de74fb67773241559297bf066053c144)
- **Neri, Cucchiarini & Strik (Interspeech 2006).** Three groups of immigrant learners of Dutch: ASR tool with feedback, the same tool without feedback, and no tool. **ASR-based feedback was effective in correcting the errors addressed in training.** — [ISCA Archive](https://www.isca-archive.org/interspeech_2006/neri06_interspeech.html)

### Inferences
- The bot's task is close to the conditions where CAPT works best: segmental, controlled read-aloud, explicit feedback, beginners. That makes the effect-size literature relevant. Arabic letters, harakat and short words are a controlled segmental task.
- Effect sizes for CAPT (≈0.5–0.7) are similar to or somewhat below those for pronunciation instruction in general (≈0.8–0.9). That is evidence for **augmentation and scaling of practice**, not for replacing teachers.
- The Neri et al. 2006 design (feedback vs. same tool without feedback vs. control) maps directly onto an A/B design for the thesis: bot with explanations vs. bot with only a right/wrong signal.

### Gaps
- Full-text moderator effect sizes and CIs for Ngo et al. were not retrieved. The PDF fetch returned unreadable binary.
- Pooled effect sizes for Mahdi & Al Khateeb (2019) and Almusharraf et al. (2024) were not retrieved.
- I found no meta-analysis that directly compares CAPT feedback with **human teacher feedback** as an active control. The claim that a bot can "replace" a teacher therefore has no direct meta-analytic support.
- Nothing was found for L1-Russian learners of Arabic specifically.
- Cucchiarini, Neri & Strik (2009, Speech Communication 51), "Oral proficiency training in Dutch L2: The contribution of ASR-based corrective feedback," is known to me, but its details could not be verified in this session.

## 2. Feedback design: explicit vs. implicit, metalinguistic, error rates, false alarms

### Takeaway
Explicit and specific feedback is consistently better than implicit feedback, both in CAPT (Ngo et al.) and in classroom oral corrective feedback research (Lyster & Saito 2010: prompts > recasts). The main technical risk is **false alarms**. Even state-of-the-art mispronunciation detectors reach only about 60% precision and 40–80% recall. I found no study that directly measures the effect of false alarms on learner trust. That is a gap the thesis could address.

### Cited Findings
- In CAPT, explicit corrective feedback gives large effects and indirect feedback gives moderate effects. — [Ngo, Chen & Lai, ReCALL](https://resolve.cambridge.org/core/journals/recall/article/effectiveness-of-automatic-speech-recognition-in-eslefl-pronunciation-a-metaanalysis/A915444CF252B61D14961D2FE733822D)
- **Lyster & Saito (2010), "Oral feedback in classroom SLA," Studies in Second Language Acquisition 32, 265–302.**
  - 15 classroom studies, N = 827. Corrective feedback had **significant and durable** effects.
  - Prompts (elicit self-correction) were more effective than recasts, and younger learners benefited more. The second-hand summary attributes "medium for recasts, large for prompts" to this study, but I could not confirm that attribution. — [Cambridge SSLA](https://resolve.cambridge.org/core/journals/studies-in-second-language-acquisition/article/oral-feedback-in-classroom-sla/4999EE1C8379B2BF026B148EAF373CA1)
  - Learners tend to want **more** corrective feedback than teachers think they should give. — [Lyster, Saito & Sato review, Language Teaching](https://www.cambridge.org/core/journals/language-teaching/article/abs/oral-corrective-feedback-in-second-language-classrooms/B33FC71C12A1317DCA0CE704B7B0BC00)
- **Neri, Cucchiarini & Strik (ICSLP 2002), "Feedback in CAPT: technology push or demand pull?"** Many commercial CAPT products favour technical novelty over pedagogical criteria. The authors argue that pedagogically sound CAPT is possible with current technology. — [ISCA Archive](https://www.isca-archive.org/icslp_2002/neri02_icslp.html)
- **Hansen (2006) criteria for CAPT feedback, cited in a DFKI survey:**
  - the feedback is comprehensible;
  - it detects whether the correct phoneme was used;
  - it detects whether phoneme length was correct;
  - it gives guidance for improvement.

  — [DFKI survey (R. Ai)](https://www-live.dfki.de/fileadmin/user_upload/import/7337_audio_feedback.pdf). Phoneme length matters for Arabic (long vs. short vowels, madd).
- **Detector accuracy.** State-of-the-art L2 mispronunciation detection has roughly **60% precision** (only 6 of 10 flagged "errors" are real) and **40–80% recall**. Source: Korzekwa et al. 2022, as cited by an Icelandic CAPT group. — [research-publishing.net chapter](https://research-publishing.net/publication/chapters/978-2-38372-015-7/1480.pdf). Modelling uncertainty, and allowing more than one correct pronunciation, raised precision by up to 18% relative. — [arXiv 2101.06396](https://www.arxiv.org/pdf/2101.06396)
- **Reported false-reject / false-accept rates**, from different datasets and not directly comparable:
  - FRR 8.0% / FAR 32.6% (Japanese learners of Chinese) — [Interspeech 2014](https://www.isca-archive.org/interspeech_2014/duan14_interspeech.html)
  - FAR 29.2% / FRR 22.9% (another system) — [Signal journal](https://signal.ejournal.org.cn/en/article/doi/10.16798/j.issn.1003-0530.2020.06.020)
  - Discriminative training can lower false rejections at a small cost in false acceptances, so the operating point is tunable. — [Qian et al., Interspeech 2010](https://www.isca-archive.org/interspeech_2010/qian10b_interspeech.html)
- **Two ASR-specific risks:**
  - Modern ASR with strong language models tends to "reconstruct" what the learner intended and so **masks real mispronunciations**. Systems with lower WER masked more errors. — [BEA 2026 paper, S. Park, ACL Anthology listing](https://aclanthology.org/people/seongjin-park/unverified/)
  - ASR errors can produce feedback that looks like a learner error and confuses learners. ASR confidence scores are proposed as a mitigation. — [Lu et al., Interspeech 2019](https://www.isca-archive.org/interspeech_2019/lu19b_interspeech.pdf)
- **Quranic Arabic specifically:** standard WER systematically **underestimates** ASR failure on tajweed-relevant errors, which motivated a "TajweedWER" metric (tested on Al-Fatiha with 8 reciters). — [ICML 2026 listing](https://icml.cc/virtual/2026/80190)

### Inferences
- **Precision over recall.** For beginners, a false alarm (telling a learner a correct reading is wrong) is probably more harmful than a missed error. It undermines trust and can push the learner to "correct" a right form. This is my inference: I found no direct trust study. Design recommendations that follow:
  - flag an error only when model confidence is high;
  - otherwise say "not sure, please repeat" or route the attempt to a teacher;
  - report precision and recall (or FAR/FRR) of the error flags separately in the thesis, not only WER/CER.
- Do not let an LLM/ASR language model "auto-correct" the transcript. Constrained or forced-alignment recognition against the expected letter or word is preferable, given the error-masking finding.
- **Feedback content,** following the explicit/metalinguistic evidence and Hansen's criteria: say *which* letter or haraka was wrong, *what* was heard vs. expected, and give a short articulatory tip in Russian (place of articulation, length). Then ask for an immediate retry, which is a "prompt" in the sense of Lyster & Saito: elicit self-correction rather than just modelling the answer.
- **How many errors to show:** I found no CAPT-specific evidence. Limiting feedback to 1–2 highest-confidence errors per attempt is a defensible design choice based on cognitive load, but it should be labelled as a design choice, not an evidence-based finding.

### Gaps
- No study was found that measures how false alarms affect learner trust, motivation or learning, and no empirically established "acceptable error rate" threshold was found. The thesis could measure this, for example with a learner rating of whether the feedback was correct, and teacher verification.
- No direct CAPT evidence was found on immediate vs. delayed feedback, or on the optimal number of errors shown per attempt.
- Visual feedback (spectrograms/waveforms): Amrate & Tsai count 6 implicit-spectrogram studies but do not separately analyse effectiveness.

## 3. Human-in-the-loop / hybrid models

### Takeaway
The CAPT and Quran-app literature points toward **hybrid use**. The system provides scalable drill and immediate feedback, and teachers or peers supervise, correct faulty flags and handle what ASR cannot (prosody, tajweed nuance, motivation). Note that in Ngo et al., practice with peers gave larger effects than solo practice.

### Cited Findings
- Amrate & Tsai recommend **supervised or collaborative CAPT**, in which teachers or peers compensate for faulty system feedback, since ASR often fails on accented and child speech. — [Cambridge ReCALL 2025](https://www.cambridge.org/core/journals/recall/article/computerassisted-pronunciation-training-a-systematic-review/71E786F7DFC99727837909FDED7A2320)
- Peer-practice ASR conditions gave large effects, compared with small effects for solo practice. — [Ngo, Chen & Lai](https://resolve.cambridge.org/core/journals/recall/article/effectiveness-of-automatic-speech-recognition-in-eslefl-pronunciation-a-metaanalysis/A915444CF252B61D14961D2FE733822D)
- **Tarteel (AI Quran memorisation app), PRISMA systematic review:** Mustapa, Mohd Saad & Ismail (2025), QURANICA 17(2).
  - The app provides automated correction and instant feedback that help memorisation.
  - Tajwid-recognition accuracy still needs improvement.
  - **Human teachers remain central**, partly for religious reasons (sanad, barakah). The app is best used as a "supplementary tool for memorizing and reviewing."

  — [QURANICA](https://ejournal.um.edu.my/index.php/quranica/article/view/64936)
- **Chatbot vs. human partner.** Fryer et al. (2017), Computers in Human Behavior 75, 461–468: in a language course, interest was equal at the first task. Interest under the chatbot partner then **dropped (a novelty effect)**. Human-partner task interest predicted later course interest and chatbot-partner interest did not. — [HKU Hub](https://hub.hku.hk/handle/10722/241841) / [datalearner listing](https://datalearner.com/academic/journal-papers/0747-5632/volumes-and-issues/187/paper-detail/36965)

### Inferences
- The defensible thesis claim is "the bot scales practice and first-line feedback and reduces teacher workload by triaging." It is not "the bot replaces the teacher."
- **Suggested hybrid architecture:**
  - The bot auto-handles high-confidence correct and incorrect cases.
  - Low-confidence attempts, and attempts the learner disputes ("I think I was right"), are queued for teacher review.
  - Teachers review a random sample to audit accuracy.
  - Teacher time saved and the agreement rate between bot and teacher become thesis metrics.
- In a religious-text context (Quran reading), learners and communities may expect a human chain of transmission. A design that positions the bot as preparation for, or a supplement to, a teacher is more acceptable.

### Gaps
- No quantitative study was found of teacher-review workflows for AI pronunciation flags: workload savings, or agreement rates between teachers and CAPT on beginner Arabic.

## 4. Spaced repetition, mastery learning, motivation and chatbot/messenger learning

### Takeaway
Spacing is among the most robust effects in learning science and supports scheduled review of letters. Chatbot-based language learning shows moderate pooled effects (g ≈ 0.5–0.6), but the effects are strongest in **short interventions**, consistent with novelty effects. Messenger-bot evidence specifically is thin and low-quality (small quasi-experiments).

### Cited Findings
- **Cepeda, Pashler, Vul, Wixted & Rohrer (2006), Psychological Bulletin 132(3), 354–380.** 839 assessments of distributed practice across 317 experiments in 184 articles. Spaced study beats massed study. The optimal inter-study interval increases with the desired retention interval. — [PubMed 16719566](https://pubmed.ncbi.nlm.nih.gov/16719566/). A secondary source says spacing gives about 15% more retention on average, but this was not verified in the original. — [Wooclap blog](https://www.wooclap.com/en/blog/why-you-should-teach-your-students-about-spaced-practice/)
- **Chatbot meta-analyses:**
  - Lyu et al. (2024), Int. J. Applied Linguistics: 31 studies, 41 effect sizes, **g = 0.608** on L2 learning, high heterogeneity.
  - A Review of Educational Research meta-analysis (28 studies, 70 effect sizes) reports **g = 0.484**. Its attribution to Wang et al. 2024 is **uncertain**.
  - Zhang et al. (2023), Education and Information Technologies: 18 studies, g = 0.527.
  - Li, Wang & Yang (JCAL): GenAI chatbots, 41 studies, ES = 0.576.

  — [search summary of UCLouvain listing "Hype or hope?"](https://research.dial.uclouvain.be/entities/publication/29791a54-111b-40eb-bacb-346494980619), [CityU Scholars](https://scholars.cityu.edu.hk/en/publications/effect-ofchatbotassisted-language-learning-ametaanalysis/), [citedrive JCAL 10.1111/jcal.70060](https://www.citedrive.com/en/discovery/can-generative-scpaiscp-chatbots-promote-second-language-acquisition-a-metaanalysis/). These attributions come from search snippets, so verify them before citing.
- **Wu & Yu (2024), British Journal of Educational Technology 55(1).** Meta-analysis of 24 randomised studies of AI chatbots on learning outcomes in general, with a large effect. **Short interventions had stronger effects than long ones**, which the authors interpret as a fading novelty effect. — [HKU Hub](https://hub.hku.hk/handle/10722/355065) (the pooled value was not retrieved)
- **Messenger studies:**
  - **Telegram bot (Werewolf game bot), Indonesia:** quasi-experiment with 60 high-school students; vocabulary mastery improved significantly vs. placebo. — [UPI JER](https://ejournal.upi.edu/index.php/JER/article/view/37421)
  - **Telegram as a channel, not a bot (Frontiers in Psychology 2022):** 60 Iranian EFL learners, randomised to experimental and control groups, 18 sessions. Motivation increased and foreign-language anxiety decreased compared with control. — [PMC9521357](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9521357/)

### Inferences
- **Design implications:**
  - Use spaced review of letters and words the learner previously got wrong, i.e., expanding intervals.
  - Use mastery gating: do not advance to the next lesson of Муаллим ас-Сани until accuracy on the current letters reaches a threshold.
  - Expect engagement to decline after the novelty wears off. Plan reminders, streaks and teacher contact, and report retention/dropout curves rather than only pre/post gains.
- Gamification evidence specific to messenger bots was not found in rigorous form. Treat it as a design hypothesis.

### Gaps
- No reliable published **dropout/retention rates** for Telegram/WhatsApp learning bots were found.
- Mastery-learning meta-analyses (e.g., Kulik, Kulik & Bangert-Drowns 1990, Review of Educational Research) are known to me, but their effect sizes were not verified this session.
- Huang, Hew & Fryer (2022, JCAL) on chatbots for language learning, and Duolingo-type retention data, were not retrieved.

## 5. Arabic / Quran reading technology studies

### Takeaway
Quran/tajweed technology research is dominated by **ASR prototype accuracy studies with tiny samples** and by Indonesian/Malaysian app-development papers with weak one-group pre/post designs. I found **no RCT** showing learning gains in Arabic letter or Quran reading from automated pronunciation feedback. The thesis pilot would therefore add new evidence, but it cannot lean on strong prior outcome data.

### Cited Findings
- **Tarteel app SLR (2025):** helps memorisation through instant feedback. Tajwid-recognition accuracy is limited, and human teachers remain essential. — [QURANICA 17(2)](https://ejournal.um.edu.my/index.php/quranica/article/view/64936)
- **Surah Al-Mulk ASR memorisation prototype (beginners, one verse a day):** tested with **4 participants**, CER 13.69% and WER 13.13% ("moderate"), positive expert evaluation. — [UiTM IR](https://ir.uitm.edu.my/id/eprint/146115/1/146115.pdf) (details from a search summary)
- **Literature review of Quran recitation evaluation (arXiv, Oct 2025):** automated tools have "failed to achieve widespread adoption or pedagogical efficacy." — [arXiv 2510.12858](https://arxiv.org/pdf/2510.12858v1)
- **Teachable Machine hijaiyah-letter recognition:** real-time recognition of selected letters, tested with 2 participants. — [UNISSA JIT](https://unissa.edu.bn/journal/index.php/JIT/article/download/1161/832/1792) (from a search summary)
- **Android Quran-reading app for deaf students (SLBN Cerme Gresik, Indonesia):** one-group pre/post design with a Wilcoxon test. Mean hijaiyah-reading score rose from 67.16 to 80.5. — [UNESA Jurnal Pendidikan Khusus](https://ejournal.unesa.ac.id/index.php/jurnal-pendidikan-khusus/article/view/61854)
- Other Iqro/hijaiyah Android apps are development papers without clear outcome tests. — [UPI repository](https://repository.upi.edu/65624), [Unindra](https://jim.unindra.ac.id/index.php/JRKT/article/download/6483/847), [arXiv 1301.6319 (Iqro' on Pocket PC)](https://arxiv.org/pdf/1301.6319)
- Standard WER underestimates Quranic ASR failures. — [TajweedWER, ICML 2026](https://icml.cc/virtual/2026/80190)

### Inferences
- The thesis should frame its pilot as filling a documented gap: there are no controlled outcome studies of automated feedback for beginner Arabic letter reading, particularly for Russian-speaking learners.
- It should report task-appropriate accuracy (letter- or haraka-level precision/recall vs. teacher judgement), not only WER/CER.

### Gaps
- No Saudi or Malaysian RCTs on tajweed apps with effect sizes were found in this session.
- No studies were found on Russian-language Arabic-reading apps or bots.

## 6. Evaluation designs suitable for a master's pilot

### Takeaway
The field's typical study has about 47 participants, lasts about 7 weeks, is quasi-experimental and uses controlled-speech outcome measures. A master's pilot can match or exceed this standard. Do it with:
- a feedback vs. no-explanation A/B comparison, modelled on Neri et al. 2006;
- pre, post and **delayed** post-tests;
- teacher-rated outcomes;
- separate measurement of the bot's error-flag accuracy.

### Cited Findings
- **Typical CAPT designs:** mostly quasi-experimental (20 of 30 had control groups). Samples ranged from 5 to 132 (mean ≈ 47), and durations from 1 to 32 weeks (mean ≈ 7). Discrete measures (21 studies) were favoured over global ones (4). Human raters were preferred, and combining acoustic measures with human ratings is recommended. — [Amrate & Tsai 2025](https://www.cambridge.org/core/journals/recall/article/computerassisted-pronunciation-training-a-systematic-review/71E786F7DFC99727837909FDED7A2320)
- **Three-arm design precedent:** ASR + feedback vs. ASR without feedback vs. no tool. — [Neri et al. 2006](https://www.isca-archive.org/interspeech_2006/neri06_interspeech.html)
- **Expected effect sizes:** about 0.5–0.7 for CAPT and chatbot interventions. — [Ngo et al.](https://resolve.cambridge.org/core/journals/recall/article/effectiveness-of-automatic-speech-recognition-in-eslefl-pronunciation-a-metaanalysis/A915444CF252B61D14961D2FE733822D); chatbot meta-analyses above
- Controlled outcome measures inflate effects relative to free-speech measures. — [Lee, Jang & Plonsky 2015](https://experts.nau.edu/en/publications/the-effectiveness-of-second-language-pronunciation-instruction-a-/)
- Lyster & Saito tested effects across immediate vs. delayed outcome timing and found CF effects durable. — [SSLA](https://resolve.cambridge.org/core/journals/studies-in-second-language-acquisition/article/oral-feedback-in-classroom-sla/4999EE1C8379B2BF026B148EAF373CA1)

### Inferences
These are proposals derived from the cited evidence, not findings.

- **Power:** detecting d ≈ 0.6 between two independent groups at α = .05 with 80% power needs roughly 45 per group (standard power calculation). With a realistic pilot of 20–40 learners, use a **within-subject design**: each learner gets explanations on a random half of items or letters. Alternatively, report the study as a pilot with effect sizes and CIs rather than claiming significance.
- **Primary measures:**
  1. Accuracy on the immediate retry after feedback (explanation vs. right/wrong only).
  2. Pre/post/delayed (1–2 weeks) accuracy on a fixed set of letters and words, scored by a blinded teacher.
  3. Bot error-flag precision, recall, and FAR/FRR against teacher judgement, i.e., inter-rater agreement (Cohen's κ) between bot and teacher.
  4. Engagement: sessions per week, days active, dropout curve.
  5. A short perceived-accuracy and trust questionnaire, including how often the learner disagreed with the bot.
- **Teacher-workload metric:** share of attempts resolved automatically vs. escalated to a teacher. This directly tests the claim that the bot "partly replaces teachers."
- **Limitations to declare:** novelty effects (Fryer 2017; Wu & Yu 2024), the lack of an active human-teacher control, the small sample, and controlled-task measures overestimating real-reading gains.

### Gaps
- No published master's-scale pilot of an Arabic-reading bot with this design was found to serve as a direct template.
