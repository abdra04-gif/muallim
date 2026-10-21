#!/bin/sh
# Три входа в БД (ADR-0054): muallim_owner (миграции), muallim_app (бот), muallim_reader (DBeaver).
# Новые случайные пароли → роли и права в базе (scripts/db/roles.sql) → строки в .env.
# Запускает человек (CLAUDE.md: всё про персональные данные). Пароли на экран не выводятся.
# Повторный запуск = смена паролей и повторная раздача прав (например, после новой миграции).
# После запуска перезапустите бота: make run.
set -eu
umask 077
cd "$(dirname "$0")/../.."

[ -f .env ] || { echo "Нет .env" >&2; exit 1; }
admin=$(sed -n 's/^POSTGRES_USER=//p' .env)
db=$(sed -n 's/^POSTGRES_DB=//p' .env)
owner=$(openssl rand -hex 24)  # только 0-9a-f: не нужно экранировать в URL и SQL
app=$(openssl rand -hex 24)
reader=$(openssl rand -hex 24)

# Docker Compose проверяет APP_DB_PASSWORD сервиса bot даже для команды к postgres, а пароль
# появляется только после этого скрипта — до первого запуска подставляем заглушку (бот её не видит).
# Пароли — через stdin (\set), а не аргументами: аргументы видны в списке процессов (ps).
{
  printf '\\set owner_password %s\n\\set app_password %s\n\\set reader_password %s\n' \
    "'$owner'" "'$app'" "'$reader'"
  cat scripts/db/roles.sql
} | APP_DB_PASSWORD="${APP_DB_PASSWORD:-roles-not-created-yet}" \
  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "$admin" -d "$db" -f -

DB="$db" OWNER="$owner" APP="$app" READER="$reader" python3 - <<'PY'
import os, re
from pathlib import Path

env, db = Path(".env"), os.environ["DB"]
text = env.read_text()
values = {
    # бот и muallim-research — входом muallim_app (с компьютера: порт 5432 на localhost)
    "DATABASE_URL": f"postgresql+asyncpg://muallim_app:{os.environ['APP']}@localhost:5432/{db}",
    # alembic (make migrate) — входом владельца схемы
    "MIGRATION_DATABASE_URL": f"postgresql+asyncpg://muallim_owner:{os.environ['OWNER']}@localhost:5432/{db}",
    # для бота в Docker (docker-compose.yml собирает адрес сам)
    "APP_DB_PASSWORD": os.environ["APP"],
    # DBeaver: пользователь muallim_reader, этот пароль
    "READER_DB_PASSWORD": os.environ["READER"],
}
for key, value in values.items():
    line = f"{key}={value}"
    pattern = re.compile(rf"(?m)^{key}=.*$")
    text = pattern.sub(line, text) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"
env.write_text(text)
env.chmod(0o600)
PY

echo "Готово: три входа созданы, пароли записаны в .env (DBeaver — пользователь muallim_reader,"
echo "пароль — READER_DB_PASSWORD). Перезапустите бота: make run"
