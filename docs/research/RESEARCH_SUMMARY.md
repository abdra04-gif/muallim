# Muallim — speech recognition for beginner readers: summary

**Date:** 2026-11-17. This is the short version. Every figure comes from the full reports listed at the end; nothing here is new.

## In short

- **No ready-made model is proven for our learners.** Nothing published covers adults who start Arabic reading from zero, or Russian- and Kazakh-speaking learners.
- **We built and tested the most promising design.** For single letters with a vowel sign, a checker that picks from the 84 possible answers was right in **88 %** of recordings of students it had never heard. Free transcription by the same model was right in **47 %**.
- **The dataset format is ready as a proposal:** one record per attempt, original audio, three transcription layers, split by learner.
- **Consent must be explicit.** Telegram's rules require it. A one-screen draft is ready; pressing "Continue" means "I agree to publication".
- **The decisive next step is our own recordings**, labelled by a teacher. Every number below is measured on other people's recordings.

## 1. What we built and tested

### Step 1 — ready-made systems

Five systems listened to the same 840 public recordings: 28 letters × 3 vowel signs × 10 students. The students were Indonesian school pupils, recorded for an open dataset.

<!-- fig:step1 -->

### Step 2 — our own checkers

Step 1 confirmed what the literature says: free transcription fails on single letters. So we built the alternative the research points to. All four checkers use the same listening model, the best one from step 1. Only the way of deciding differs.

| Checker | How it decides |
|---|---|
| Free transcription | Writes down what it hears, then we read the first letter and vowel |
| Constrained choice | May only choose among the 28 letters and 3 vowels |
| Template comparison | Compares the recording with other students' average recording of each of the 84 items |
| Trained classifier | A small layer trained to pick one of the 84 items |

They were tested on all 8,904 recordings. Each recording was judged by a checker trained on **other students only**.

<!-- fig:step2 -->

The bot does not need to know *what* was read. It knows what should be read and asks one question: **was it read?** That is the test that matters.

<!-- fig:verify -->

<!-- fig:hard -->

**"Not sure" helps.** If the classifier answers only when it is confident, it answers three recordings out of four and is right in 95.8 % of them. On the rest the bot can ask the learner to say it again.

**What this does not show.** The labels say what each student was *asked* to read, not what a teacher heard. Substitutions were simulated from other students' recordings. The students are not ours. The classifier must be retrained and checked on our learners' recordings before the bot uses it.

**On the bot's own recordings.** The project's library recordings of letters could not serve as a check: each contains the spoken name of the vowel as well as the syllable, and some are known to be mislabelled. A script is ready to check any new voice messages as soon as they exist.

## 2. What exists in the world

We reviewed more than 40 models and services, 25 datasets, 16 Arabic products and about 20 systems for other languages, with over 130 sources. Every system found judges speech in one of four ways.

| Way | Examples | Sees a wrong vowel | Works on one letter | Accuracy on learners published |
|---|---|---|---|---|
| Recognise words, compare with the text | Tarteel, Duolingo, Google Read Along | No | No | No |
| Write down sounds, compare | Muaalem, IQRA systems, **Muallim today** | Yes | Weak | Staged errors only |
| Verify each expected sound | HAFSS, Quran Lab, children's letter-sound tools, Chinese state exam | Yes | By design | The only real figures |
| General voice model talks | QuranCast | Unknown | Unknown | None |

The third way is the only one with published numbers on real learners, and it is the one our step 2 tested.

<!-- fig:recall -->

### Muallim against the others

| | Tarteel | Quran Lab | ELSA and similar | Children's tools | **Muallim** |
|---|---|---|---|---|---|
| Judges sounds, not words | No | Yes | Yes | Some | Yes |
| Sees vowel-sign errors | No | Yes | — | No | Yes |
| Starts from single letters | No | No | No | Some | Yes |
| Adult beginners from zero | No | No | No | No | Yes |
| Says "not sure" | No | Left to the app | No | Some | No |
| Tested on learners | Not published | Private | Not published | Children | Not yet |
| Teacher checks the labels | No | Private | No | No | Yes |
| Open licence | No | No paid use | No | No | Yes |

**Where we are stronger:** we start where beginners start, we see vowel errors, teachers verify the labels, and we can publish an evaluation that others can repeat. No vendor does the last.

**Where we are weaker:** the bot's model never heard a learner; on single letters it is right in 39 % of recordings; it reports a long vowel in half of them; it always gives a verdict; nothing is tested on our learners yet; the present consent does not allow publication.

**Weak points seen in others:** accuracy claimed but never shown; word recognition sold as pronunciation checking; numbers measured on professional reciters; consent for collected voices not described.

## 3. Dataset format

| Element | Proposal |
|---|---|
| One record | One attempt: one voice message, one learner, one textbook item |
| Audio | The original Telegram voice message, unedited |
| Table | `metadata.jsonl`, one attempt per line, plus simple CSV tables |
| Three transcriptions, kept apart | What should be read · what the system heard · what a teacher heard |
| Split | By learner, never by recording; test learners fixed before any training |
| Publication | Hugging Face, with access after accepting usage terms |
| Not published | Name, Telegram account, exact dates, the question about prayer |

The bot already stores most of this. Seven gaps remain; the main ones are a consent record for publication and release codes for speakers.

## 4. Consent to public release

Telegram's developer terms forbid collecting data for datasets unless the user gives "individual, explicit, active and revocable consent". A notice line is not enough.

Draft screen (shown in Russian in the bot):

> **Your recordings will become part of an open dataset**
>
> If you press "Continue": your voice messages are saved and **published on the internet**. Any researcher in any country can download them. Published with them: what you read, the errors found, your age group, gender and first language. **Not published:** your name, Telegram account, phone number.
>
> Your voice is you: someone who knows you may recognise it. You can withdraw at any time; we remove your recordings from our storage and future versions, but copies already downloaded cannot be taken back. Only recordings of people aged 18 or over are published.
>
> **[ Continue — I agree to publication ]**   [ Practise without recording ]   [ More details ]

The second button makes agreement voluntary. Recordings made under the present consent ("only researchers") cannot be published unless the learner agrees again.

## 5. How to improve the bot

| Order | Change | Why |
|---|---|---|
| 1 | Put the consent screen into the bot | Nothing can be published without it |
| 2 | Record and label our first learners | Every number above is on other people's voices |
| 3 | For single letters, verify instead of transcribe | 88 % against 47 % in step 2 |
| 4 | Add "not sure" and "say it again" | 95.8 % right when answering three out of four; HAFSS did this in 2006 |
| 5 | Do not report a held vowel on a single letter as "too long" | The bot's model writes a long vowel in 411 of 840 recordings |
| 6 | Judge only what the lesson teaches | Fewer chances for a false alarm |
| 7 | Run a second checker silently on every attempt | Shows where the main one errs, at no cost to the learner |
| 8 | Send the confusable letters to teachers first | ظ, ث/س, the emphatic letters: the weakest spots for every system |

## 6. Decisions needed

| Decision | Recommendation |
|---|---|
| Consent model | "Continue" means publication; a second button allows practice without recording |
| Wording of the screen | Approve or correct the draft |
| Licence | Access after accepting terms for audio; CC BY 4.0 for labels |
| Learners under 18 | May use the bot; recordings not published |
| Ethics approval | Which university body reviews the study |
| Hosting country | Decides which data law applies |
| Quran Lab models | Their licence forbids paid features: research comparison only? |
| First recordings | Who records the first test set, with consent: the author, a teacher, volunteers |
