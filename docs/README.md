# Документация — где что лежит

| Хочу… | Смотреть |
|---|---|
| понять, что делает система и зачем | `requirements/requirements.md` |
| увидеть архитектуру и схемы | `architecture/overview.md`, картинки в `architecture/diagrams/` |
| понять, как архитектура выросла из требований качества | `architecture/design-iterations.md` |
| узнать, **почему** сделано так и что отбросили | `adr/README.md` |
| понять, откуда взялась строка / цифра / идея | `research/sources.md` (ключи `SRC-NNN`) |
| что я прочитал, что думаю о статье, какие статьи читать дальше | `research/reading/README.md` (`/read-next`, `/read-note`, `/read-draft`) |
| чем обосновано каждое методическое решение, где дыры | `research/justification.md` (`/justify`) |
| что решили с руководителем и когда | `thesis/supervisor/` (`/supervisor`) |
| вопросы к защите и мои ответы | `thesis/defense/questions.md` (`/defense-drill`) |
| найти, где реализовано требование и чем проверено | `requirements/traceability.md` |
| увидеть, какие требования **сейчас** проверены зелёными тестами, и отпечаток версии | `requirements/verification-status.md` (`make trace`) |
| проследить RQ → гипотеза → метрика → расчёт → рисунок в главе | `research/traceability.md` |
| гипотезы и план анализа, зафиксированные до данных | `research/preregistration.md` |
| найти рисунок или таблицу диссертации и из чего они построены | `thesis/figures.md` |
| узнать, чем измеряется качество (скорость, точность, надёжность) | `requirements/quality-scenarios.md` |
| понять, зачем считается каждая метрика и на какой RQ отвечает | `research/metrics-gqm.md` |
| разобраться в таблицах БД | `data/data-dictionary.md` |
| посмотреть данные, написать свой SQL-запрос | `data/browsing.md`, `data/sql-guide.md` |
| разметить данные | `data/annotation-guide.md` |
| построить отчёт | `data/reports.md` |
| узнать про книгу и методику | `pedagogy/` |
| безопасность, персональные данные, этика | `security/` |
| как работать с агентами, хуки, TDD | `process/` |
| собрать материал для диссертации | `thesis/` |
| требования вуза к ВКР (Положение о ГИА), формы отзыва и рецензии, сроки сдачи | `thesis/university-requirements.md` |
| бизнес-часть ВКР: календарь программы, главы (конкуренты, рынок, PMF, юнит-экономика), критерии защиты, **частые ошибки** | `thesis/business-track.md` |
| сколько страниц в каждой главе и сколько нужно | `thesis/page-budget.md` |
| вспомнить, что и когда просили у ИИ | `journal/prompts/` |
| открытые вопросы | `research/open-questions.md` |
| хронология исследования | `research/research-log.md` |
| какие линтеры, хуки, агенты добавить; работы и бот научрука | `research/linters-hooks-agents.md` |
| термины | `glossary.md` |
| что отложено (безопасность и др.) и когда закрыть | `tech-debt.md` |
| план на магистратуру и докторантуру | `roadmap.md` |
| как учат по книге, принципы Максуди → бот | `pedagogy/teaching-practice.md` |
| сводный обзор литературы, права, этики | `../reports/` и `../research_notes/` |
| что делали в каждую рабочую сессию | `journal/sessions/` |
| что решили на встречах с руководителем | `journal/meetings/` |
| что может помешать работе и что с этим делаем | `risks.md` |
| требования глазами ученика, учителя, исследователя | `requirements/user-stories.md` |

Поиск по всему репозиторию: `grep -rn "FR-09" .` — найдёт требование, код, тесты и документы.
