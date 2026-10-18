# Рисунки и таблицы диссертации

У каждого рисунка и таблицы — постоянный ID (Р-NN, Т-NN), источник и паспорт: из чего и когда
построено. Номер в тексте («Рисунок 2.1») назначается при вёрстке; ID не меняется (ADR-0036).
Ссылаются на ID: `../research/traceability.md`, черновики `chapters/`.

**Статус:** ✅ готов · 🔄 строится из данных (обновлять перед сдачей) · ⏳ планируется.
**Паспорт** для 🔄: отчёт (`analytics/reports/…`), дата, n попыток / учеников, отпечаток кода из
`make trace`. Без паспорта цифра в главу не идёт.

## Рисунки
| ID | Что | Глава | Файл | Строится из | Статус |
|---|---|---|---|---|---|
| Р-01 | Контекст системы | 2 | `docs/architecture/diagrams/01-context.png` | `docs/architecture/diagrams/01-context.mmd`, `make diagrams` | ✅ |
| Р-02 | Слои архитектуры | 2 | `docs/architecture/diagrams/02-layers.png` | `docs/architecture/diagrams/02-layers.mmd` | ✅ |
| Р-03 | Обработка голосового (последовательность) | 2 | `docs/architecture/diagrams/03-voice-sequence.png` | `docs/architecture/diagrams/03-voice-sequence.mmd` | ✅ |
| Р-04 | Схема БД | 2 | `docs/architecture/diagrams/04-er.png` | `docs/architecture/diagrams/04-er.mmd` | ✅ |
| Р-05 | Жизненный цикл данных | 5 | `docs/architecture/diagrams/05-data-lifecycle.png` | `docs/architecture/diagrams/05-data-lifecycle.mmd` | ✅ |
| Р-06 | Петля агента: хуки и TDD-фазы | 3 | `docs/architecture/diagrams/06-agent-loop.png` | `docs/architecture/diagrams/06-agent-loop.mmd` | ✅ (обновлено 2026-10-18, ADR-0039) |
| Р-07 | Смысловые области (bounded contexts) | 2 | `docs/architecture/diagrams/07-contexts.png` | `docs/architecture/diagrams/07-contexts.mmd` | ✅ |
| Р-08 | Precision/recall по типу ошибки и букве | 4 | — | `src/muallim/research/metrics.py` | ⏳ |
| Р-09 | Матрица путаниц: все ошибки / подтверждённые | 4 | — | `analytics/sql/04_letter_confusions.sql` | ⏳ |
| Р-10 | Ошибки по признакам сифат | 4 | — | TD-FN-36 | ⏳ |
| Р-11 | Δ балла и исправленные ошибки после объяснения | 4 | — | TD-FN-24 | ⏳ |
| Р-12 | Главная метрика пилота по неделям | 4 | — | TD-FN-24 | ⏳ |
| Р-13 | Срабатывания хуков по причинам | 3 | — | `docs/journal/hooks/` | ⏳ |
| Р-14 | Риск — покрытие B1: доля ложных отклонений против доли «не уверен» (RQ-2, ADR-0051) | 4 | — | TD-FN-72 | ⏳ |
| Р-15 | Кривая обучения B2: F1 при 25 / 50 / 75 / 100 % обучающих учеников (RQ-2, разведка) | 4 | — | TD-FN-72 | ⏳ |

## Рисунки TikZ для текстов на двух языках (`thesis/figures/`)
Р-01, Р-02, Р-03 и Р-06 в диссертации нарисованы заново в TikZ с подписями на двух языках (исходные `.mmd`
подписаны по-русски): `fig-context.tex` (Р-01), `fig-layers.tex` (Р-02), `fig-pipeline.tex` (ср. Р-03),
`fig-harness.tex` (ср. Р-06). Новые: `fig-research-design.tex` (дизайн исследования), `fig-gantt.tex` (план
работ). Снимки экранов `screen-card.png`, `screen-result.png` — копии `docs/design/screens/07_line.png`,
`09_result_errors.png` на 2026-10-18. При изменении архитектуры обновлять и `.mmd`, и TikZ.

## Таблицы
| ID | Что | Глава | Строится из | Статус |
|---|---|---|---|---|
| Т-01 | Качество проверки: precision, recall, F1, FAR, FRR, ДИ, n | 4 | `src/muallim/research/metrics.py` | ⏳ |
| Т-02 | Согласие: κ «бот — учитель» и «учитель — учитель» | 4 | `src/muallim/research/metrics.py` | ⏳ |
| Т-03 | Частота типов ошибок, число учеников | 4 | `analytics/sql/03_error_kinds.sql` | ⏳ |
| Т-04 | Трудные строки и пары книги | 4 | `analytics/sql/08_book_lines.sql` | ⏳ |
| Т-05 | Отложенный тест (RQ-3) | 4 | roadmap 1.7 | ⏳ |
| Т-06 | Путь новичка: первый успех, возврат, отток | 4 | `src/muallim/research/metrics.py` | ⏳ |
| Т-07 | Сценарии качества на данных пилота (QAS-02…04) | 4 | `src/muallim/research/metrics.py` | ⏳ |
| Т-08 | Методика агентов: вмешательства, итерации | 3 | `docs/journal/sessions/` | ⏳ |
| Т-09 | Сравнение с аналогами (Tarteel, IqraEval, muallimi_soniy) | 1 | `docs/research/literature-review.md` | ⏳ |
| Т-10 | Сравнение инструментов для бота | 2 | `docs/research/bot-tooling.md` | ✅ (черновик) |
| Т-11 | B0 / B1 / B2 на тестовых учениках: P, R, F1, FAR, FRR, κ, доля закрытого разрыва, ECE, ДИ (RQ-2) | 4 | TD-FN-72 | ⏳ |
| Т-12 | PER на чтении экспертов: B0 vs B2 (H2.3) | 4 | TD-FN-72 | ⏳ |
