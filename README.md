# Muallim — ИИ-тренажёр чтения по «Аль-Муаллим ас-Сани»

Магистерская диссертация: Исмаилов, 2026.

Telegram-бот, который учит читать по-арабски по учебнику Ахмада Хади Максуди «Муаллим ас-Сани»
(«Второй учитель»). Ученик читает вслух букву или слово, бот распознаёт произношение моделью
Quran Muaalem, находит ошибки и объясняет их по-русски. Каждая попытка сохраняется (аудио — только
с согласия), чтобы изучать ошибки учеников и модели, размечать данные и улучшать проверку.

## Быстрый старт
```bash
make setup                         # зависимости + pre-commit
cp .env.example .env               # вписать BOT_TOKEN и пароль БД
make db-up && make migrate         # PostgreSQL в Docker + схема
make run-stub                      # бот без модели (для проверки интерфейса)
uv sync --extra ml && make run     # бот с моделью (~2 ГБ, нужен ffmpeg)
```

## Для исследователя
```bash
make report                                              # отчёт → analytics/reports/
uv run muallim-research annotation-export --limit 50     # очередь на разметку (CSV)
uv run muallim-research annotation-import FILE --annotator A1
uv run muallim-research dataset-export                   # датасет → data/exports/<дата>/
```

## Документация
Всё — в [`docs/`](docs/README.md): требования, архитектура со схемами, решения (ADR, включая
отклонённые идеи), источники с привязкой к коду, словарь данных, разметка, безопасность,
методика, материалы для диссертации, история запросов к ИИ-агенту.

## Качество
`make check` — ruff, mypy --strict, import-linter (архитектура), pytest (покрытие ≥ 80 %).
То же в CI, плюс gitleaks и pip-audit.
