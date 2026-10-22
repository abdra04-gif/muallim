# Материалы для диссертации

Карта: глава → где брать материал в репозитории. Агент `thesis-scribe` пополняет
`materials-log.md` по ходу работы, чтобы к моменту написания всё было собрано.

| Глава (структура по ADR-0052, RQ — ADR-0064; тексты — `thesis/chapters/`) | Материал |
|---|---|
| Введение: контекст и актуальность (наука, практика, индустрия, 09.04.01), проблема, цель, задачи, гипотеза, RQ-1…RQ-3, вклад C1–C4, объект и новизна | `docs/adr/0052-dataset-and-ai-model-as-thesis-object.md`, `docs/research/literature-review.md` (RQ), `docs/requirements/requirements.md` |
| 2. Обзор: букварь, ученики, обратная связь, оценка чтения Корана, адаптация моделей, репетиторы чтения и отслеживание знаний, ИИ-агенты | `docs/pedagogy/teaching-practice.md`, `docs/research/literature-review.md`, `docs/research/sources.md`, `reports/Муаллим ас Сани методика ИИ и этика.md` |
| 3. Методология: design science, GQM, гипотезы, четыре исследования, предрегистрация, достоверность разработки | `docs/research/metrics-gqm.md`, `docs/research/preregistration.md`, `docs/data/annotation-guide.md`, `docs/process/agent-harness.md`, `docs/risks.md` |
| 4. Реализация: программа и карта навыков, инструмент сбора и разметка, модели B1/B2 и K1/K2, приватность, обвязка | `docs/architecture/overview.md`, схемы `docs/architecture/diagrams/*.png`, `docs/adr/`, `docs/data/data-dictionary.md`, `docs/security/` |
| 5. Оценка и обсуждение: RQ-1…RQ-3, достоверность разработки | `docs/research/traceability.md`, `docs/thesis/figures.md`, `analytics/reports/`, `docs/journal/sessions/`, `docs/journal/hooks/` |
| 6. Заключение: личный вклад автора, апробация, докторантура | `docs/roadmap.md`, `docs/research/open-questions.md`, `docs/tech-debt.md` |
| Приложения | трассировка исследования и требований, транскрипция, кратко о предрегистрации |

Требования вуза (Положение о ГИА, формы отзыва и рецензии) и как работа им отвечает —
`university-requirements.md`; объём глав: цель и сейчас — `page-budget.md` (ADR-0053).
Аннотация на русском (обязательна, 4–5 с.) — `thesis/annotation-ru.tex`, `make annotation`.

Рисунки для Word/LaTeX — `docs/architecture/diagrams/*.png` (2× разрешение).
Библиография — `docs/research/sources.bib`.
