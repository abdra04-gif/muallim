# Материалы для диссертации

Карта: глава → где брать материал в репозитории. Агент `thesis-scribe` пополняет
`materials-log.md` по ходу работы, чтобы к моменту написания всё было собрано.

| Глава (черновик структуры, утверждает руководитель) | Материал |
|---|---|
| Введение: актуальность, цель, задачи, RQ | `docs/requirements/requirements.md` (цель), `docs/research/literature-review.md` (RQ) |
| 1. Обзор: обучение чтению по «Муаллим ас-Сани», автоматическая оценка произношения | `docs/pedagogy/teaching-practice.md`, `docs/research/literature-review.md`, `docs/research/sources.md`, `reports/Муаллим ас Сани методика ИИ и этика.md` |
| 2. Проектирование системы | `docs/requirements/quality-scenarios.md` (сценарии качества), `docs/architecture/overview.md`, схемы `docs/architecture/diagrams/*.png`, `docs/adr/` (в т. ч. отклонённые альтернативы), `docs/data/data-dictionary.md` |
| 3. Методика разработки с ИИ-агентами | `docs/process/agent-harness.md`, `docs/journal/prompts/` (история запросов), `docs/journal/meetings/` (решения руководителя), `docs/risks.md` (риски и доказательства мер), ADR-0011/0012 |
| 4. Эксперимент: пилот с учениками, разметка, оценка модели | `docs/research/metrics-gqm.md` (цели, вопросы, метрики), `analytics/reports/`, `docs/data/annotation-guide.md`, выгрузки `data/exports/` |
| 5. Безопасность и этика | `docs/security/` |
| Заключение, дальнейшая работа (докторантура) | `docs/roadmap.md`, `docs/research/open-questions.md`, `docs/tech-debt.md` |
| Приложения | матрица трассировки, словарь данных, код ключевых модулей |

Рисунки для Word/LaTeX — `docs/architecture/diagrams/*.png` (2× разрешение).
Библиография — `docs/research/sources.bib`.
