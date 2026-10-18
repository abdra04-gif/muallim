.DEFAULT_GOAL := help

# macOS: Pillow ищет libfribidi (арабский текст на картинках, ADR-0024) только в системных путях;
# Homebrew кладёт её в /opt/homebrew/lib. В Linux/Docker не нужно (apt install libfribidi0).
ifeq ($(shell uname),Darwin)
LIBS := DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
endif
.PHONY: thesis thesis-check trace husary-cuts design help setup check lint test cov run run-stub db-sync db-up db-down db-shell backup restore migrate migration report errors verify diagrams audit

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

run-stub: db-sync ## Бот с заглушкой распознавания
	$(LIBS) ASR_BACKEND=stub uv run muallim

db-up: ## PostgreSQL в Docker
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

migrate: backup ## Применить миграции (сначала — проверенная копия)
	uv run alembic upgrade head

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

report: ## Отчёт по данным исследования
	uv run muallim-research report

thesis: ## Диссертация LaTeX → thesis/build/main.pdf
	cd thesis && latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build main.tex

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
