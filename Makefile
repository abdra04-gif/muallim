.DEFAULT_GOAL := help

# macOS: Pillow ищет libfribidi (арабский текст на картинках, ADR-0024) только в системных путях;
# Homebrew кладёт её в /opt/homebrew/lib. В Linux/Docker не нужно (apt install libfribidi0).
ifeq ($(shell uname),Darwin)
LIBS := DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
endif
.PHONY: logs try thesis thesis-ru annotation proposal research papers thesis-check trace husary-cuts design help setup check lint test cov run run-stub db-sync db-up db-down db-shell backup backup-db db-roles restore migrate migration report errors verify diagrams audit hygiene

help: ## Список команд
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Установить зависимости и pre-commit
	uv sync
	uv run pre-commit install

check: lint test ## Все проверки, как в CI

lint: ## ruff + mypy + архитектура
	uv run ruff format --no-cache --check .
	uv run ruff check --no-cache .
	uv run mypy
	uv run lint-imports

test: ## Тесты с покрытием
	$(LIBS) uv run pytest -q --cov --cov-report=term-missing:skip-covered

run: db-sync ## Бот с моделью (нужно uv sync --extra ml)
	$(LIBS) uv run muallim

try: ## Проверка бота в терминале: make try a='"/start" "✅ Да, разрешаю" "🎤"' (без Telegram и .env)
	$(LIBS) uv run muallim --test $(if $(a),$(a),"/start")

run-stub: db-sync ## Бот с заглушкой распознавания
	$(LIBS) ASR_BACKEND=stub uv run muallim

db-up: ## PostgreSQL в Docker
	@mkdir -p data/audio data/erasures  # иначе Docker создаст их от root, и бот не сможет писать
	docker compose up -d postgres

db-down: ## Остановить PostgreSQL
	docker compose stop postgres

db-shell: ## Консоль psql к базе в Docker (выход — \q)
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

backup: ## Резервная копия: БД + голосовые записи → data/backups/<дата>/ (с проверкой и SHA256SUMS)
	sh scripts/db/backup.sh

restore: ## Восстановить из копии: make restore d=data/backups/<дата> (ПЕРЕЗАПИШЕТ данные, спросит «да»)
	@test -n "$(d)" || (echo "укажите d=data/backups/<дата>" && exit 1)
	sh scripts/db/restore.sh "$(d)"

backup-db: ## Копия только БД (секунды) — её делает make migrate
	sh scripts/db/backup.sh --db-only

migrate: backup-db ## Применить миграции входом владельца схемы (сначала — копия БД)
	uv run alembic upgrade head

db-roles: ## Три входа в БД (владелец, бот, просмотр) и пароли в .env — запускает человек
	sh scripts/db/roles.sh

db-sync: ## Если в БД не все миграции — копия и upgrade; иначе ничего
	@if uv run alembic current 2>/dev/null | grep -q '(head)'; then :; else \
		echo 'БД отстаёт от кода — применяю миграции'; $(MAKE) migrate; fi

migration: ## Новая миграция: make migration m="описание"
	@test -n "$(m)" || (echo 'укажите m="описание"' && exit 1)
	uv run alembic revision --autogenerate -m "$(m)" --rev-id $$(printf "%04d" $$(( $$(ls migrations/versions/*.py | wc -l) + 1 )))

husary-cuts: ## Нарезка «как правильно» из чтения Хусари: make husary-cuts a="--sections letter"
	uv run --extra ml python scripts/audio/husary_cuts.py $(a)

errors: ## Каталог ошибок: make errors a="--letter ص --lesson L18" (все фильтры: --help)
	uv run muallim-research errors $(a)

verify: ## Сверка БД и файлов записей: потери, лишние, повреждённые
	uv run muallim-research verify

logs: ## Последние строки лога бота (logs/bot.log, ADR-0048); n=200 — больше строк
	@tail -n $(if $(n),$(n),50) logs/bot.log 2>/dev/null || echo "Лога ещё нет: бот не запускался через make run"

report: ## Отчёт по данным исследования
	uv run muallim-research report

thesis: ## Диссертация LaTeX, английская версия → thesis/build/main.pdf
	cd thesis && latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build main.tex

thesis-ru: ## Диссертация LaTeX, русская версия → thesis/build/main-ru.pdf
	cd thesis && latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build main-ru.tex

annotation: ## Аннотация к ВКР на русском (4–5 с., Положение о ГИА п. 6.10) → thesis/build/annotation-ru.pdf
	cd thesis && latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build annotation-ru.tex

proposal: ## Предложение темы (en, ru) → thesis/build/proposal-en.pdf, proposal-ru.pdf
	cd thesis && for f in proposal-en proposal-ru; do latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build $$f.tex || exit 1; done

research: ## Исследовательский обзор (en, ru) → thesis/build/research-en.pdf, research-ru.pdf
	cd thesis && for f in research-en research-ru; do latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build $$f.tex || exit 1; done

papers: thesis thesis-ru annotation proposal research ## Все документы диссертации на двух языках

thesis-check: ## Проверка вёрстки: арабский, кириллица, ссылки, рисунки → thesis/build/check.pdf
	cd thesis && latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build check.tex

trace: ## Трассировка: требования ↔ тесты сейчас, исследование, отпечаток версии → docs/requirements/verification-status.md
	uv run python scripts/trace.py $(a)

design: ## Макеты экранов бота из кода → docs/design/screens/
	$(LIBS) uv run python scripts/render_screens.py
	uv run python scripts/render_mockups.py

diagrams: ## Перерисовать схемы в docs/architecture/diagrams
	scripts/render_diagrams.sh

audit: ## Проверка зависимостей на уязвимости
	uv run pip-audit

hygiene: ## Объявленные зависимости (deptry) и безопасность CI (zizmor); версии закреплены
	uvx deptry@0.25.1 src
	uvx zizmor@1.30.1 --offline .github/workflows
