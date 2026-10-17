.DEFAULT_GOAL := help

# macOS: Pillow ищет libfribidi (арабский текст на картинках, ADR-0024) только в системных путях;
# Homebrew кладёт её в /opt/homebrew/lib. В Linux/Docker не нужно (apt install libfribidi0).
ifeq ($(shell uname),Darwin)
LIBS := DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
endif
.PHONY: thesis thesis-check trace husary-cuts design help setup check lint test cov run run-stub db-up db-down db-shell backup restore migrate migration report errors diagrams audit

help: ## Список команд
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Установить зависимости и pre-commit
	uv sync
	uv run pre-commit install

check: lint test ## Все проверки, как в CI

lint: ## ruff + mypy + архитектура
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run lint-imports

test: ## Тесты с покрытием
	$(LIBS) uv run pytest -q --cov --cov-report=term-missing:skip-covered

run: ## Бот с моделью (нужно uv sync --extra ml)
	$(LIBS) uv run muallim

run-stub: ## Бот с заглушкой распознавания
	$(LIBS) ASR_BACKEND=stub uv run muallim

db-up: ## PostgreSQL в Docker
	docker compose up -d postgres

db-down: ## Остановить PostgreSQL
	docker compose stop postgres

db-shell: ## Консоль psql к базе в Docker (выход — \q)
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

backup: ## Резервная копия: БД (pg_dump) + голосовые записи → data/backups/<дата>/
	@d=data/backups/$$(date +%Y-%m-%d_%H%M%S); mkdir -p $$d && \
	docker compose exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" -Fc "$$POSTGRES_DB"' > $$d/db.dump && \
	tar -czf $$d/audio.tar.gz -C data audio 2>/dev/null || true; \
	ls -la $$d && echo "Копия: $$d (хранить вне ноутбука — см. docs/data/browsing.md)"

restore: ## Восстановить БД из копии: make restore d=data/backups/<дата> (ПЕРЕЗАПИШЕТ данные)
	@test -n "$(d)" || (echo "укажите d=data/backups/<дата>" && exit 1)
	docker compose exec -T postgres sh -c 'pg_restore -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --clean --if-exists' < $(d)/db.dump
	@test ! -f $(d)/audio.tar.gz || tar -xzf $(d)/audio.tar.gz -C data

migrate: ## Применить миграции
	uv run alembic upgrade head

migration: ## Новая миграция: make migration m="описание"
	@test -n "$(m)" || (echo 'укажите m="описание"' && exit 1)
	uv run alembic revision --autogenerate -m "$(m)" --rev-id $$(printf "%04d" $$(( $$(ls migrations/versions/*.py | wc -l) + 1 )))

husary-cuts: ## Нарезка «как правильно» из чтения Хусари: make husary-cuts a="--sections letter"
	uv run --extra ml python scripts/audio/husary_cuts.py $(a)

errors: ## Каталог ошибок: make errors a="--letter ص --lesson L18" (все фильтры: --help)
	uv run muallim-research errors $(a)

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
