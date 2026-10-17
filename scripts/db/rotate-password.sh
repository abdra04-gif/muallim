#!/bin/sh
# Сменить пароль PostgreSQL: новый случайный пароль → в базе (ALTER USER) → в .env.
# Запускает человек (CLAUDE.md: всё про персональные данные). Пароль на экран не выводится.
# После смены перезапустите бота: make run
set -eu
cd "$(dirname "$0")/../.."

[ -f .env ] || { echo "Нет .env" >&2; exit 1; }
user=$(sed -n 's/^POSTGRES_USER=//p' .env)
db=$(sed -n 's/^POSTGRES_DB=//p' .env)
new=$(openssl rand -hex 24)  # только 0-9a-f: не нужно экранировать в URL и SQL

docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "$user" -d "$db" \
  -c "ALTER USER \"$user\" PASSWORD '$new';"

NEW="$new" python3 - <<'EOF'
import os, re
from pathlib import Path

env = Path(".env")
new = os.environ["NEW"]
text = env.read_text()
text = re.sub(r"(?m)^POSTGRES_PASSWORD=.*$", f"POSTGRES_PASSWORD={new}", text)
text = re.sub(r"(?m)^(DATABASE_URL=[^:]+://[^:]+:)[^@]*@", rf"\g<1>{new}@", text)
env.write_text(text)
env.chmod(0o600)  # читать .env может только владелец
EOF

echo "Пароль базы изменён и записан в .env. Перезапустите бота: make run"
