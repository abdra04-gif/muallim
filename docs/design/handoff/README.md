# Муаллим 2.0 — задание на бота (handoff)

Получено 2026-11-14 от ChatGPT по пакету `muallim-for-chatgpt.zip` (сборка `make site`). Текст задания — без изменений (кроме формы записи пути к файлу аудита, чтобы его не принимали за существующий).

| Файл | Что |
|---|---|
| `CLAUDE_IMPLEMENTATION_BRIEF.md` | подробное задание: ограничения, экраны, архитектура, фазы, тесты, приёмка. Начинать с Фазы 0 (аудит), код не менять до отчёта и подтверждения автора |
| `muallim-2.0-eight-screens.jpg` | концепт восьми экранов (направление, не утверждённый контент; PNG-оригинал сжат в JPG, чтобы пройти лимит 1 МБ) |

Задание ссылается на имена из пакета для ChatGPT. В репозитории это:
- `PROJECT-RULES.md` → `CLAUDE.md` в корне;
- `spec-for-chatgpt.md` → собирается `make site` из `docs/site/content/*.md` (читать исходники там);
- `design/muallim-2.0-eight-screens.png` → `muallim-2.0-eight-screens.jpg` в этой папке.

Что сделано после задания (тоже читать): демо уроков `docs/site/lessons.tpl.html` + `docs/site/lessons.sim.js` +
`docs/site/lessons-content.yaml`, макеты `docs/design/widgets/v3/`, ранние черновики концепции — `docs/design/drafts/`,
сводка решений — `docs/journal/sessions/2026-11-19.md`.
