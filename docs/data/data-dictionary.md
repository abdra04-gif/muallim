# Словарь данных

Описание каждой таблицы и поля. Источник истины — `src/muallim/infrastructure/db/tables.py`;
при изменении схемы обновляется и этот файл (проверяет агент architecture-guardian), и создаётся
миграция. Схема связей: ![ER](../architecture/diagrams/04-er.svg)

**Категории данных:** 🔴 персональные · 🟡 псевдонимизированные · 🟢 не персональные.

## `learners` — ученики
| Поле | Тип | Описание | Кат. |
|---|---|---|---|
| `id` | UUID, PK | внутренний постоянный идентификатор | 🟡 |
| `telegram_user_id` | bigint, уникальный | Telegram ID; **не выгружается** в исследовательские данные | 🔴 |
| `pseudonym` | varchar(16), уникальный | `L-` + 8 hex-символов из `id`; единственный идентификатор в отчётах и датасете | 🟡 |
| `language` | varchar(8) | язык Telegram-клиента (для будущей локализации) | 🟢 |
| `current_item_id` | varchar(32) | открытая карточка, например `L18-01` (id из `curriculum/course.ru.yaml`) | 🟢 |
| `research_consent` | bool | текущее согласие на хранение записей (история — в `consents`) | 🟢 |
| `blocked_bot` | bool | ученик заблокировал бота (зарезервировано) | 🟢 |
| `feedback_language` | varchar(8), null | язык объяснений (ADR-0017); пока только русский — команда /language скрыта (ADR-0022), значение не меняется | 🟢 |
| `created_at` | timestamptz (UTC) | дата регистрации | 🟢 |

## `learner_profiles` — анкета ученика (FR-44, ADR-0038)
Одна строка на ученика, заполняется один раз после согласия на исследование; не перезаписывается.
Удаляется вместе с учеником (CASCADE). Только кнопки — свободного текста нет.
| Поле | Тип | Описание | Кат. |
|---|---|---|---|
| `learner_id` | UUID, PK → learners, CASCADE | чья анкета | 🟡 |
| `adult` | bool | ответ «мне 18+»; `false` — согласие на запись голоса снято, остальное не спрашивалось | 🔴 |
| `native_language` | varchar(8), null | `ru` / `kk` / `tt` / `other`; null у младших 18 | 🔴 |
| `arabic_reading` | varchar(16), null | `none` / `some_letters` / `slow_syllables` — опыт чтения до бота; null у младших 18 | 🟡 |
| `questionnaire_version` | varchar(16) | версия вопросов (`QUESTIONNAIRE_VERSION`) | 🟢 |
| `answered_at` | timestamptz (UTC) | когда ответил | 🟢 |

## `consents` — журнал согласий
Каждое «да»/«нет» — новая строка; ничего не перезаписывается.
| Поле | Тип | Описание |
|---|---|---|
| `id` | int, PK | |
| `learner_id` | UUID → learners, CASCADE | |
| `kind` | varchar(32) | сейчас только `research_audio` |
| `granted` | bool | дал / отозвал |
| `text_version` | varchar(32) | версия текста согласия (`CONSENT_TEXT_VERSION`) |
| `at` | timestamptz | когда |

## `attempts` — попытки чтения (основная единица данных)
| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID, PK | |
| `learner_id` | UUID → learners, CASCADE | |
| `item_id` | varchar(32) | карточка из `curriculum/course.ru.yaml` |
| `curriculum_version` | varchar(32) | `version` из YAML на момент попытки |
| `model_version` | varchar(128) | пакет модели, версия и параметры чтения; `stub` — заглушка, исключается из отчётов |
| `reference_phonemes` | text | эталон, по которому оценено (лучший из вакф/васл) |
| `heard_phonemes` | text | что распознала модель |
| `score` | smallint 0–100 | сходство последовательностей фонем (`difflib.SequenceMatcher.ratio`) |
| `verdict` | varchar(16) | `excellent` / `passed` / `failed` (пороги — `domain/policy.py`) |
| `audio_sha256` | varchar(64), null | хеш записи; `null` — согласия не было |
| `audio_duration_ms` | int, null | длительность записи |
| `processing_ms` | int | время распознавания и оценки (NFR-PERF-01) |
| `created_at` | timestamptz | |
| `reference_variant` | varchar(16), null | по какому эталону оценено: `wasl` / `waqf` (ADR-0019) |
| `candidates` | JSON, null | все эталоны: `[{"variant", "reference", "score"}]` |
| `model_output` | JSON, null | сырые данные модели сверх строки фонем (для отладки и дообучения) |
| `policy` | JSON, null | пороги на момент решения: `{"pass_threshold", "excellent_threshold"}` |
| `app_version` | varchar(64), null | версия кода: `0.2.0+a1b2c3d[-dirty]` |
| `feedback_language` | varchar(8), null | на каком языке показано объяснение |

Поля следа решения пусты у попыток до миграции 0002.

## `curriculum_items` — снимок учебной программы (ADR-0023)
Пишется ботом при старте: одна строка на карточку каждой версии программы. Нужен, чтобы любую
попытку связать со страницей и строкой книги и с тем текстом, который видел ученик, даже после
правок `course.ru.yaml`. Если контент изменён без новой `version`, бот не запустится.

| Поле | Тип | Описание | Кат. |
|---|---|---|---|
| `curriculum_version` | varchar(32), PK | версия программы (= `attempts.curriculum_version`) | 🟢 |
| `item_id` | varchar(32), PK | id карточки (= `attempts.item_id`) | 🟢 |
| `lesson_id` | varchar(16) | урок, `L18` | 🟢 |
| `lesson_number` | smallint | номер урока по порядку книги | 🟢 |
| `lesson_title` | varchar(128) | название урока, как в меню бота | 🟢 |
| `position` | smallint | номер карточки в уроке, с 1 | 🟢 |
| `kind` | varchar(16) | `letter` / `line` / `word` | 🟢 |
| `text` | text | арабский текст карточки | 🟢 |
| `note` | text | пометка книги, например «Обратите внимание: пары похожих слов» | 🟢 |
| `source_id` | varchar(16), null | источник, `SRC-040` | 🟢 |
| `page` | smallint, null | страница книги | 🟢 |
| `line` | smallint, null | строка на странице (`book/README.md`) | 🟢 |
| `verified` | boolean | сверено человеком с книгой | 🟢 |
| `published_at` | timestamptz | когда версия впервые записана в БД | 🟢 |

## Представления (views) для просмотра — `src/muallim/infrastructure/db/views.py`
Только чтение. Telegram ID в них нет — только псевдоним. Открывать в DBeaver/psql (`docs/data/browsing.md`).

| Представление | Строка = | Главные поля |
|---|---|---|
| `v_attempts` | попытка | `pseudonym`, `item_id`, `lesson_id`, `page`, `line`, `item_text`, `item_note`, `score`, `verdict`, `errors`, `disputed`, `annotations`, `audio_sha256`, `model_version` |
| `v_errors` | найденная ошибка | `pseudonym`, `item_id`, `page`, `line`, `item_text`, `kind`, `expected`, `heard`, `position`, `syllable`, `message`, `score`, `label` (последняя разметка), `disputed`, `audio_sha256` |

## `detected_errors` — ошибки, найденные системой
| Поле | Тип | Описание |
|---|---|---|
| `id` | int, PK | |
| `attempt_id` | UUID → attempts, CASCADE | |
| `ordinal` | smallint | порядок в ответе ученику |
| `kind` | varchar(32) | тип из `domain.assessment.ErrorKind`: `letter_substitution`, `vowel_substitution`, `sound_substitution`, `fragment_substitution`, `madd_too_short`, `vowel_missing`, `shadda_missing`, `sound_missing`, `madd_too_long`, `extra_sound` |
| `position` | smallint | индекс в `reference_phonemes` |
| `syllable` | smallint, null | номер слога; `null` для односложных карточек |
| `expected` / `heard` | varchar(16) | что должно было прозвучать / что прозвучало |
| `message` | text | точный текст, который увидел ученик |

## `annotations` — разметка человеком
| Поле | Тип | Описание |
|---|---|---|
| `id` | int, PK | |
| `attempt_id` | UUID → attempts, CASCADE | |
| `detected_error_id` | int → detected_errors, null | не заполняется с руководства 2.0: ошибки по фонемам выводятся из `corrected_phonemes`; кандидат на удаление миграцией (TD-DB-04) |
| `annotator` | varchar(64) | **код** разметчика (A1, T2), не имя; латиница, цифры, `-`, `_` |
| `label` | varchar(32) | с 2.0: `agree` (бот услышал верно), `fix` (исправлено), `audio_unusable`, `off_task`; метки 1.0 (`correct`, `false_alarm`, …) в метрики не входят |
| `corrected_phonemes` | text, null | что прозвучало на самом деле (Quran Phonetic Script): при `agree` — то, что услышал бот, при `fix` — исправленное; `null` — `audio_unusable` / `off_task` |
| `comment` | text | |
| `guide_version` | varchar(16) | версия руководства по разметке |
| `created_at` | timestamptz | |
| `source` | varchar(16), null | откуда метка: `excel` (пакет `tasks.csv`) или `telegram` (кнопки в боте, FR-17); `null` — метки до миграции 0005 (все из Excel) |
| `seconds_spent` | int, null | секунд от показа записи до ответа — только Telegram; при исправлении фонем — до отправки исправления |
| `self_corrected` | boolean, null | ученик ошибся и сам перечитал верно — отдельная категория (руководство 2.1, ADR-0043); только при `agree`/`fix`; `null` — метки до миграции 0006 (не спрашивали) |

Строки не изменяются и не удаляются при исправлении: исправленная метка — новая строка, в
метриках и датасете берётся **последняя метка каждого разметчика** на попытку (история
сохраняется). Удаляются вместе с попыткой (CASCADE) и при отзыве согласия на запись голоса.

## `annotators` — разметчики по приглашению и отозванные (FR-17, ADR-0041)
| Поле | Тип | Описание |
|---|---|---|
| `code` | varchar(64), PK | код разметчика (A1, A2…), не имя |
| `telegram_user_id` | bigint, unique, null | привязан приглашением; **персональные данные** — только для проверки доступа, в выгрузки не попадает |
| `created_at` | timestamptz | |
| `revoked_at` | timestamptz, null | доступ закрыт (`muallim-research annotator-revoke`); действует и на разметчиков из `ANNOTATOR_IDS` |

Разметчики из `ANNOTATOR_IDS` (настройки) здесь не хранятся, пока их не отзовут.

## `annotator_invites` — приглашения в разметку (FR-17, ADR-0041)
| Поле | Тип | Описание |
|---|---|---|
| `id` | int, PK | |
| `code_digest` | varchar(64), unique | SHA-256 кода приглашения (без регистра, дефисов и пробелов); **сам код не хранится** |
| `annotator` | varchar(64) | для какого кода разметчика |
| `created_at`, `expires_at` | timestamptz | действует сутки |
| `used_at` | timestamptz, null | погашено при входе (один раз); неиспользованные удаляются при отзыве |

## `learner_reports` — жалобы «бот ошибся» (ADR-0020)
| Поле | Тип | Описание |
|---|---|---|
| `id` | int, PK | |
| `attempt_id` | UUID → attempts, CASCADE | оспоренная попытка |
| `learner_id` | UUID → learners, CASCADE | кто оспорил (только свою попытку) |
| `reason` | varchar(32) | `read_correctly` / `wrong_error` / `other` |
| `created_at` | timestamptz | |

## `interaction_events` — журнал действий
| Поле | Тип | Описание |
|---|---|---|
| `id` | int, PK | |
| `learner_id` | UUID → learners, SET NULL | после удаления ученика событие остаётся обезличенным |
| `event` | varchar(48) | `learner_registered`, `consent_changed` (payload: `granted`, `audio_deleted`), `item_opened`, `attempt_assessed`, `recognition_failed` (payload: `item_id`, `stage` = `decode` / `model`, `processing_ms`; без текста ошибки), `reference_played`, `reference_recorded`, `attempt_disputed`, `quiz_answered`, `feedback_language_set`, `learner_deleted`; разметка (FR-17, `learner_id` — сам разметчик): `annotation_shown`, `annotation_submitted` (payload: `annotator`, `attempt_id`, `status`), `annotator_invite_redeemed`, `annotator_invite_failed` (для ограничения подбора кода) |
| `payload` | JSON | только ID карточек, баллы, флаги; **никогда** — текст сообщений |
| `created_at` | timestamptz | |

## Вне БД
| Что | Где | Описание |
|---|---|---|
| Аудиозаписи | `data/audio/<2 символа>/<sha256>.ogg` | оригинал из Telegram (OGG/Opus), права 0600 |
| Учебная программа | `curriculum/course.ru.yaml` | версия → `attempts.curriculum_version` |
| Объяснения на языках | `curriculum/lexicon.<язык>.yaml`, `curriculum/feedback.<язык>.yaml` | язык → `attempts.feedback_language` |
| Эталонные записи | `curriculum/audio/<id>.ogg` | источник — `curriculum/audio/SOURCES.md` |
| Пакеты разметки | `data/annotation/<код>_<дата>/` | `tasks.csv` (UTF-8 с BOM) + `audio/` — копии голосов; удалить после загрузки |
| Выгрузки датасета | `data/exports/<дата>/` | `manifest.jsonl` + `truth.csv`/`predictions.csv` (Iqra'Eval) + `audio/` |
| Журнал удалений | `data/erasures/erasures.jsonl` | вне БД (ADR-0054): строка — время UTC, `delete` / `withdraw` / `grant`, UUID ученика; пишется до commit, повторяется после восстановления |
| Резервные копии | `data/backups/<дата>/` | `db.dump` + `audio.tar.gz` + `erasures.jsonl` + `SHA256SUMS`; неудачная — с суффиксом `-FAILED` |
