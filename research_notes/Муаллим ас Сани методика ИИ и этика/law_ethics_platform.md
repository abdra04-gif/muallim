# Legal, research-ethics and platform requirements for a Telegram bot that collects learners' voice and learning data (Russia + Kazakhstan, as of October 2026)

> NOT LEGAL ADVICE. Compiled 2026-10-17 from web sources (some secondary, e.g. law-firm and accounting blogs). Statutory texts should be checked on consultant.ru / pravo.gov.ru / adilet.zan.kz before relying on them. Interpretations marked "uncertain" are exactly that. Where a point comes from the researcher's background knowledge and not from a source fetched in this session, it is in "Inferences" or "Gaps" and labeled.

## 1. Russia, 152-ФЗ: is voice personal or biometric data? Does 572-ФЗ (ЕБС) apply?

### Takeaway
A voice recording linked to a Telegram ID is personal data. It becomes *biometric* personal data (ст. 11 152-ФЗ) when it is used to establish identity. Roskomnadzor's position is that biometric status depends on purpose. A bot that uses voice only to assess recitation (tajwid/pronunciation) and to train an ASR/pronunciation model, never to identify the speaker, most likely does NOT process biometrics, but this point is legally uncertain. 572-ФЗ restricts *identification/authentication* with face and voice to the ЕБС and accredited organizations, and should not be triggered if voice is never used for identification. You should state that in writing.

### Cited Findings
- RKN clarification (letter № 08АП-6782, as retold by secondary sources): voice is listed among physiological data (with fingerprints, iris, DNA) that may be biometric. Data counts as biometric only if (a) it describes physiological/biological features, (b) it allows identity to be established, AND (c) the operator uses it to establish identity. — [pravo.ppt.ru (letter 08АП-6782)](https://pravo.ppt.ru/pismo/roskomnadzor/n-08ap-6782-253935); [securitylab.ru commentary](https://www.securitylab.ru/blog/personal/Business_without_danger/32598.php)
- Commentators note that an RKN clarification is not binding in court. Its role is to align territorial RKN offices. — [securitylab.ru](https://www.securitylab.ru/blog/personal/Business_without_danger/32598.php)
- Some practitioners take a broader view: any recording in which a person is recognisable by voice is biometrics. This is a lawyer's opinion, not the regulator's. — [harant.ru Q&A](https://harant.ru/questions/q-160801/)
- 572-ФЗ of 29.12.2022 (ЕБС law) covers two biometric modalities, face image and voice recording. Minцифры order of 19.06.2025 № 553 (in force 28.09.2025) sets voice-sample parameters and microphone specifications for ЕБС identification/authentication. — [ppt.ru on order 553](https://ppt.ru/amp/obzory/vstupaet-v-silu/prikaz-mintsifry-rossii-19-06-2025-553); [vbr.ru](https://www.vbr.ru/sovety/help/people-and-economic/zapret-na-sbor-biometrii/)
- According to a law-firm marketing page: since 1 June 2023, commercial organizations may perform biometric identification only via the ЕБС or with accreditation, and storing raw face/voice samples in their own systems is banned (the page cites ст. 15 572-ФЗ; not verified against the statute). The same page gives a video-analytics example that counts visitors without identifying anyone and argues it falls outside 572-ФЗ, i.e. purpose matters. It does not address ML training data. — [vitvet.com](https://vitvet.com/about/news/biometricheskie-dannye-biznes-shtraf-ebs-2026/)
- Secondary sources disagree on whether *every* biometric operator must connect to the ЕБС or whether accredited alternatives exist. — [securitylab.ru (Rubikon)](https://www.securitylab.ru/blog/company/Rubikon/353601.php); [habr](https://habr.com/ru/articles/920862)
- 572-ФЗ ст. 13 (per secondary source): refusing biometric identification cannot be a ground for refusing a service. — [vbr.ru](https://www.vbr.ru/sovety/help/people-and-economic/zapret-na-sbor-biometrii/)

### Inferences
- For the bot, the safest legal framing is: "voice recordings are processed solely to evaluate pronunciation and to train/evaluate speech models; they are not used and will not be used to identify or authenticate any person; no voiceprints/speaker embeddings are created." With that purpose limitation, the recording is ordinary (non-biometric) personal data under RKN's three-condition test. However, do not train speaker-ID models and avoid storing speaker embeddings.
- Uncertainty: a regulator or court could take the broader view (any recognisable voice = biometrics). The conservative mitigation is to obtain consent that *also* meets ст. 11 standards (a separate, explicit consent for the voice recordings). That costs little and covers both readings.
- Voice consent should be optional. The bot should still work for users who decline recording-for-research, in the spirit of 572-ФЗ ст. 13 and of voluntary research participation.

### Gaps
- I did not retrieve the primary text of RKN letter 08АП-6782 or any RKN statement specific to ML training on voice. No RKN or court position on "voice data used for training ASR models" was found.
- The exact 572-ФЗ article that bans private storage of voice samples was not verified against the official text (only a marketing page).

## 2. Russia, 152-ФЗ: operator status, consent, notification, localization, cross-border transfer, research exception, minors, fines

### Takeaway
A student running a public bot is an "оператор" (the definition explicitly includes individuals). The "personal/family needs" exemption does not apply to a public research bot (background knowledge). Since 01.09.2022 almost every operator, including individuals using automated processing, must notify RKN before processing. Only three narrow exemptions remain. Since 01.09.2025 consent must be a separate document, not buried in a policy or ToS. Data of Russian citizens must first be recorded and stored in Russian databases (ст. 18 ч. 5). Any foreign transfer requires a prior RKN notification (since 01.03.2023). Fines rose sharply from 30.05.2025.

### Cited Findings
- **Notification of RKN (ст. 22):** ч. 2 items 1–6 (old exemptions) were repealed effective 01.09.2022 by 266-ФЗ of 14.07.2022. The remaining exemptions are: п. 7 state systems for state security, п. 8 processing *exclusively without automation tools*, п. 9 transport security. A bot is automated processing, so no exemption applies. The notification must include the operator's name **or the individual's full name** and address, purposes, security measures (ст. 18.1, 19, including crypto tools), the responsible person, start date, end condition, whether cross-border transfer occurs, **location of the database with Russian citizens' data**, and, per ч. 3.1, data categories, subject categories, legal basis, actions and methods for each purpose. — [consultant.ru, ст. 22 152-ФЗ](https://www.consultant.ru/document/cons_doc_LAW_61801/d996966e22e1320c9de1ab82d9f6be12c3d9d765/)
- **Cross-border transfer:** since 01.03.2023 a separate notification to RKN is required before starting cross-border transfer. "Cross-border transfer" = transfer to a foreign state authority, foreign individual or foreign legal entity (п. 11 ст. 3 152-ФЗ). RKN letter 06.12.2022 № 08ВМ-107716 addresses whether each transfer needs notifying. — [Kontur](https://kontur.ru/articles/1478); [1С:ИТС](https://its.1c.ru/db/content/newsclar/src/482555.htm); [ALRUD briefing](https://alrud.ru/upload/Информационные%20письма/АЛРУД_Информационное_письмо_Трансграничная_передача_персональных_данных.pdf)
- **Separate consent document from 01.09.2025:** Federal Law 24.06.2025 № 156-ФЗ amended 152-ФЗ so that consent must be drawn up separately from other documents (contract, offer, policy). A checkbox is acceptable only next to text that expressly says it is consent to personal-data processing. Mandatory content is in ст. 9 ч. 4: specific purposes, list of data, actions, term, third parties, and the withdrawal procedure. Electronic form is allowed. — [ppt.ru](https://ppt.ru/news/personal-data/oformlyat-soglasie-na-obrabotku-personalnykh-dannykh-nuzhno-budet-po-novomu); [harant.ru](https://harant.ru/blog/internet-pravo/chto-izmenilos-s-1-sentyabrya-2025-goda-v-oblasti-personalnyh-dannyh-dlya-onlajn-biznesa/); [elama.ru](https://elama.ru/blog/soglasie-na-obrabotku-personalnyh-dannyh-obrazets/amp/)
- Commentators say re-papering consents obtained before 01.09.2025 is not required. That is an opinion, not an official position. — [buhexpert8.ru](https://buhexpert8.ru/1s-buhgalteriya/kadry-i-zarabotnaya-plata/kadrovye-dokumenty/s-1-sentyabrya-2025-oformlyajte-soglasie-na-obrabotku-persdannyh-otdelnym-dokumentom.html)
- **Biometric consent:** ст. 11 152-ФЗ requires written consent for biometric data (per secondary source). If third parties process the data, a processing instruction (поручение) is needed and the third party must be named in the consent. — [securitylab.ru (Rubikon)](https://www.securitylab.ru/blog/company/Rubikon/353601.php)
- **Fines (420-ФЗ of 30.11.2024, in force 30.05.2025, ст. 13.11 КоАП):** leak of 1,000–10,000 subjects: 3–5 mln RUB for companies/entrepreneurs, 200–400 k RUB for officials. Leak of special-category data: 10–15 mln RUB (companies). Leak of biometric data: 15–20 mln RUB (legal entities, ч. 17). Repeat leaks: turnover fine of 1–3% of revenue, min. 25 mln and max. 500 mln RUB (ч. 18). Refusing service to people who decline biometrics: 200–500 k RUB (ст. 14.8 ч. 8). — [v2b.ru](https://www.v2b.ru/articles/oborotnye-shtrafy-za-utechku-personalnyh-dannyh/); [vitvet.com](https://vitvet.com/about/news/biometricheskie-dannye-biznes-shtraf-ebs-2026/); [buh.ru](https://buh.ru/news/gosduma-odobrila-zakon-ob-oborotnykh-shtrafakh-za-utechku-personalnykh-dannykh.html)
- **Criminal liability:** ст. 272.1 УК РФ (illegal use/transfer of computer information containing personal data), in force since 11.12.2024 (421-ФЗ). — [vitvet.com](https://vitvet.com/about/news/biometricheskie-dannye-biznes-shtraf-ebs-2026/); [habr](https://habr.com/ru/articles/1000854)
- The moratorium on unscheduled RKN inspections was reportedly lifted in 2025. — [vitvet.com](https://vitvet.com/about/news/biometricheskie-dannye-biznes-shtraf-ebs-2026/) (secondary, unverified)

### Inferences
- **Operator status:** ст. 3 п. 2 152-ФЗ defines an оператор as a "государственный орган, муниципальный орган, юридическое или **физическое лицо**…". The ст. 1 ч. 2 п. 1 carve-out covers only processing "исключительно для личных и семейных нужд", which does not fit a public bot collecting research data (background knowledge, consistent with the ст. 22 ч. 3 reference to the "individual's full name"). Alternatively, if the university formally hosts the project, the university can be the operator and the student a person acting on its instruction. This is the preferred structure if the university agrees, because it moves the obligations to an institution that already has an RKN registration and a DPO.
- **Research exception (ст. 6 ч. 1 п. 9, background knowledge, verify text):** processing without consent is allowed for statistical or other research purposes *on condition of mandatory depersonalisation (обезличивание)*. Raw voice is hard to depersonalise because the voice itself is identifying. So this exception will not cover voice collection, and consent remains the legal basis for voice. It can support analysis of already-pseudonymised learning results. Pseudonymisation (replacing the Telegram ID with a key) is not full обезличивание if the key is kept. Since 01.09.2024 (233-ФЗ, background knowledge) RKN rules on depersonalisation and the "dataset" regime for the state data platform exist. Uncertain applicability; verify.
- **Localization (ст. 18 ч. 5, background knowledge):** when collecting personal data of Russian citizens, including via the Internet, the operator must ensure recording, systematisation, accumulation, storage, update and retrieval *using databases located in Russia*. A copy abroad is possible only after the Russian "primary" database exists and with a cross-border notification. Since 2025 (background knowledge) КоАП ст. 13.11 ч. 8–9 fines for localization breaches were increased for legal entities (up to 6–18 mln RUB). The exact numbers were not verified in this session; see Gaps.
- **Telegram itself** stores messages and voice notes on its own (foreign) servers. The localization duty concerns the *operator's* database, i.e. the bot backend. Best practice is that the bot downloads the voice file via the Bot API and stores it on a Russian server first. Whether RKN would treat the Telegram transit as cross-border transfer by the operator is uncertain. Users send the data to Telegram themselves.
- **Minors (background knowledge):** 152-ФЗ has no special age rule. Consent for a person lacking full legal capacity is given by the legal representative (ст. 9 ч. 6). Civil Code ст. 26/28 (under 14: parents act; 14–18: minors act with parental consent) is commonly applied. Conservative practice is parental consent for under-18s for research and voice. A cleaner design is to exclude under-18s from the research/voice-donation part (age self-declaration plus a separate path).
- An individual operator faces the citizen/official-level fines in КоАП, which are lower than corporate ones. The criminal ст. 272.1 УК applies to anyone.

### Gaps
- Exact current КоАП ст. 13.11 amounts for *citizens* for failure to notify, processing without consent and localization breaches were not retrieved.
- The text of ст. 6 ч. 1 п. 9 and ст. 18 ч. 5 was not fetched in this session (paraphrased from background knowledge).
- No source was found on whether a student acting under a university's research project should notify RKN personally.

## 3. Kazakhstan: Law № 94-V «О персональных данных и их защите» (as amended to 2026)

### Takeaway
Kazakhstan requires storage in a database or digital object located in Kazakhstan (ст. 12 п. 2), with no exceptions by data category or volume. Consent (ст. 8) is the practical basis; legitimate interest is not available. Cross-border transfer to non-adequate countries needs consent (ст. 16). Since 18.01.2026 automated processing requires consent plus a right to object (ст. 19-1). Prior notification to the regulator applies only to large operators (ст. 10-1, since 25.08.2026). Several amendments took effect in 2026.

### Cited Findings
- 94-V (21.05.2013) remains in force. Key amendments:
  - 96-VII (in force 02.03.2022): rewrote ст. 8 on consent and added consent services, ст. 8-1 (state) and 8-2 (non-state).
  - 155-VIII (in force 13.03.2025): raised КоАП ст. 79 fines.
  - 231-VIII (17.11.2025, in force 18.01.2026): added ст. 19-1 and consent-retention / 15-working-day deletion rules in ст. 8.
  - 256-VIII (in force 12.07.2026): revised definitions and **removed the statutory definition of biometric data**.
  - 326-VIII (24.06.2026, in force 25.08.2026): added ст. 10-1, 23-2 and 25-1 and amended ст. 6, 7, 8 and 12.
  - 350-VIII (from 14.09.2026) and 311-VIII (from 01.01.2027): content not established.
  - Digital Code № 255-VIII in force 12.07.2026.
  — [UPPERSETUP (Aug 2026)](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no); [prg.kz](https://prg.kz/m/amp/document/31396226/2/120000)
- **Localization, ст. 12 п. 2:** storage "в базе и (или) цифровом объекте, которые находятся на территории Республики Казахстан", with no exceptions. Rules 179/NQ (amended by 338/NQ, 12.07.2026) add that restricted-access data be stored in a server room or data center in Kazakhstan. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)
- **Cross-border, ст. 16:** transfer to adequate-protection countries is free. Otherwise it needs consent, a treaty, a law, or protection of constitutional rights. There is no official adequacy list, so consent is the reliable basis. Localization still applies. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)
- **Consent, ст. 8:** on paper, via the state access-control service (ст. 8-1) or a non-state service (ст. 8-2). Consent lasts only as long as needed for the purpose (п. 5). Processing must stop within 15 working days of withdrawal (п. 7). The ст. 9 list of non-consent bases is closed, and legitimate interest is not a basis. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)
- **Automated processing, ст. 19-1 (from 18.01.2026):** "Запрещается автоматизированная обработка персональных данных" except with consent or by law. The operator must explain the processing and its consequences and allow objection. An objection is reviewed within 3 working days. Digital Code ст. 43 adds the rights to an explanation and to human review. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)
- **Biometrics:** the definition was removed from 94-V art. 1 (from 12.07.2026). Digital Code ст. 48 treats biometric data used for digital authentication as personal data. Mandatory biometric processing only where a law provides. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)
- **Registration, ст. 10-1 (from 25.08.2026):** only "large" operators (ст. 25-1) must notify before processing. Small and medium operators are exempt. Implementing rules were not yet published as of Aug 2026. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)
- **Fines, КоАП РК ст. 79** (MRP 2026 = 4,325 tenge): up to 200 MRP for unlawful processing (large business), up to 2,000 MRP where a protection failure caused loss. Criminal: УК ст. 147. — [UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no)

### Inferences
- A foreign individual (a Russia-based student) operating a bot used by Kazakh residents is likely within 94-V's scope as an operator collecting Kazakh residents' data. Localization in Kazakhstan therefore formally applies. Enforcement against a foreign individual is practically unlikely, but the formal risk remains. There are two compliant options: (a) a Kazakh server (e.g., PS.kz, Hoster.kz) for KZ users' data, or (b) the Russian server plus explicit ст. 16 consent to transfer. Option (b) does not satisfy ст. 12 localization, which applies even when transfer is lawful.
- Voice used for ASR/pronunciation scoring counts as "automated processing" under ст. 19-1. The consent text must explicitly cover automated processing and offer an objection channel with a 3-working-day response.
- Minors: the source does not cover minors. Kazakh civil majority is 18 (background knowledge), so parental consent via the legal representative is the conservative rule.

### Gaps
- Whether 94-V applies extraterritorially to a foreign operator without presence in Kazakhstan: no source found.
- Kazakh-specific minors rule in 94-V: not found.
- Content of 350-VIII and 311-VIII: not found.
- I did not consult adilet.zan.kz directly; findings rest on one detailed secondary analysis (UPPERSETUP, Aug 2026).

## 4. Research ethics in Russian universities (master's research with human participants)

### Takeaway
No federal statute requires ethics-committee approval for non-medical social or educational research in Russia. Leading universities (e.g., HSE) run ethics committees that review student projects, including at department level. Approval is a university-policy requirement where it exists and is increasingly expected by journals. Check your own university's rules. In practice: information sheet, informed consent, data management plan, anonymisation/pseudonymisation, a withdrawal right and extra protection for minors.

### Cited Findings
- HSE has a university-wide Commission for ethical review of empirical research ([hse.ru/org/hse/irb](https://www.hse.ru/org/hse/irb)), with application templates for staff **and students**. It issues formal opinions on compliance with the ethical norms of modern social sciences. — [HSE IRB page](https://www.hse.ru/org/hse/irb)
- HSE's Psychology Department commission reviews empirical projects of staff, **students and postgraduates** for compliance with social-science ethics and Russian law. — [HSE psychology commission regulation](https://social.hse.ru/data/2020/03/02/1563750320/%D0%9F%D0%BE%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5%20%D0%BE%D0%B1%20%D1%8D%D1%82%D0%B8%D1%87%D0%B5%D1%81%D0%BA%D0%BE%D0%B9%20%D0%BA%D0%BE%D0%BC%D0%B8%D1%81%D1%81%D0%B8%D0%B8%20%D0%B4%D0%B5%D0%BF%D0%B0%D1%80%D1%82%D0%B0%D0%BC%D0%B5%D0%BD%D1%82%D0%B0%20%D0%BF%D1%81%D0%B8%D1%85%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D0%B8.pdf)
- An HSE commission protocol of 24.10.2024 shows outcomes such as approval without remarks or approval subject to minor edits, including for a project on effects of online learning. — [HSE protocol 24.10.2024](https://hse.ru/data/2024/11/13/1935411710/%D0%9F%D1%80%D0%BE%D1%82%D0%BE%D0%BA%D0%BE%D0%BB_24.10.2024_%D0%BE%D0%BF%D1%80%D0%BE%D1%81%D1%8B%20%D0%B8%20%D0%BF%D0%BE%D0%B2%D0%B5%D0%B4%D0%B5%D0%BD%D1%87%D0%B5%D1%81%D0%BA%D0%B8%D0%B5%20%D1%8D%D0%BA%D1%81%D0%BF%D0%B5%D1%80%D0%B8%D0%BC%D0%B5%D0%BD%D1%82%D0%BE%D0%B2_%D0%BD._140.docx)
- Nazarbayev University (Kazakhstan) has an Institutional Research Ethics Committee regulation, relevant if Kazakh partners or participants are involved. — [NU regulation (PDF)](https://regulations.nu.edu.kz/bitstream/123456789/602/10/)

### Inferences
- Mandatory approval for non-clinical research is not federally required in Russia (background knowledge; ethics review is legally mandatory for clinical/biomedical trials). It is advisable because voice is identifying, the topic is religious (a sensitive characteristic: "религиозные убеждения" are special-category data under ст. 10 152-ФЗ), and minors may participate.
- **Special category risk:** a Quran-learning bot's user list may reveal religious beliefs. ст. 10 152-ФЗ allows processing of special categories with *written* consent (background knowledge). Treat the dataset as sensitive. This argues for an ethics committee opinion even if not strictly required.
- Ask the supervisor whether the dissertation council or university (and journals where results will be published) require a committee opinion. If the student's university has no committee, a supervisor-signed ethics statement plus a DMP is the minimum.

### Gaps
- Specific rules for MSU, KFU or ITMO ethics committees were not retrieved.
- No found requirement from ВАК or the Russian Ministry of Science mandating ethics approval for master's theses.

## 5. Religious content risks in Russia

### Takeaway
Since 2015 the Bible, Quran, Tanakh and Kanjur, their contents and quotations, cannot be declared extremist materials. That protection covers the sacred text, not translations of meaning (тафсир) and commentaries. Several Russian translations and tafsirs (e.g., Kuliev's 2002 edition in 2013; al-Sa'di tafsir in Kuliev's translation in 2020) have been ruled extremist by courts. A bot that uses only the Arabic mushaf text and its own neutral pedagogical content is low risk. Avoid embedding or linking third-party Russian translations/tafsirs without checking the Minjust federal list.

### Cited Findings
- Amendment to the law «О противодействии экстремистской деятельности» bans declaring the Bible, Quran, Tanakh and Kanjur, their contents and quotations extremist. The bill was introduced by Putin after the Yuzhno-Sakhalinsk court ruling (case 2-4657/2014) that declared a dua book quoting Al-Fatiha extremist. legalacts.ru lists it as Federal Law of 23.11.2015 № 314-ФЗ; the number was not confirmed against the text. — [pravo.ru](https://pravo.ru/news/view/123242/); [pravo.ru (Putin bill)](https://pravo.ru/news/view/122921/); [legalacts.ru](https://legalacts.ru/doc/federalnyi-zakon-ot-23112015-n-314-fz-o/); [Kommersant](https://www.kommersant.ru/Doc/2851462)
- Experts noted the vagueness of "extremism" remains, so the amendment does not resolve risks for other religious literature. — [Kommersant FM](https://www.kommersant.ru/Doc/2832323)
- 17.09.2013: the Oktyabrsky District Court of Novorossiysk declared extremist the first (2002, King Fahd Complex) edition of Elmir Kuliev's "Смысловой перевод священного Корана". No confirmation of reversal was found. — [Kommersant](https://www.kommersant.ru/doc/2309752); [RAPSI](https://rapsinews.ru/judicial_news/20130924/268923083.html)
- 2020: the Krasnoglinsky District Court of Samara declared extremist the first volume of al-Sa'di's tafsir (in Russian translation), based on an FSB expert opinion. — [Mediazona](https://zona.media/news/2020/08/19/samara-tafsir-al-sadi); [Novaya Gazeta](https://novayagazeta.ru/amp/articles/2021/02/16/89250-prishli-za-koranom-pridut-i-za-volterom)

### Inferences
- Use Arabic Uthmani text from a well-known source (e.g., Tanzil/King Fahd mushaf in Arabic). If a Russian meaning translation is needed, use one not on the federal list (Krachkovsky's academic translation is commonly considered safe; verify), and do not host tafsir collections.
- Moderate any user-generated content, and do not let the bot become a channel for distributing materials from banned organisations. Displaying symbols or materials of organisations designated extremist/terrorist (ст. 20.3, 20.29 КоАП) is the main risk vector.
- Note for Kazakhstan: Kazakhstan has its own regime of religious-literature expertise (Law on Religious Activity and Religious Associations, 2011). Not researched here (gap).

### Gaps
- The Minjust federal list was not checked live for specific translations as of Oct 2026.
- Kazakhstan's religious-literature rules were not researched.

## 6. Platform risk: Telegram in Russia and Kazakhstan (2025–2026), MAX; Telegram's bot terms

### Takeaway
Telegram is not formally banned in Russia as of mid-October 2026, but it is heavily degraded. Calls have been restricted since August 2025, and deliberate throttling was confirmed by RKN on 10.02.2026, hitting **media, including voice notes**, more than text. Outages were still widely reported on 16.10.2026. This directly threatens a voice-based bot for Russian users. The state messenger MAX is being pushed but has serious trust/surveillance concerns. Separately, **Telegram's Bot Developer Terms ban collecting data to build datasets/ML/AI products**, except for data users submit directly and voluntarily with explicit, active, revocable consent. The consent design therefore matters contractually too.

### Cited Findings
- Aug 2025: RKN restricted voice calls on Telegram and WhatsApp (officially anti-fraud). By Oct 2025 both were fully restricted in some southern regions. — [Mediazona EN](https://en.zona.media/article/2026/04/07/russian_internet_censorship_2026); [GlobalSecurity/RFE/RL](https://www.globalsecurity.org/wmd/library/news/russia/2025/08/russia-250814-rferl03.htm)
- 10.02.2026: RKN confirmed deliberate slowdown of Telegram (~90 mln Russian users), citing fraud and inadequate personal-data protection. Disruptions are largely confined to media such as **voice notes**, videos and images. Text is mostly unaffected. — [The Moscow Times](https://www.themoscowtimes.com/2026/02/10/roskomnadzor-tightens-restrictions-on-telegram-as-users-report-disruptions-a91907); [Meduza](https://meduza.io/en/feature/2026/02/10/telegram-is-one-of-the-last-messaging-apps-in-russia-that-the-state-doesn-t-control-did-the-kremlin-just-block-it-for-good); [The Record](https://therecord.media/russia-throttles-telegram-pushes-its-own-messaging-app)
- Feb–Apr 2026: RBC reported a decision on a full block by 1 April. RKN said it had nothing to add. Experts say a full block is technically impossible without disconnecting from the global internet. A criminal case concerning Durov ("aiding terrorism") was reported in Feb 2026. — [Kommersant](https://www.kommersant.ru/doc/8463664); [Kommersant (experts)](https://www.kommersant.ru/doc/8552632); [RIA](https://ria.ru/20260226/roskomnadzor-2076971768.html); [Mediazona EN](https://en.zona.media/article/2026/04/07/russian_internet_censorship_2026)
- 16.10.2026: ongoing failures (500+ Downdetector reports per day), with complaints about sending messages, calls and media. No official confirmation of a full block. — [hi-tech.mail.ru](https://hi-tech.mail.ru/news/145611-chto-segodnya-s-telegram/); [metaratings](https://cybersport.metaratings.ru/articles/chto-proishodit-s-telegram-segodnya/); [Bitrix24 journal](https://www.bitrix24.ru/journal/blokirovka-telegram/)
- Telegram is not on the whitelist of services available during mobile internet shutdowns. In 2026 the state escalated against VPNs (Mar 2026 deadline for companies to block VPN users; charges for >15 GB of foreign mobile traffic). — [Mediazona EN](https://en.zona.media/article/2026/04/07/russian_internet_censorship_2026)
- A lawyer's opinion: using Telegram via VPN is not prohibited and not fined for users. — [legalacademy.ru](https://legalacademy.ru/sphere/post/telegram-v-rossii-kak-zakonno-prodolzhat-rabotu-v-usloviyah-novyh-ogranichenii-2026-goda)
- MAX (VK-developed, state-backed): embedded via a June 2025 decree, and from Dec 2025 required for apartment-building management communications. Reports of pressure on students to install it. A Habr analysis (Mar 2026) found the Android app checking Telegram domains and VPN status, which MAX denies. An advocacy site claims MAX shares data with the FSB and has been preinstalled on phones since Sept 2025 (treat with caution). — [Mediazona EN](https://en.zona.media/article/2026/04/07/russian_internet_censorship_2026); [stateofsurveillance.org](https://stateofsurveillance.org/news/russia-telegram-throttle-max-surveillance-app-2026/)
- From 01.04.2026 the FSB may reportedly request data from organisations' databases, including biometrics (secondary, unverified). — [vitvet.com](https://vitvet.com/about/news/biometricheskie-dannye-biznes-shtraf-ebs-2026/)
- **Telegram Bot Developer Terms** ([telegram.org/tos/bot-developers](https://telegram.org/tos/bot-developers)):
  - §4: the bot must be bound by an easily accessible privacy policy. If Telegram's Standard Policy does not cover your practices, you must provide your own policy (set in @BotFather).
  - §4.1: additional data may be requested from users by agreement. Deceiving users to get around data limits is prohibited.
  - §4.2: delete user data without undue delay on user request, when no longer needed, or when the bot stops, unless the user agreed to longer retention.
  - §4.3: no collection "beyond what is essential". Collection aimed at building **large datasets, machine learning models and AI products is always prohibited** (e.g., scraping groups/channels). BUT data users "submit directly and voluntarily" may be used if the intended use is clearly disclosed and the user gives "individual, explicit, active and revocable consent".
  - §4.4: encrypt user data at rest, with keys stored separately, and notify breaches as required by law.
  - §9.1: comply with applicable privacy laws.
  - No last-updated date is shown.
  — [Telegram Bot Developer Terms](https://telegram.org/tos/bot-developers)

### Inferences
- The voice-for-ML design is compatible with Telegram's terms *only* via the §4.3 carve-out. The consent button must be separate, unticked by default, and active (a user tap), must state ML training explicitly, and must be revocable (/withdraw command). Use only voice the user records for the bot. Never mine group chats.
- For Russian users, voice-note upload is the most throttled feature. Expect data loss and drop-outs that bias the research sample. Note this as a study limitation. Mitigations: a web app (Telegram Mini App or standalone PWA hosted in Russia) with in-browser recording that uploads directly to your server, bypassing Telegram media transport; and a backup channel (website + email, optionally a VK/MAX bot) announced in advance.
- MAX as a research channel: ethically questionable for voice research given reported data-sharing concerns. If used, it must be disclosed in the information sheet.
- Kazakhstan: no 2025–2026 Telegram restrictions were found in this session (gap). Telegram is widely used there.

### Gaps
- Telegram's status in Kazakhstan in 2026 was not researched.
- No authoritative (RKN/official) status of Telegram as of October 2026 beyond media reports of disruptions.

## 7. Practical compliance checklist (synthesis: inferences based on the above; not legal advice)

### Takeaway
Best structure: make the university the operator (or co-operator) if possible. Store Russian users' data on a Russian server and Kazakh users' data on a Kazakh server, or at least obtain explicit cross-border consent. Collect voice only with separate, optional, active, revocable consent limited to non-identification purposes. Exclude or parent-gate minors. Notify RKN. Publish a privacy policy in @BotFather. Get an ethics-committee opinion. Plan for Telegram degradation.

### Cited Findings
- Requirements underpinning the checklist:
  - RKN notification with database location ([consultant.ru ст. 22](https://www.consultant.ru/document/cons_doc_LAW_61801/d996966e22e1320c9de1ab82d9f6be12c3d9d765/))
  - Separate consent document from 01.09.2025 ([ppt.ru](https://ppt.ru/news/personal-data/oformlyat-soglasie-na-obrabotku-personalnykh-dannykh-nuzhno-budet-po-novomu))
  - Cross-border notification from 01.03.2023 ([Kontur](https://kontur.ru/articles/1478))
  - Kazakhstan: localization (ст. 12), consent (ст. 8), ст. 16 and ст. 19-1 ([UPPERSETUP](https://uppersetup.com/ru/blog/personal-data-and-localisation-in-kazakhstan-in-2026-law-no))
  - Telegram §4 terms ([telegram.org](https://telegram.org/tos/bot-developers))
  - Throttling of voice notes ([The Moscow Times](https://www.themoscowtimes.com/2026/02/10/roskomnadzor-tightens-restrictions-on-telegram-as-users-report-disruptions-a91907))

### Inferences
**A. Governance**
1. Ask the supervisor/university: can the university be the operator (with you acting under its instruction) and is an ethics-committee opinion required? Obtain the opinion anyway (sensitive data: religion, voice, possible minors).
2. If you are the operator yourself, file the RKN notification (pd.rkn.gov.ru, electronic form). Include purposes, categories (Telegram ID, username, learning results, voice recordings), the subject category "users of the bot (learners) in RF and RK", the legal basis (consent, ст. 6 ч. 1 п. 1; ст. 10 for religious-belief inference if applicable), the Russian server address, cross-border status and security measures. Give the notification before starting processing.
3. If any data goes abroad (Kazakh server, foreign cloud GPU for training, Hugging Face, Google Colab, OpenAI API, etc.), file the cross-border notification first. Prefer adequate countries (Kazakhstan is a party to Convention 108, so treated as adequate; verify RKN list).

**B. Data architecture**
4. Russian users → Russian VPS (primary DB and voice storage). Kazakh users → Kazakh VPS, or Russia with explicit ст. 16 consent. The latter still leaves a formal ст. 12 localization gap.
5. Pseudonymise: store a random participant code in the research DB. Keep the Telegram-ID ↔ code key in a separate, access-restricted table. Encrypt at rest, with keys stored separately (Telegram §4.4).
6. Voice: store the original file plus derived features. Do NOT compute or store speaker embeddings/voiceprints. Strip metadata. For ML, train only on consenting users' data. Document dataset provenance (datasheet).
7. Train in Russia, or document cross-border use if foreign compute is used.

**C. Consent flow (in the bot, before first data collection)**
8. Screen 1, information sheet (short, plain language, RU/KZ): who you are (full name, university, supervisor, contacts), purpose (learning Quranic Arabic reading; master's research; improving the bot's pronunciation model), what is collected, where it is stored (country), how long, who has access, risks, voluntariness, how to withdraw (/delete, /withdraw), and a link to the full privacy policy (also set in @BotFather).
9. Consent 1 (required to use the bot): processing of Telegram ID and learning results for providing the service and for research in pseudonymised form. This is a separate consent document/message, not part of the ToS (156-ФЗ).
10. Consent 2 (optional, separate button, not pre-selected): recording and storing voice for (a) automated pronunciation assessment, (b) research analysis, (c) training and evaluating speech models. State explicitly: "не используется для установления личности (идентификации)". State data-sharing (none / named co-researchers), retention, and cross-border (yes/no, which country). The bot must still work if declined, e.g. with listening-only exercises.
11. Optional Consent 3: use of anonymised excerpts in publications or open datasets. Default: no. Do not publish raw voice openly.
12. Log each consent: timestamp, consent version, text hash, Telegram ID. Allow withdrawal at any time. On withdrawal, delete the voice within a stated term (Kazakhstan: 15 working days, ст. 8 п. 7; Russia: ст. 21 ч. 5 gives 30 days, background knowledge). Explain what happens to already-trained models: weights are not "unlearned", so say so honestly.
13. Kazakhstan ст. 19-1: mention automated assessment, its consequences (feedback only, no grading with legal effect) and an objection channel answered within 3 working days.

**D. Minors**
14. Age gate at start. Under 18: either exclude from voice and research (allow learning only, with no data retained beyond the session), or require parental consent (a parent confirms via a separate flow; hard to verify in Telegram). Recommended for a master's thesis: research and voice for adults (18+) only.

**E. Retention**
15. Voice: until the end of the research project plus a defined period (e.g., thesis defence + 1–3 years, per university DMP), then delete or keep only consented anonymised derivatives. Learning results: pseudonymised, same period. Telegram IDs: delete when the account is inactive for X months or when the bot shuts down (Telegram §4.2).

**F. Content**
16. Use the Arabic mushaf text only. If translations are used, check the Minjust federal list of extremist materials first. Avoid tafsir; moderate user content.

**G. Platform resilience**
17. Provide a web/Mini-App recording path to your own server. Announce backup channels (website, email). Record platform-induced data loss as a methodological limitation. Avoid MAX for voice research, or disclose it.

**H. Security and incidents**
18. Keep a minimal security policy (ст. 18.1 152-ФЗ documents: processing policy, order on the responsible person, list of persons with access). Since 2022 (266-ФЗ, background knowledge) leaks must be reported to RKN within 24 h, with follow-up within 72 h.

### Gaps
- Whether RKN treats a lone student researcher as needing a full set of ст. 18.1 organisational documents: no source found.
- Russia–Kazakhstan adequacy status in the RKN list was not verified in this session.
- 24h/72h breach-notification and 30-day withdrawal timelines are from background knowledge (266-ФЗ, ст. 21 152-ФЗ) and were not re-verified here.
