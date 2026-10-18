# Статус трассировки (сгенерировано `make trace`, не править руками)

Сформирован: 2026-10-18T02:02:16+00:00. Матрицы: `docs/requirements/traceability.md`, `docs/research/traceability.md` (ADR-0036).

## Отпечаток версии
Записывайте в паспорт рисунка или таблицы (`docs/thesis/figures.md`) и рядом с отчётом.

| Часть | SHA-256 (16 знаков) | Файлов |
|---|---|---|
| код | `7d4e156cb0541607` | 75 |
| программа (книга) | `65ad89963eb0aeee` | 3 |
| SQL-отчёты | `e48f975a8cc23f52` | 11 |
| миграции | `d83a9fe5cd87809b` | 4 |
| зависимости | `af8a1c870e87abfe` | 1 |
| предрегистрация | `d919a6ff575c0fce` | 1 |

## Требования
Проверено зелёными тестами: **0 из 53**. Тесты не запускались (`--no-tests`).

| ID | Тесты из матрицы | Сейчас |
|---|---|---|
| FR-01 | `tests/architecture/test_book.py`, `tests/unit/test_curriculum_content.py`, `tests/unit/test_screens.py` | не запускались |
| FR-02 | `tests/unit/test_curriculum_model.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-03 | `tests/integration/test_bot_flow.py` | не запускались |
| FR-04 | `tests/unit/test_assessment.py`, `tests/unit/test_policy.py` | не запускались |
| FR-05 | `tests/unit/test_feedback.py` | не запускались |
| FR-06 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py` | не запускались |
| FR-07 | `tests/unit/test_use_cases.py` | не запускались |
| FR-08 | `tests/unit/test_use_cases.py` | не запускались |
| FR-09 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-10 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-11 | `tests/integration/test_research.py` | не запускались |
| FR-12 | `tests/unit/test_use_cases.py` | не запускались |
| FR-13 | `tests/integration/test_research.py` | не запускались |
| FR-14 | `tests/integration/test_research.py` | не запускались |
| FR-20 | `tests/integration/test_reference_audio.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-21 | `tests/unit/test_transcription.py` | не запускались |
| FR-22 | `tests/unit/test_feedback_languages.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-23 | `tests/integration/test_bot_flow.py`, `tests/integration/test_research.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-24 | `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-25 | `tests/unit/test_use_cases.py` | не запускались |
| FR-26 | `tests/integration/test_data_tools.py`, `tests/integration/test_di.py` | не запускались |
| FR-27 | `tests/architecture/test_migrations.py`, `tests/integration/test_data_tools.py` | не запускались |
| FR-28 | `tests/integration/test_data_tools.py`, `tests/integration/test_postgres.py` | не запускались |
| FR-29 | — | нет автотестов |
| FR-30 | `tests/integration/test_reference_audio.py`, `tests/unit/test_screens.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-31 | `tests/unit/test_screens.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-32 | `tests/unit/test_curriculum_model.py`, `tests/unit/test_screens.py` | не запускались |
| FR-33 | `tests/unit/test_render.py` | не запускались |
| FR-34 | `tests/unit/test_curriculum_content.py` | не запускались |
| FR-35 | `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-36 | `tests/unit/test_curriculum_content.py` | не запускались |
| FR-37 | `tests/unit/test_curriculum_content.py`, `tests/unit/test_screens.py` | не запускались |
| FR-38 | `tests/unit/test_render.py`, `tests/unit/test_screens.py` | не запускались |
| FR-39 | `tests/unit/test_quiz.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-40 | `tests/integration/test_reference_audio.py` | не запускались |
| FR-41 | `tests/unit/test_curriculum_content.py` | не запускались |
| FR-42 | `tests/integration/test_di.py` | не запускались |
| FR-43 | `tests/integration/test_reading_guide.py`, `tests/unit/test_feedback.py`, `tests/unit/test_screens.py`, `tests/unit/test_send.py`, `tests/unit/test_syllables.py`, `tests/unit/test_transcription.py`, `tests/unit/test_use_cases.py` | не запускались |
| FR-44 | `tests/integration/test_bot_flow.py`, `tests/integration/test_sql_repositories.py`, `tests/unit/test_use_cases.py` | не запускались |
| NFR-TR-01 | `tests/unit/test_curriculum_content.py` | не запускались |
| NFR-TR-02 | `tests/architecture/test_docs.py` | не запускались |
| NFR-TR-03 | `tests/architecture/test_db_scripts.py`, `tests/integration/test_audio_store.py`, `tests/integration/test_integrity.py` | не запускались |
| NFR-TR-04 | `tests/architecture/test_hooks.py` | не запускались |
| NFR-REL-02 | `tests/integration/test_audio_decode.py`, `tests/integration/test_metrics_report.py`, `tests/unit/test_use_cases.py` | не запускались |
| NFR-ACC-01 | `tests/integration/test_metrics_report.py`, `tests/unit/test_metrics.py` | не запускались |
| NFR-SEC-01 | `tests/architecture/test_hooks.py` | не запускались |
| NFR-SEC-02 | `tests/integration/test_research.py` | не запускались |
| NFR-SEC-03 | `tests/integration/test_audio_store.py` | не запускались |
| NFR-SEC-04 | `tests/integration/test_sql_repositories.py` | не запускались |
| NFR-MNT-01 | `tests/architecture/test_layers.py` | не запускались |
| NFR-MNT-03 | `tests/architecture/test_migrations.py` | не запускались |
| NFR-SEC-07 | `tests/architecture/test_logging.py`, `tests/unit/test_logs.py` | не запускались |
| NFR-TR-05 | `tests/architecture/test_docs.py` | не запускались |

## Исследование
Строк в матрице: 27 — считается ✅ 9, частично 🟡 5, нет ❌ 10, данных не собираем 3.
