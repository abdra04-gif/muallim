# Статус трассировки (сгенерировано `make trace`, не править руками)

Сформирован: 2026-10-20T19:55:27+00:00. Матрицы: `docs/requirements/traceability.md`, `docs/research/traceability.md` (ADR-0036).

## Отпечаток версии
Записывайте в паспорт рисунка или таблицы (`docs/thesis/figures.md`) и рядом с отчётом.

| Часть | SHA-256 (16 знаков) | Файлов |
|---|---|---|
| код | `efc7a6e733edd2be` | 99 |
| программа (книга) | `125a24eb1ee7e973` | 3 |
| SQL-отчёты | `35bb9e9f17483fc5` | 11 |
| миграции | `5009ec6fb8d3cec0` | 8 |
| зависимости | `a9f76fc0b602ab89` | 1 |
| предрегистрация | `dd14f532dd71f045` | 1 |

## Требования
Проверено зелёными тестами: **63 из 66**.

| ID | Тесты из матрицы | Сейчас |
|---|---|---|
| FR-01 | `tests/architecture/test_book.py`, `tests/unit/test_curriculum_content.py`, `tests/unit/test_screens.py` | ✅ |
| FR-02 | `tests/unit/test_curriculum_model.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-03 | `tests/integration/test_bot_flow.py` | ✅ |
| FR-04 | `tests/unit/test_assessment.py`, `tests/unit/test_policy.py` | ✅ |
| FR-05 | `tests/unit/test_feedback.py` | ✅ |
| FR-06 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py` | ✅ |
| FR-07 | `tests/unit/test_use_cases.py` | ✅ |
| FR-08 | `tests/unit/test_use_cases.py` | ✅ |
| FR-09 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-10 | `tests/integration/test_bot_flow.py`, `tests/integration/test_erasures.py`, `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-11 | `tests/integration/test_research.py` | ✅ |
| FR-12 | `tests/unit/test_use_cases.py` | ✅ |
| FR-13 | `tests/integration/test_research.py` | ✅ |
| FR-14 | `tests/integration/test_research.py`, `tests/unit/test_metrics.py` | ✅ |
| FR-17 | `tests/integration/test_annotator_bot.py`, `tests/integration/test_annotators_sql.py`, `tests/unit/test_annotation.py` | ✅ |
| FR-20 | `tests/integration/test_reference_audio.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-21 | `tests/integration/test_console_beginner.py`, `tests/unit/test_transcription.py` | ✅ |
| FR-22 | `tests/unit/test_feedback_languages.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-23 | `tests/integration/test_bot_flow.py`, `tests/integration/test_constraints.py`, `tests/integration/test_research.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-24 | `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-25 | `tests/integration/test_console_beginner.py`, `tests/integration/test_staff_bot.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-26 | `tests/integration/test_data_tools.py`, `tests/integration/test_di.py` | ✅ |
| FR-27 | `tests/architecture/test_migrations.py`, `tests/integration/test_data_tools.py` | ✅ |
| FR-28 | `tests/integration/test_data_tools.py`, `tests/integration/test_postgres.py` | ✅ |
| FR-29 | — | нет автотестов |
| FR-30 | `tests/integration/test_reference_audio.py`, `tests/integration/test_teacher_bot.py`, `tests/unit/test_screens.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-31 | `tests/unit/test_screens.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-32 | `tests/unit/test_curriculum_model.py`, `tests/unit/test_screens.py` | ✅ |
| FR-33 | `tests/unit/test_render.py` | ✅ |
| FR-34 | `tests/unit/test_curriculum_content.py` | ✅ |
| FR-35 | `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-36 | `tests/unit/test_curriculum_content.py` | ✅ |
| FR-37 | `tests/unit/test_curriculum_content.py`, `tests/unit/test_screens.py` | ✅ |
| FR-38 | `tests/unit/test_render.py`, `tests/unit/test_screens.py` | ✅ |
| FR-39 | `tests/unit/test_quiz.py`, `tests/unit/test_screens.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-40 | `tests/integration/test_reference_audio.py` | ✅ |
| FR-41 | `tests/unit/test_curriculum_content.py` | ✅ |
| FR-42 | `tests/integration/test_di.py` | ✅ |
| FR-43 | `tests/integration/test_reading_guide.py`, `tests/unit/test_feedback.py`, `tests/unit/test_screens.py`, `tests/unit/test_send.py`, `tests/unit/test_syllables.py`, `tests/unit/test_transcription.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-44 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-45 | `tests/integration/test_opening_bot.py`, `tests/unit/test_new_screens.py` | ✅ |
| FR-46 | `tests/unit/test_new_screens.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-47 | `tests/unit/test_new_screens.py` | ✅ |
| FR-48 | `tests/unit/test_readable_images.py` | ✅ |
| FR-49 | `tests/integration/test_console_beginner.py`, `tests/integration/test_isti_adha_audio.py`, `tests/integration/test_opening_bot.py`, `tests/unit/test_beginner_screens.py`, `tests/unit/test_quiz.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-50 | `tests/integration/test_console_beginner.py`, `tests/integration/test_staff_bot.py`, `tests/unit/test_beginner_screens.py`, `tests/unit/test_staff.py`, `tests/unit/test_use_cases.py` | ✅ |
| FR-51 | — | нет автотестов |
| FR-52 | — | нет автотестов |
| NFR-TR-01 | `tests/unit/test_curriculum_content.py` | ✅ |
| NFR-TR-02 | `tests/architecture/test_docs.py` | ✅ |
| NFR-TR-03 | `tests/architecture/test_db_scripts.py`, `tests/integration/test_audio_store.py`, `tests/integration/test_integrity.py` | ✅ |
| NFR-TR-04 | `tests/architecture/test_hooks.py` | ✅ |
| NFR-REL-02 | `tests/architecture/test_logging.py`, `tests/integration/test_audio_decode.py`, `tests/integration/test_metrics_report.py`, `tests/unit/test_use_cases.py` | ✅ |
| NFR-ACC-01 | `tests/integration/test_metrics_report.py`, `tests/unit/test_metrics.py` | ✅ |
| NFR-SEC-01 | `tests/architecture/test_hooks.py` | ✅ |
| NFR-SEC-08 | `tests/architecture/test_db_scripts.py`, `tests/integration/test_postgres_roles.py` | ✅ |
| NFR-SEC-02 | `tests/integration/test_research.py` | ✅ |
| NFR-SEC-03 | `tests/integration/test_audio_store.py` | ✅ |
| NFR-SEC-04 | `tests/integration/test_sql_repositories.py` | ✅ |
| NFR-MNT-01 | `tests/architecture/test_layers.py`, `tests/architecture/test_presentation_state.py`, `tests/integration/test_teacher_bot.py` | ✅ |
| NFR-MNT-03 | `tests/architecture/test_migrations.py` | ✅ |
| NFR-SEC-06 | `tests/architecture/test_dep_check.py` | ✅ |
| NFR-MNT-06 | `tests/architecture/test_learner_texts.py` | ✅ |
| NFR-MNT-07 | `tests/integration/test_console.py` | ✅ |
| NFR-SEC-07 | `tests/architecture/test_logging.py`, `tests/unit/test_logs.py` | ✅ |
| NFR-TR-05 | `tests/architecture/test_docs.py` | ✅ |

## Исследование
Строк в матрице: 43 — считается ✅ 9, частично 🟡 6, нет ❌ 22, данных не собираем 6.
