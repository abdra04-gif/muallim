# Muallim and the Field — Comparison, Weak Points and Improvements

**Project:** Muallim (Telegram reading trainer, textbook *al-Muallim ath-Thani*)
**Date:** 2026-11-17
**Status:** synthesis of the five phase reports and the two surveys. It adds no new sources. Every statement about another system comes from those reports; every statement about Muallim comes from the project's own files or from the Phase 3 test.

---

## 1. What was reviewed

| Area | Reviewed | Where |
|---|---|---|
| Speech models, services and methods | More than 40, in seven families | Phase 1 |
| Datasets | 25 | Phase 2 |
| Arabic products and research systems | 16 products, 7 sound-level pipelines, 10 design approaches | Survey of Arabic systems |
| Systems for other languages | About 20: adult apps, children's reading tutors, scoring services, tone-language tools, messenger bots | Survey of other languages |
| Systems run by us | 5 ready-made, on the same 840 recordings (4,200 model outputs) | Phase 3, step 1 |
| Checkers built by us | 4, tested on all 8,904 recordings, each clip judged by a checker that never heard its speaker | Phase 3, step 2 |
| Sources cited | More than 130 links and papers | All reports |

What this review is not: no commercial product was installed and tried; vendor pages are the vendors' own words; sources in Arabic and Chinese were not searched in those languages.

---

## 2. How the field divides

Every system found, in any language, uses one of four ways to judge speech.

| Way | Typical examples | Sees a wrong vowel | Says which sound | Works on one letter | Accuracy on learners |
|---|---|---|---|---|---|
| **Words:** recognise the words, compare with the text | Tarteel, Duolingo, Google Read Along, Amira, Amal | No | No | No | For reading gains only |
| **Sounds, free:** write down the sounds, compare with the expected ones | Muaalem, HisnLabs, IQRA systems, QVoice, **Muallim today** | Yes | Yes | Weak (35–50 %) | Benchmarks with staged errors |
| **Sounds, verified:** score each expected sound against its alternatives | HAFSS, Quran Lab reference method, Azure, ELSA, children's letter-sound tools, Putonghua test | Yes | Partly | By design | The only learner figures in the field |
| **Voice model:** a general model listens and talks | QuranCast | Unknown | In words, cannot be checked | Unknown | None |

Reading the table: Muallim is in the second row. The evidence of this research says that for the textbook's first stage the third row is the better fit, and that the fourth row has no evidence at all.

---

## 3. Muallim against the others

| Property | Tarteel (market leader) | Quran Lab (research) | ELSA and similar | Children's reading tools | **Muallim today** |
|---|---|---|---|---|---|
| Unit judged | Word | Sound | Sound | Word; sound in some | Sound |
| Vowel-sign errors | No | Yes | Not applicable | No | Yes |
| Starts from single letters | No | No | No | Some | **Yes** |
| Follows a graded textbook | No | No | Own course | Own stories | **Yes** |
| Adult beginners from zero | Not the target | Not the target | Not from zero | Children | **Yes** |
| Says "not sure" or asks to repeat | No | Left to the app | No | Some (teacher sets strictness) | **No** |
| Second, independent check | Unknown | Two signals combined | Unknown | Unknown | **No** |
| Trained or tested on learners | Users' recordings | Tested on learners (private sets) | Not published | Children's voices (vendors' statements) | **No** |
| Published evaluation | No | Self-reported | One unexplained figure | Reading gains only | **Not yet** |
| Teacher verifies the labels | No | Private | No | No | **Yes** |
| Stores what the system answered | Unknown | Unknown | Unknown | Unknown | **Yes** |
| Consent for the voice documented | No | Not applicable | Not found | Partly (on-device) | **Draft only** |
| Open model and licence | No | No paid use | No | No | **Yes (MIT)** |

---

## 4. Where Muallim is stronger

| Strength | Why it matters | Basis |
|---|---|---|
| It belongs to the family with the best benchmark evidence | Sound-level models without a language model won IQRA 2026 | Phase 1 |
| It sees vowel-sign errors | The market leader and all word-based products cannot | Arabic survey |
| It starts where real beginners start | No product reviewed serves the letters-and-vowels stage for adult non-Arabs | Both surveys |
| It keeps the full trace of each decision | Reference, raw model output, versions and thresholds are stored with every attempt; no dataset found stores this | Phase 4 |
| Teacher labelling is built in | Several annotators, history kept, agreement computed | Phase 4 |
| Its recogniser can be replaced | Several models can be compared on the same recordings | Phase 5 |
| It can publish what vendors do not | An evaluation against teachers that others can repeat | Both surveys |

## 5. Where Muallim is weaker

| Weak point | Evidence | Consequence |
|---|---|---|
| The model never heard a learner | Trained on 22 professional male reciters | Unknown behaviour on beginners, women, children |
| On single letters it is right in 39.4 % of clips | Phase 3 | The first stage of the book rests on the model's weakest material |
| It writes a long vowel when a learner holds a short one | 411 of 840 clips | Risk of a false "too long" on the very first lessons |
| It confuses the pairs a beginner confuses | د→ت, ع→ء, ث→س, ض→د | The verdict is least reliable where it is most needed |
| It always gives a verdict | No "not sure", no "say it again" | False alarms discourage beginners; HAFSS avoided this in 2006 |
| One signal only | No second check | Nothing catches the model's own mistakes |
| No evaluation on its own learners | No labelled recordings yet | No claim about accuracy can be made |
| The consent does not cover publication | Present text: "only researchers" | No recording made so far can enter a public dataset |
| It runs on a server, not on the phone | Telegram | Privacy must rest on consent; products on the device avoid the question |
| No symbol for a non-Arabic sound | Phase 4 | A Russian substitute is forced into an Arabic label |

## 6. Weak points seen in the others

| Weak point | Who | Why it matters to us |
|---|---|---|
| Accuracy claimed, never shown | Almost every vendor, in every language | A published, repeatable evaluation is a real contribution |
| Word recognition presented as pronunciation checking | Tarteel, Duolingo, Amal | Do not adopt it for vowels and letters |
| Results reported on professional reciters | Most Arabic models | Figures under 2 % say nothing about learners |
| Errors in test sets are staged or synthetic | IQRA benchmarks | Real learner errors are missing from the field's data |
| One master voice as the yardstick | TajweedMate, Maqam | Rewards imitation of a voice |
| No decision policy | Most modern open models | The model outputs sounds; nobody decides what to tell the learner |
| Beginners named but not designed for | All except HAFSS | The niche is open |
| Consent for collected voices not described | Every dataset in Phase 2, every product | Documenting ours is part of the contribution |

---

## 7. How to improve the bot

Ordered by what unblocks the rest. "Decides" names who must approve under the project's rules.

| # | Improvement | Based on | Effect | Decides |
|---|---|---|---|---|
| 1 | Put the consent screen for public release into the bot | Telegram terms, Phase 5 | Without it no recording can be published | Author |
| 2 | On single-letter items, do not report a held vowel as "too long" | Phase 3: 411 of 840 clips | Removes a likely false alarm in the first lessons | Author (method) |
| 3 | Add the answers "not sure" and "say it again" | HAFSS; Quran Lab's 32–46 % | Fewer wrong verdicts; protects motivation | Author (method) |
| 4 | Judge only what the lesson teaches | HAFSS: vowel errors only for beginners | Fewer chances for a false alarm | Author (method) |
| 5 | For Stage I, verify instead of transcribe: a classifier over the 84 letter–vowel answers | Phase 3 step 2 (built and tested); Black et al.; Putonghua test | Tested on unseen speakers: 88.0 % right against 47.2 % for free transcription; accepts 90.5 % of correct readings instead of 47.2 % | Author (new component) |
| 6 | Run a second recogniser silently on every attempt | Phase 5; `fastconformer-quran` (two of three signals) | Shows where the main model errs, at no cost to the learner | Author |
| 7 | Send the confusable pairs to teachers first | Phase 3 confusions | Labels arrive where the model is weakest | Agent, with the teacher |
| 8 | Label the test recordings without showing the model's answer; freeze the test learners | Phase 4 | Makes the evaluation credible | Author |
| 9 | Publish agreement between teachers beside agreement with the system | Black et al. (95 % between humans) | Shows the ceiling any system can reach | Agent |
| 10 | Build a table of the substitutions our learners actually make | HAFSS rule base; our labels | Lets the verifier test "target versus its usual substitute" | Author with the teacher |
| 11 | Compare with several reference recordings as one more signal | Phase 1; criticism of single-voice comparison | A check that needs no Arabic model | Author |
| 12 | Let the teacher set strictness per group | Microsoft, Rosetta Stone, Quran Lab presets | Adapts to the learner's level | Author |
| 13 | Later: judge lengths relative to the reader's own pace | HAFSS, HisnLabs | Needed when the book reaches prolongation | Author (method) |

Not recommended: word recognition as the judge; a general voice model as the teacher; any accuracy statement before our own labelled test exists.

---

## 8. What Muallim can claim, and what it cannot

| Can be claimed now | Cannot be claimed yet |
|---|---|
| The design follows the best-supported family of methods | That the bot is accurate on beginners |
| No published system serves this learner group and this material | That the chosen model is the best one |
| The dataset would be the first of its kind | That the dataset exists |
| A first test shows where every available model fails on single letters | That these figures describe our learners |
| A checker that verifies the expected letter beat free transcription by 41 points on speakers it never heard | That it will do so on Russian-speaking adults; it must be retrained on our recordings |
